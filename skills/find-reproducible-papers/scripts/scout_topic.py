#!/usr/bin/env python3
"""Topic -> N license-clean, reproducible-signal example candidates.

Driver around find_reproducible_papers.py. Given a topic and a target count N,
it searches arXiv, screens each candidate for reproducibility signals AND a
license-redistributability gate, and accumulates candidates that are usable as
APP example papers until N are found (or the scan limit is hit).

It runs NO paper code and spawns no agents — it is the cheap, deterministic
front of the pipeline. A candidate that passes here is a license-clean, public-
code-bearing, CPU-feasible (non-heavy) paper worth a Stage-C reproduce-check
(see SKILL.md) before any simulate-publication staging run.

Usage:
    scout_topic.py --topic "condensed matter physics" --until 10 --use-github
    scout_topic.py --topic ai --until 10 --allow-reference-only
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

# Import the screener module living next to this file.
_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("frp", _HERE / "find_reproducible_papers.py")
frp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(frp)

# Topic -> (categories, extra keywords). Unknown topics fall back to keyword search.
TOPIC_MAP: dict[str, dict[str, Any]] = {
    "ai": {"categories": ["cs.LG", "cs.CL", "stat.ML"], "keywords": []},
    "machine learning": {"categories": ["cs.LG", "stat.ML"], "keywords": []},
    "deep learning": {"categories": ["cs.LG"], "keywords": []},
    "nlp": {"categories": ["cs.CL"], "keywords": []},
    "interpretability": {"categories": ["cs.LG"], "keywords": ["interpretability", "sparse autoencoder"]},
    "condensed matter": {"categories": ["cond-mat.str-el", "cond-mat.stat-mech",
                                        "cond-mat.quant-gas", "cond-mat.mes-hall"], "keywords": []},
    "condensed matter physics": {"categories": ["cond-mat.str-el", "cond-mat.stat-mech",
                                                 "cond-mat.quant-gas", "cond-mat.mes-hall"], "keywords": []},
    "statistical physics": {"categories": ["cond-mat.stat-mech"], "keywords": []},
    "quantum": {"categories": ["quant-ph"], "keywords": []},
    "quantum computing": {"categories": ["quant-ph"], "keywords": []},
    "quantum information": {"categories": ["quant-ph"], "keywords": []},
    "tensor network": {"categories": ["quant-ph", "cond-mat.str-el"], "keywords": ["tensor network"]},
    "astrophysics": {"categories": ["astro-ph.GA", "astro-ph.CO", "astro-ph.HE"], "keywords": []},
    "high energy": {"categories": ["hep-th", "hep-ph"], "keywords": []},
}


def resolve_topic(topic: str) -> tuple[list[str], list[str]]:
    key = topic.strip().lower()
    if key in TOPIC_MAP:
        t = TOPIC_MAP[key]
        return list(t["categories"]), list(t["keywords"])
    # Unknown topic: search all categories by keyword.
    return [], [topic.strip()]


def pwc_candidate_ids(db_path: str, terms: list[str], limit: int) -> list[str]:
    """arXiv ids of papers with OFFICIAL code in the PwC index whose title matches
    all given terms (AND). Title is the only field-proxy the links dump carries."""
    sig_terms = [t for t in terms if len(t) >= 4] or terms
    where = " AND ".join("paper_title LIKE ?" for _ in sig_terms)
    sql = (f"SELECT DISTINCT arxiv_id FROM links WHERE is_official=1 AND arxiv_id != '' "
           f"AND ({where}) LIMIT ?")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = conn.execute(sql, [f"%{t}%" for t in sig_terms] + [limit]).fetchall()
    conn.close()
    return [r[0] for r in rows]


def is_good(row: dict[str, Any], require_redistributable: bool) -> bool:
    """A usable example candidate: real code + reproducibility signal + license OK."""
    sig, sc = row["signals"], row["score"]
    has_code = bool(sig.get("repo")) or bool(sig.get("declared_code_links"))
    tier_ok = sc["tier"] in ("A-strong", "B-promising")   # heavy-compute is already capped to C
    if not (has_code and tier_ok):
        return False
    if require_redistributable and not (sig.get("paper_license") or {}).get("redistributable"):
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--topic", required=True, help="Topic (e.g. 'condensed matter physics', 'ai').")
    p.add_argument("--until", type=int, default=10, help="Target number of good candidates (default 10).")
    p.add_argument("--scan-limit", type=int, default=200, help="Max papers to gather/screen (default 200).")
    p.add_argument("--from-date", dest="from_date", help="Earliest submission date YYYY-MM-DD.")
    p.add_argument("--to-date", dest="to_date", help="Latest submission date YYYY-MM-DD.")
    p.add_argument("--keywords", help="Extra topic keywords (';'/',' separated) appended to the topic.")
    p.add_argument("--source", choices=["arxiv", "pwc"], default="arxiv",
                   help="arxiv: live arXiv search (default). pwc: papers with official code from the "
                        "Papers-with-Code index (title-matched), no arXiv search throttle.")
    p.add_argument("--pwc-index", dest="pwc_index", default=frp.DEFAULT_PWC_DB,
                   help="Papers-with-Code sqlite index (build with build_pwc_index.py).")
    p.add_argument("--use-github", dest="use_github", action="store_true",
                   help="Enrich repos via gh (license/stars/recency).")
    p.add_argument("--no-hf", dest="use_hf", action="store_false", help="Skip Hugging Face enrichment.")
    p.add_argument("--allow-reference-only", dest="allow_ref_only", action="store_true",
                   help="Keep papers whose license forbids re-hosting (default: drop them).")
    p.add_argument("--timeout", type=float, default=45.0)
    p.add_argument("--out-root", dest="out_root", default="working/find-reproducible-papers")
    p.add_argument("--timestamp", help="Override run timestamp.")
    args = p.parse_args(argv)

    if args.use_github and not frp._have_gh():
        frp.eprint("[warn] --use-github set but `gh` not found; continuing without it.")
        args.use_github = False

    require_redistributable = not args.allow_ref_only
    cats, kws = resolve_topic(args.topic)
    if args.keywords:
        kws += [k.strip() for k in re.split(r"[;,]", args.keywords) if k.strip()]
    query = frp.build_search_query(cats, kws, "OR", [], args.from_date, args.to_date)

    slug = re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-")[:32] or "topic"
    stamp = args.timestamp or frp.now_stamp()
    out_dir = Path(args.out_root) / f"topic-{slug}-{stamp}"
    if out_dir.exists():
        frp.eprint(f"[error] {out_dir} already exists; pass a fresh --timestamp.")
        return 2
    out_dir.mkdir(parents=True)

    pwc_db = args.pwc_index if Path(args.pwc_index).is_file() else None
    criteria = {"topic": args.topic, "source": args.source, "categories": cats, "keywords": kws,
                "search_query": query, "until": args.until, "scan_limit": args.scan_limit,
                "require_redistributable": require_redistributable, "use_github": args.use_github,
                "use_hf": args.use_hf, "pwc_index": pwc_db,
                "generated": frp.iso_now(), "_note": frp.SCORE_DISCLAIMER}
    frp.write_text(out_dir / "criteria.json", json.dumps(criteria, indent=2, ensure_ascii=False) + "\n")

    if args.source == "pwc":
        if not pwc_db:
            frp.eprint(f"[error] --source pwc needs the index at {args.pwc_index}; build it with build_pwc_index.py.")
            return 2
        terms = (kws or []) + [w for w in re.findall(r"[A-Za-z]+", args.topic) if len(w) >= 4]
        ids = pwc_candidate_ids(pwc_db, terms or [args.topic], args.scan_limit)
        frp.eprint(f"[scout] pwc: {len(ids)} papers with official code match {terms}; fetching metadata...")
        cands = frp.arxiv_fetch_by_ids(ids, timeout=args.timeout) if ids else []
    else:
        frp.eprint(f"[scout] topic={args.topic!r} query={query}")
        cands = frp.arxiv_search(query, args.scan_limit, "submittedDate", "descending", timeout=args.timeout)
    frp.eprint(f"[scout] gathered {len(cands)} candidates; screening until {args.until} good...")
    if not cands:
        frp.eprint("[done] No candidates (arXiv API may be blocked, or no PwC matches). criteria.json written.")
        return 1

    weights = dict(frp.DEFAULT_WEIGHTS)
    rows: list[dict[str, Any]] = []
    good: list[dict[str, Any]] = []
    for i, cand in enumerate(cands, 1):
        if len(good) >= args.until:
            break
        sig = frp.enrich_candidate(cand, use_github=args.use_github, hf=args.use_hf,
                                   timeout=args.timeout, paper_license=True, pwc_db=pwc_db)
        sc = frp.score_candidate(cand, sig, weights)
        row = {"cand": cand, "signals": sig, "score": sc}
        rows.append(row)
        if is_good(row, require_redistributable):
            good.append(row)
            frp.eprint(f"[scout] {len(good)}/{args.until}  {cand['arxiv_id']} "
                       f"({sc['tier']}, {sc.get('reuse')}) {cand['title'][:60]}")

    frp.write_jsonl(out_dir / "screening.jsonl",
                    [{"arxiv_id": r["cand"]["arxiv_id"], **r["score"],
                      "good": is_good(r, require_redistributable),
                      "signals": r["signals"], "title": r["cand"]["title"],
                      "abs_url": r["cand"]["abs_url"]} for r in rows])

    shortlist = [{
        "arxiv_id": r["cand"]["arxiv_id"], "title": r["cand"]["title"], "abs_url": r["cand"]["abs_url"],
        "score": r["score"]["score"], "tier": r["score"]["tier"], "reuse": r["score"].get("reuse"),
        "paper_license": (r["signals"].get("paper_license") or {}).get("label"),
        "code": frp.best_code_link(r["signals"]),
        "code_confirmed": frp._code_confirmed(r["signals"]),
        "primary_category": r["cand"]["primary_category"], "red_flags": r["score"]["red_flags"],
    } for r in good]
    frp.write_text(out_dir / "topic-shortlist.json", json.dumps(
        {"topic": args.topic, "found": len(good), "target": args.until, "scanned": len(rows),
         "_note": frp.SCORE_DISCLAIMER + " Next: run a Stage-C reproduce-check (SKILL.md) on each before staging.",
         "papers": shortlist}, indent=2, ensure_ascii=False) + "\n")

    # report
    md = [f"# Topic scout: {args.topic}\n",
          f"- Generated: {frp.iso_now()}",
          f"- Found {len(good)}/{args.until} good candidates (scanned {len(rows)} of {len(cands)} gathered)",
          f"- Gate: code + tier A/B + {'redistributable license' if require_redistributable else 'any license (reference-only allowed)'}",
          f"- Query: `{query}`\n",
          "> Screening prior, not a reproducibility verdict. Run Stage-C reproduce-checks before staging.\n",
          "| # | arXiv | Title | Cat | Tier | Reuse | License | Code |",
          "|---|-------|-------|-----|------|-------|---------|------|"]
    for i, s in enumerate(shortlist, 1):
        code = f"[link]({s['code']})" if s["code"] else "—"
        md.append(f"| {i} | [{s['arxiv_id']}]({s['abs_url']}) | {frp._short(s['title'], 55)} | "
                  f"{s['primary_category']} | {s['tier']} | {s['reuse']} | {s['paper_license']} | {code} |")
    if len(good) < args.until:
        md.append(f"\n_Only {len(good)} found within scan-limit {args.scan_limit}. "
                  f"Raise --scan-limit, widen the date window, or relax the topic._")
    frp.write_text(out_dir / "topic-report.md", "\n".join(md) + "\n")

    frp.eprint(f"\n[done] {len(good)}/{args.until} good candidates. Report: {out_dir / 'topic-report.md'}")
    print(str(out_dir))
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
