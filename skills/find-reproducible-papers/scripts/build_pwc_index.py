#!/usr/bin/env python3
"""Build a local arXiv->code index from the Papers with Code archive.

Papers with Code was sunset; its dataset lives on Hugging Face as
`pwc-archive/links-between-paper-and-code` (CC-BY-SA-4.0). This one-time builder
downloads that parquet (~41 MB) and writes a stdlib-`sqlite3`-readable index so
the screener/driver can look up an official code repo for an arXiv id offline
(no rate limits). The snapshot is frozen (~2025): papers newer than that are not
in it, so this complements — does not replace — the live arXiv/GitHub path.

Needs `pandas` + `pyarrow` for this build step only; the runtime lookup is stdlib.

    pip install pandas pyarrow
    build_pwc_index.py            # -> working/find-reproducible-papers/cache/pwc-links.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

PARQUET_URL = ("https://huggingface.co/datasets/pwc-archive/"
               "links-between-paper-and-code/resolve/main/data/train-00000-of-00001.parquet")
DEFAULT_DB = "working/find-reproducible-papers/cache/pwc-links.sqlite"
ATTRIBUTION = ("Papers with Code (pwc-archive/links-between-paper-and-code on Hugging Face), "
               "CC-BY-SA-4.0. Frozen snapshot.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=DEFAULT_DB, help=f"sqlite output path (default {DEFAULT_DB}).")
    p.add_argument("--parquet-url", default=PARQUET_URL)
    p.add_argument("--official-only", action="store_true",
                   help="Keep only is_official=True links (smaller index).")
    p.add_argument("--parquet-file", help="Use a local parquet file instead of downloading.")
    args = p.parse_args(argv)

    try:
        import pandas as pd  # noqa: F401  (build-time only)
    except ImportError:
        print("This builder needs pandas + pyarrow: pip install pandas pyarrow", file=sys.stderr)
        return 2

    if args.parquet_file:
        path = Path(args.parquet_file)
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
        tmp.close()
        path = Path(tmp.name)
        print(f"[pwc] downloading {args.parquet_url} ...", file=sys.stderr)
        req = urllib.request.Request(args.parquet_url, headers={"User-Agent": "app-pwc-index/0.1"})
        with urllib.request.urlopen(req, timeout=120) as resp, path.open("wb") as fh:
            fh.write(resp.read())
        print(f"[pwc] downloaded {path.stat().st_size // 1024} KiB", file=sys.stderr)

    df = pd.read_parquet(path)
    cols = ["paper_arxiv_id", "repo_url", "is_official", "framework", "paper_title"]
    df = df[[c for c in cols if c in df.columns]].copy()
    df = df[df["paper_arxiv_id"].notna() & (df["paper_arxiv_id"] != "")]
    # normalise arxiv id to the bare form (drop version suffix)
    df["arxiv_id"] = df["paper_arxiv_id"].astype(str).str.replace(r"v\d+$", "", regex=True)
    df["is_official"] = df.get("is_official", False).fillna(False).astype(bool).astype(int)
    if args.official_only:
        df = df[df["is_official"] == 1]
    df["framework"] = df.get("framework", "").fillna("")
    df["paper_title"] = df.get("paper_title", "").fillna("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(str(out))
    conn.execute("CREATE TABLE links (arxiv_id TEXT, repo_url TEXT, is_official INTEGER, "
                 "framework TEXT, paper_title TEXT)")
    conn.executemany(
        "INSERT INTO links VALUES (?,?,?,?,?)",
        df[["arxiv_id", "repo_url", "is_official", "framework", "paper_title"]].itertuples(index=False, name=None),
    )
    conn.execute("CREATE INDEX idx_arxiv ON links(arxiv_id)")
    conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    conn.executemany("INSERT INTO meta VALUES (?,?)",
                     [("attribution", ATTRIBUTION), ("rows", str(len(df))),
                      ("official_only", str(bool(args.official_only)))])
    conn.commit()
    n_official = conn.execute("SELECT COUNT(*) FROM links WHERE is_official=1").fetchone()[0]
    n_ids = conn.execute("SELECT COUNT(DISTINCT arxiv_id) FROM links").fetchone()[0]
    conn.close()

    print(f"[pwc] wrote {out}: {len(df)} links, {n_ids} distinct arXiv ids, {n_official} official.",
          file=sys.stderr)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
