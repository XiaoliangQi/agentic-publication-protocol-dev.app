#!/usr/bin/env python3
"""Gather arXiv candidates and screen them for reproducibility readiness.

This is the deterministic half of the `find-reproducible-papers` dev skill. It
does NOT execute any paper code and it does NOT verify reproducibility. It only:

  Stage A - Gather:  query the arXiv API by criteria (categories, keywords,
                     date window) and collect candidate papers with metadata.
  Stage B - Screen:  for each candidate, collect *cheap* availability signals
                     (author-declared code link, GitHub repo metadata, Hugging
                     Face linked artifacts, data/figure/compute hints) and score
                     a transparent "reproducibility-readiness" prior, then sort
                     candidates into triage tiers and emit a shortlist.

The score is a triage prior for prioritising which papers a human/agent should
deep-assess next. It is NOT a reproducibility result. Actually verifying that a
paper reproduces (running code, checking a figure) is Stage C, performed by the
agent per SKILL.md, and recorded with the protocol's reproduce-results statuses
(reproduced / runs-but-differs / blocked-* / manual-only).

stdlib only. GitHub enrichment is optional and uses the `gh` CLI if available.

Usage:
    find_reproducible_papers.py [--preset project] [--categories cat,cat]
        [--keywords "term; term"] [--from-date 2024-01-01] [--max-candidates 60]
        [--shortlist-size 5] [--use-github] [--require-code-hint]
        [--criteria-file criteria.json] [--out-root working/find-reproducible-papers]

Outputs are written under:
    <out-root>/<timestamp>/
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# --- arXiv Atom / OpenSearch namespaces -------------------------------------
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"

ARXIV_API = "http://export.arxiv.org/api/query"
HF_PAPERS_API = "https://huggingface.co/api/papers/{}"
USER_AGENT = (
    "app-find-reproducible-papers/0.1 "
    "(Agentic Publication Protocol dev tool; +https://github.com/LionSR/AgenticPublicationProtocol)"
)

# arXiv asks callers to wait ~3s between requests; be polite.
ARXIV_POLITENESS_SECONDS = 3.5
ARXIV_PAGE_SIZE = 50

# --- Domain presets ("match project": physics + ML interpretability) --------
# Categories chosen to resemble the existing data/example-papers papers
# (quant-ph, cond-mat, math-ph) plus the one ML-interpretability case.
PRESETS: dict[str, dict[str, Any]] = {
    "project": {
        "categories": [
            "quant-ph",
            "cond-mat.str-el",
            "cond-mat.stat-mech",
            "math-ph",
            "cs.LG",
        ],
        "keywords": [],
        "keyword_mode": "OR",
        "description": "Project-matching mix: quantum / condensed-matter physics plus ML.",
    },
    "quant-ph": {
        "categories": ["quant-ph"],
        "keywords": [],
        "keyword_mode": "OR",
        "description": "Quantum physics only.",
    },
    "cond-mat": {
        "categories": ["cond-mat.str-el", "cond-mat.stat-mech", "cond-mat.quant-gas"],
        "keywords": [],
        "keyword_mode": "OR",
        "description": "Condensed-matter (strongly correlated / statistical / cold atoms).",
    },
    "ml-interp": {
        "categories": ["cs.LG", "cs.CL"],
        "keywords": ["interpretability", "sparse autoencoder", "mechanistic"],
        "keyword_mode": "OR",
        "description": "Machine-learning interpretability.",
    },
}
DEFAULT_PRESET = "project"

# --- Signal regexes ----------------------------------------------------------
CODE_URL_RE = re.compile(
    r"https?://(?:www\.)?"
    r"(github\.com|gitlab\.com|bitbucket\.org|zenodo\.org|osf\.io|"
    r"codeocean\.com|figshare\.com|huggingface\.co|gitee\.com|sourceforge\.net)"
    r"/[^\s)>\]\"'}]+",
    re.IGNORECASE,
)
# Not-laptop-reproducible red flags in abstract or comment text. The target
# machine is an Apple-Silicon MacBook (CPU/MPS, no CUDA/GPU, modest RAM), so this
# covers GPU/CUDA dependence and large model training AND the domain-specific
# costs that block physics examples: large bond dimension, large exact
# diagonalisation, many-core / core-hour budgets, and large-RAM jobs.
HEAVY_RE = re.compile(
    # GPU / large-model training (no GPU on a MacBook)
    r"\bA100\b|\bH100\b|\bV100\b|\bTPU\b|\bCUDA\b|multi[- ]?gpus?|petaflop|exaflop|supercomput\w*"
    r"|pre[- ]?training\b|pretrain\b|foundation models?"
    r"|weeks? of (?:training|compute)|months? of (?:training|compute)"
    r"|thousands? of GPU|hundreds? of GPU|GPU[- ]?(?:days|years)"
    r"|distributed training|large[- ]scale cluster"
    r"|\d+\s*(?:B|billion)[- ]?parameter"
    # physics / many-body scale signals
    r"|bond[- ]?dimension[s]?\s*(?:of\s+|up to\s+)?[=:~]?\s*(?:\d{4,}|10\^?\d|10\*\*\d)"
    r"|\bchi\s*[=~]\s*(?:\d{4,}|10\^?\d)"
    r"|\b\d{3,}\s*cores\b"
    r"|\b(?:CPU|core|node)[- ]?(?:hours|years)\b"
    r"|\b\d+\s*TB\s+(?:of\s+)?(?:RAM|memory)"
    r"|\b[1-9]\d{2,}\s*GB\s+(?:of\s+)?(?:RAM|memory)"
    r"|(?:exact|full|lanczos|krylov)[- ]?diagonaliz\w+[^.]{0,40}?\b(?:[4-9]\d|\d{3,})\s*(?:sites?|spins?|qubits?|orbitals?)",
    re.IGNORECASE,
)
# Genuine data-artifact availability. "open-source"/"publicly available" live in
# CODE_HINT_RE only, so one boilerplate phrase is not double-counted as data+code.
DATA_RE = re.compile(
    r"\b(dataset|data (?:are|is) (?:publicly )?available|data availability|"
    r"zenodo|figshare|open data|benchmark)\b",
    re.IGNORECASE,
)
CODE_HINT_RE = re.compile(
    r"\b(code (?:is |are )?(?:publicly )?available|open[- ]source|publicly available|"
    r"source code|implementation is available|we (?:release|provide) (?:our )?code|"
    r"reproduc\w+)\b",
    re.IGNORECASE,
)
# Symbolic / computer-algebra tooling: a Mathematica/Sage/Lean notebook is itself
# reproducible code, and theorem/derivation language flags analytic papers that
# the protocol supports as first-class examples (see reproduce-results/paper-types.md).
SYMBOLIC_RE = re.compile(
    r"Mathematica|Wolfram|SageMath|\bSymPy\b|Lean\s?4|\bMagma\b|Macaulay2"
    r"|\.nb\b|\.wl\b|computer algebra|symbolic comput\w+",
    re.IGNORECASE,
)
THEORY_RE = re.compile(
    r"\b(theorem|lemma|proposition|corollary|proof|closed[- ]form|"
    r"analytic(?:al|ally)?|exact (?:solution|result)|rigorous(?:ly)?)\b",
    re.IGNORECASE,
)
FIG_RE = re.compile(r"(\d+)\s+figures?\b", re.IGNORECASE)
TAB_RE = re.compile(r"(\d+)\s+tables?\b", re.IGNORECASE)
# arXiv-aggregator repos (RSS feeds, awesome-lists, paper trackers) contain every
# arXiv id, so a code-search by id matches them spuriously. Skip these.
AGGREGATOR_RE = re.compile(
    r"arxiv|\brss\b|awesome|daily.?paper|paper.?(?:list|feed|track|digest|bot)|"
    r"reading.?list|bibliograph|sanity|feedly|newsletter|\bdigest\b",
    re.IGNORECASE,
)

OSI_LICENSE_IDS = {
    "MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "GPL-2.0", "GPL-3.0",
    "LGPL-2.1", "LGPL-3.0", "MPL-2.0", "ISC", "UNLICENSE", "CC0-1.0",
    "AGPL-3.0", "BSL-1.0", "EPL-2.0", "0BSD",
}

# --- Scoring rubric (triage prior, NOT a reproducibility verdict) -----------
# Documented in SKILL.md. Tunable via --criteria-file "weights".
DEFAULT_WEIGHTS: dict[str, int] = {
    "author_declared_repo": 40,   # code link found in abstract/comment (high confidence)
    "repo_found_via_search": 20,  # plausible repo found via GitHub search (unconfirmed); only if no declared repo
    "osi_license": 12,            # repo carries a recognised OSI/open license
    "recent_activity": 10,        # repo pushed within RECENT_ACTIVITY_DAYS
    "data_signal": 10,            # abstract/comment mentions available data/benchmark
    "figures_present": 6,         # comment lists figures (concrete targets to reproduce)
    "hf_artifacts": 6,            # Hugging Face has linked models/datasets/spaces
    "code_hint_in_abstract": 8,   # explicit "code available"/"reproducible" language
    "symbolic_tooling": 8,        # Mathematica/Sage/Lean/etc. (derivation-checkable code)
    "theory_signal": 6,           # theorem/proof/analytic language (assess via derivation checks)
    "heavy_compute_penalty": -15, # heavy-compute red flag (hard to reproduce in a sandbox)
}
RECENT_ACTIVITY_DAYS = 365 * 2
# Calibrated for the default (no-GitHub) path, where the max realistic score is
# ~70 (declared repo 40 + data 10 + code-hint 8 + figures 6 + HF 6). A public
# author repo is the dominant signal, so a declared repo alone reaches tier B and
# a repo plus a couple of positives reaches tier A. With --use-github, license
# (+12) and recency (+10) push strong repos comfortably past TIER_A_MIN.
TIER_A_MIN = 60   # strong candidate: worth a real reproduction attempt
TIER_B_MIN = 35   # promising: public code located, some gaps


# --- small helpers -----------------------------------------------------------
def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def http_get(url: str, timeout: float, retries: int = 3, accept: str | None = None) -> bytes:
    """GET with a descriptive UA and backoff. Rate-limit aware (429/503): honors
    Retry-After and waits longer. Raises on final failure."""
    last_err: Exception | None = None
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            last_err = err
            if attempt >= retries - 1:
                break
            if err.code in (429, 503):  # rate limited / unavailable: wait longer
                ra = err.headers.get("Retry-After") if err.headers else None
                wait = float(ra) if (ra and str(ra).isdigit()) else min(60.0, 15.0 * (attempt + 1))
                eprint(f"[http] {err.code} on {url[:70]}...; backing off {wait:.0f}s")
                time.sleep(wait)
            else:
                time.sleep(2.0 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            last_err = err
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"GET failed for {url}: {last_err}")


# --- arXiv query building ----------------------------------------------------
def _yyyymmdd(value: str) -> str:
    """Accept YYYY-MM-DD or YYYYMMDD; return arXiv's YYYYMMDDHHMM form, validated."""
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) not in (8, 12):
        raise ValueError(f"Bad date {value!r}; use YYYY-MM-DD.")
    try:
        dt.datetime.strptime(digits[:8], "%Y%m%d")  # reject e.g. month 13 / day 40
    except ValueError as err:
        raise ValueError(f"Bad date {value!r}; use a real calendar date YYYY-MM-DD.") from err
    return digits if len(digits) == 12 else digits + "0000"


def _all_field(term: str) -> str:
    """An `all:` clause, quoting multi-word terms as arXiv requires."""
    return f'all:"{term}"' if " " in term else f"all:{term}"


def build_search_query(
    categories: list[str],
    keywords: list[str],
    keyword_mode: str,
    exclude: list[str],
    from_date: str | None,
    to_date: str | None,
) -> str:
    """Compose an arXiv api `search_query` string (unencoded; urlencoded later)."""
    parts: list[str] = []
    if categories:
        cats = " OR ".join(f"cat:{c.strip()}" for c in categories if c.strip())
        parts.append(f"({cats})")
    if keywords:
        joiner = " OR " if keyword_mode.upper() == "OR" else " AND "
        kws = joiner.join(_all_field(k.strip()) for k in keywords if k.strip())
        if kws:
            parts.append(f"({kws})")
    if from_date or to_date:
        lo = _yyyymmdd(from_date) if from_date else "190001010000"
        hi = _yyyymmdd(to_date) if to_date else dt.datetime.now().strftime("%Y%m%d%H%M")
        parts.append(f"submittedDate:[{lo} TO {hi}]")
    query = " AND ".join(parts) if parts else "all:physics"
    for term in exclude:
        term = term.strip()
        if term:
            query += f" ANDNOT {_all_field(term)}"
    return query


def arxiv_search(
    query: str,
    max_results: int,
    sort_by: str,
    sort_order: str,
    timeout: float,
) -> list[dict[str, Any]]:
    """Page through the arXiv API and return parsed entries (best-effort, polite)."""
    entries: list[dict[str, Any]] = []
    start = 0
    while len(entries) < max_results:
        page = min(ARXIV_PAGE_SIZE, max_results - len(entries))
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": start,
                "max_results": page,
                "sortBy": sort_by,
                "sortOrder": sort_order,
            }
        )
        url = f"{ARXIV_API}?{params}"
        eprint(f"[arxiv] start={start} page={page} :: {url}")
        try:
            raw = http_get(url, timeout=timeout, retries=5)
        except RuntimeError as err:
            eprint(
                "\n[arxiv] ERROR: could not reach the arXiv API.\n"
                "        The endpoint is http://export.arxiv.org/api/query .\n"
                "        Check network/proxy access to export.arxiv.org and retry.\n"
                f"        Detail: {err}\n"
            )
            break
        total, page_entries = parse_atom(raw.decode("utf-8", errors="replace"))
        if not page_entries:
            break
        entries.extend(page_entries)
        start += len(page_entries)  # advance by what the server actually returned
        if total and start >= total:  # total == 0 means "unknown"; keep paging
            break
        time.sleep(ARXIV_POLITENESS_SECONDS)
    return entries[:max_results]


def arxiv_fetch_by_ids(ids: list[str], timeout: float, batch: int = 50) -> list[dict[str, Any]]:
    """Fetch arXiv metadata for specific ids via id_list (few, light calls)."""
    out: list[dict[str, Any]] = []
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        params = urllib.parse.urlencode({"id_list": ",".join(chunk), "max_results": len(chunk)})
        eprint(f"[arxiv] id_list batch {i // batch + 1} ({len(chunk)} ids)")
        try:
            raw = http_get(f"{ARXIV_API}?{params}", timeout=timeout, retries=5)
        except RuntimeError as err:
            eprint(f"[arxiv] id_list fetch failed: {err}")
            break
        _, entries = parse_atom(raw.decode("utf-8", errors="replace"))
        out.extend(entries)
        if i + batch < len(ids):
            time.sleep(ARXIV_POLITENESS_SECONDS)
    return out


def parse_atom(xml_text: str) -> tuple[int, list[dict[str, Any]]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        eprint(f"[arxiv] could not parse Atom response: {err}")
        return 0, []
    total_el = root.find(f"{OPENSEARCH}totalResults")
    total = int(total_el.text) if total_el is not None and total_el.text else 0
    return total, [parse_entry(e) for e in root.findall(f"{ATOM}entry")]


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_entry(entry: ET.Element) -> dict[str, Any]:
    raw_id = _text(entry.find(f"{ATOM}id"))  # e.g. http://arxiv.org/abs/2301.07041v2
    m = re.search(r"arxiv\.org/abs/(.+)$", raw_id)
    versioned = m.group(1) if m else raw_id
    bare = re.sub(r"v\d+$", "", versioned)

    authors = [_text(a.find(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")]
    categories = [c.get("term", "") for c in entry.findall(f"{ATOM}category")]
    primary_el = entry.find(f"{ARXIV_NS}primary_category")
    primary = primary_el.get("term", "") if primary_el is not None else (categories[0] if categories else "")

    pdf_url = ""
    for link in entry.findall(f"{ATOM}link"):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")

    comment = _text(entry.find(f"{ARXIV_NS}comment"))
    abstract = re.sub(r"\s+", " ", _text(entry.find(f"{ATOM}summary")))
    return {
        "arxiv_id": bare,
        "arxiv_id_versioned": versioned,
        "title": re.sub(r"\s+", " ", _text(entry.find(f"{ATOM}title"))),
        "authors": authors,
        "abstract": abstract,
        "primary_category": primary,
        "categories": categories,
        "published": _text(entry.find(f"{ATOM}published")),
        "updated": _text(entry.find(f"{ATOM}updated")),
        "comment": comment,
        "doi": _text(entry.find(f"{ARXIV_NS}doi")),
        "journal_ref": _text(entry.find(f"{ARXIV_NS}journal_ref")),
        "abs_url": f"https://arxiv.org/abs/{bare}",
        "pdf_url": pdf_url,
    }


# --- enrichment (cheap signals; NO code execution) --------------------------
def extract_code_links(*texts: str) -> list[str]:
    found: list[str] = []
    for text in texts:
        for m in CODE_URL_RE.finditer(text or ""):
            url = m.group(0).rstrip(".,);")
            if url not in found:
                found.append(url)
    return found


def hf_paper_signals(arxiv_id: str, timeout: float) -> dict[str, Any] | None:
    try:
        raw = http_get(HF_PAPERS_API.format(arxiv_id), timeout=timeout, retries=2,
                       accept="application/json")
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (RuntimeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    artifacts = (
        int(data.get("numTotalModels") or 0)
        + int(data.get("numTotalDatasets") or 0)
        + int(data.get("numTotalSpaces") or 0)
    )
    return {
        "hf_upvotes": int(data.get("upvotes") or 0),
        "hf_linked_artifacts": artifacts,
    }


def _have_gh() -> bool:
    return shutil.which("gh") is not None


def _gh_json(args: list[str], timeout: float = 30.0) -> Any | None:
    try:
        proc = subprocess.run(
            ["gh", "api", "-X", "GET", *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _repo_meta_from_url(url: str) -> dict[str, Any] | None:
    """If a github.com URL is given, fetch repo metadata via gh."""
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", url)
    if not m:
        return None
    owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2))
    data = _gh_json([f"repos/{owner}/{repo}"])
    if not isinstance(data, dict) or "full_name" not in data:
        return None
    return _shape_repo(data)


def github_repo_search(arxiv_id: str) -> dict[str, Any] | None:
    """Find a repo whose code/README cites this exact arXiv id (high precision).

    Title-based search was removed: for generic titles it matched popular but
    unrelated repos (e.g. an awesome-list), inflating scores with false positives.
    Author-declared links are the primary path; Stage C web-search recovers repos
    that neither declare a link nor cite the arXiv id.
    """
    code = _gh_json(["-H", "Accept: application/vnd.github.text-match+json",
                     "search/code", "-f", f"q={arxiv_id}", "-f", "per_page=1"])
    if isinstance(code, dict) and code.get("items"):
        repo = code["items"][0].get("repository", {})
        if repo.get("full_name"):
            full = _gh_json([f"repos/{repo['full_name']}"])
            if isinstance(full, dict) and full.get("full_name"):
                shaped = _shape_repo(full)
                if AGGREGATOR_RE.search(f"{shaped['full_name']} {shaped['description']}"):
                    return None  # arxiv aggregator/RSS/awesome-list, not the paper's code
                shaped["match"] = "code-search-arxiv-id"
                return shaped
    return None


def _shape_repo(data: dict[str, Any]) -> dict[str, Any]:
    lic = (data.get("license") or {})
    return {
        "full_name": data.get("full_name", ""),
        "html_url": data.get("html_url", ""),
        "stars": int(data.get("stargazers_count") or 0),
        "pushed_at": data.get("pushed_at", ""),
        "language": data.get("language") or "",
        "license_spdx": (lic.get("spdx_id") or "").upper(),
        "size_kb": int(data.get("size") or 0),
        "description": data.get("description") or "",
    }


def _is_recent(pushed_at: str) -> bool:
    if not pushed_at:
        return False
    try:
        pushed = dt.datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age = dt.datetime.now(dt.timezone.utc) - pushed
    return age.days <= RECENT_ACTIVITY_DAYS


# --- paper license / redistributability ------------------------------------
# The arXiv API does not carry the license; the abstract page does, as a link.
PAPER_LICENSE_RE = re.compile(
    r'href="(https?://(?:creativecommons\.org|arxiv\.org/licenses)[^"]*)"', re.IGNORECASE
)


def classify_paper_license(url: str) -> dict[str, Any]:
    """Map an arXiv license URL to (label, redistributable, kind)."""
    u = (url or "").lower()
    if "creativecommons.org/publicdomain/zero" in u:
        return {"label": "CC0-1.0", "redistributable": True, "kind": "public-domain"}
    if "creativecommons.org/licenses/by-nc" in u:
        return {"label": "CC-BY-NC", "redistributable": False, "kind": "non-commercial"}
    if "creativecommons.org/licenses/by-nd" in u:
        return {"label": "CC-BY-ND", "redistributable": True, "kind": "no-derivatives"}
    if "creativecommons.org/licenses/by-sa" in u:
        return {"label": "CC-BY-SA", "redistributable": True, "kind": "share-alike"}
    if "creativecommons.org/licenses/by" in u:
        return {"label": "CC-BY", "redistributable": True, "kind": "attribution"}
    if "arxiv.org/licenses/nonexclusive" in u:
        return {"label": "arXiv-nonexclusive", "redistributable": False, "kind": "arxiv-default"}
    return {"label": "unknown", "redistributable": False, "kind": "unknown"}


def arxiv_license(arxiv_id: str, timeout: float) -> dict[str, Any]:
    """Fetch the paper's license from its arXiv abstract page (best-effort)."""
    try:
        html = http_get(f"https://arxiv.org/abs/{arxiv_id}", timeout=timeout, retries=2).decode(
            "utf-8", errors="replace"
        )
    except RuntimeError:
        return {"label": "unknown", "redistributable": False, "kind": "fetch-failed", "url": ""}
    m = PAPER_LICENSE_RE.search(html)
    url = m.group(1) if m else ""
    info = classify_paper_license(url)
    info["url"] = url
    return info


def classify_reuse(paper_redistributable: bool, paper_kind: str, repo_license_spdx: str) -> str:
    """Combined reuse verdict for using the paper as an APP example.

    ingestable: re-host paper + code. paper-only/code-only: re-host one, link the
    other. reference-only: link + cite + reproduce locally, do not re-host.
    """
    code_ok = (repo_license_spdx or "") in OSI_LICENSE_IDS
    if paper_kind == "non-commercial":
        return "non-commercial"
    if paper_redistributable and code_ok:
        return "ingestable"
    if paper_redistributable:
        return "paper-only"
    if code_ok:
        return "code-only"
    return "reference-only"


# --- Papers with Code (offline archive index) -------------------------------
# Built by build_pwc_index.py from the HF pwc-archive dataset (CC-BY-SA-4.0).
DEFAULT_PWC_DB = "working/find-reproducible-papers/cache/pwc-links.sqlite"


def pwc_lookup(arxiv_id: str, db_path: str | None) -> dict[str, Any] | None:
    """Look up a paper's code repo in the local Papers-with-Code index.

    Returns the official repo if present (else the most-cited-looking first row),
    or None. Stdlib sqlite3 — no network, no rate limit. Snapshot is frozen, so
    recent papers will simply miss.
    """
    if not db_path or not Path(db_path).is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT repo_url, is_official, framework FROM links WHERE arxiv_id=? "
            "ORDER BY is_official DESC", (arxiv_id,)).fetchall()
        conn.close()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    url, is_official, framework = rows[0]
    return {"html_url": url, "is_official": bool(is_official), "framework": framework or "",
            "match": "pwc-archive", "n_links": len(rows)}


def enrich_candidate(cand: dict[str, Any], use_github: bool, hf: bool,
                     timeout: float, paper_license: bool = True,
                     pwc_db: str | None = None) -> dict[str, Any]:
    # Scan title too — it often carries the decisive signal/blocker term
    # (e.g. "... with CUDA ...", "open-source ...").
    text_blob = f"{cand['title']}\n{cand['abstract']}\n{cand['comment']}"
    declared = extract_code_links(cand["abstract"], cand["comment"])
    # Figure/table counts come from the arxiv:comment field, the canonical place
    # authors write "N figures"; scanning the abstract too risks false positives.
    mfig = FIG_RE.search(cand["comment"])
    mtab = TAB_RE.search(cand["comment"])
    signals: dict[str, Any] = {
        "declared_code_links": declared,
        "code_hint": bool(CODE_HINT_RE.search(text_blob)),
        "data_signal": bool(DATA_RE.search(text_blob)),
        "heavy_compute": bool(HEAVY_RE.search(text_blob)),
        "symbolic_tooling": bool(SYMBOLIC_RE.search(text_blob)),
        "theory_signal": bool(THEORY_RE.search(text_blob)),
        "n_figures": int(mfig.group(1)) if mfig else None,
        "n_tables": int(mtab.group(1)) if mtab else None,
        "repo": None,
        "repo_source": None,
        "hf_upvotes": None,
        "hf_linked_artifacts": None,
        "paper_license": None,
    }
    if paper_license:
        signals["paper_license"] = arxiv_license(cand["arxiv_id"], timeout=timeout)
    # Repo metadata: prefer an author-declared github link.
    repo = None
    for link in declared:
        if "github.com" in link.lower():
            repo = _repo_meta_from_url(link) if use_github else None
            if repo is None:
                repo = {"html_url": link, "match": "abstract-link-unfetched"}
            signals["repo_source"] = "author-declared"
            break
    # Papers with Code official repo — high confidence, before the noisier search.
    if repo is None and pwc_db:
        pwc = pwc_lookup(cand["arxiv_id"], pwc_db)
        if pwc and pwc["is_official"]:
            if use_github:
                fetched = _repo_meta_from_url(pwc["html_url"])
                repo = fetched if fetched else pwc
            else:
                repo = pwc
            signals["repo_source"] = "pwc-official"
    if repo is None and use_github:
        repo = github_repo_search(cand["arxiv_id"])
        if repo:
            signals["repo_source"] = "github-search"
    signals["repo"] = repo
    if hf:
        hf_sig = hf_paper_signals(cand["arxiv_id"], timeout=timeout)
        if hf_sig:
            signals.update(hf_sig)
    return signals


# --- scoring -----------------------------------------------------------------
def score_candidate(cand: dict[str, Any], sig: dict[str, Any],
                    weights: dict[str, int]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    red_flags: list[str] = []

    has_declared = (bool(sig.get("declared_code_links"))
                    or sig.get("repo_source") in ("author-declared", "pwc-official"))
    has_search_repo = sig.get("repo_source") == "github-search"
    if has_declared:
        score += weights["author_declared_repo"]
        reasons.append("official repo (Papers with Code)" if sig.get("repo_source") == "pwc-official"
                       else "author-declared code link")
    elif has_search_repo:
        score += weights["repo_found_via_search"]
        reasons.append("plausible repo via GitHub search (unconfirmed)")
    else:
        red_flags.append("no public code located")

    repo = sig.get("repo") or {}
    if repo.get("license_spdx") in OSI_LICENSE_IDS:
        score += weights["osi_license"]
        reasons.append(f"OSI license ({repo['license_spdx']})")
    elif repo.get("full_name") and not repo.get("license_spdx"):
        red_flags.append("repo has no detected license")
    if repo.get("pushed_at") and _is_recent(repo["pushed_at"]):
        score += weights["recent_activity"]
        reasons.append("repo recently active")

    if sig.get("data_signal"):
        score += weights["data_signal"]
        reasons.append("data/availability mentioned")
    if sig.get("code_hint"):
        score += weights["code_hint_in_abstract"]
        reasons.append("abstract/comment claims code available / reproducible")
    if sig.get("n_figures"):
        score += weights["figures_present"]
        reasons.append(f"comment lists {sig['n_figures']} figures (concrete targets)")
    if sig.get("hf_linked_artifacts"):
        score += weights["hf_artifacts"]
        reasons.append(f"{sig['hf_linked_artifacts']} HF artifacts")
    if sig.get("symbolic_tooling"):
        score += weights["symbolic_tooling"]
        reasons.append("symbolic/CAS tooling (derivation-checkable)")
    if sig.get("theory_signal"):
        score += weights["theory_signal"]
        reasons.append("analytic/derivation paper (assess via derivation checks)")

    if sig.get("heavy_compute"):
        score += weights["heavy_compute_penalty"]
        red_flags.append("needs GPU/large-scale compute — not reproducible on a MacBook")

    score = max(0, min(100, score))
    if score >= TIER_A_MIN:
        tier = "A-strong"
    elif score >= TIER_B_MIN:
        tier = "B-promising"
    else:
        tier = "C-weak"
    # The target machine is a MacBook with no GPU. A paper that needs GPU/CUDA or
    # large-scale compute cannot be demoed here, so it is never a shortlist
    # candidate regardless of how good its repo is — cap the tier (keep the score).
    if sig.get("heavy_compute"):
        tier = "C-weak"

    # Reuse / redistributability verdict (orthogonal to the reproducibility score).
    pl = sig.get("paper_license") or {}
    reuse = classify_reuse(bool(pl.get("redistributable")), pl.get("kind", ""),
                           (sig.get("repo") or {}).get("license_spdx", ""))
    if reuse == "reference-only":
        red_flags.append(f"reference-only (paper license: {pl.get('label', 'unknown')}) — cannot re-host")
    elif reuse == "non-commercial":
        red_flags.append("paper license is non-commercial (CC-BY-NC)")
    return {"score": score, "tier": tier, "reasons": reasons, "red_flags": red_flags, "reuse": reuse}


# --- reporting ---------------------------------------------------------------
def _short(text: str, n: int) -> str:
    text = text.replace("|", "\\|")
    return text if len(text) <= n else text[: n - 1] + "…"


def build_report(criteria: dict[str, Any], rows: list[dict[str, Any]],
                 shortlist: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Reproducibility screening report\n")
    lines.append(f"- Generated: {iso_now()}")
    lines.append(f"- Candidates gathered: {len(rows)}")
    lines.append(f"- Shortlist (diversity-aware tier A/B, capped at "
                 f"{criteria['shortlist_size']}; plus any --include): {len(shortlist)}")
    lines.append(f"- arXiv query: `{criteria['search_query']}`")
    gh = "on" if criteria["use_github"] else "off"
    lines.append(f"- GitHub enrichment: {gh}; Hugging Face: {'on' if criteria['use_hf'] else 'off'}\n")
    lines.append(
        "> **This is a triage prior, not a reproducibility verdict.** The score "
        "ranks which papers are worth a real reproduction attempt. Verified "
        "reproducibility comes from Stage C (see SKILL.md): actually loading the "
        "paper, setting up the environment, and reproducing a figure/result, "
        "recorded with reproduce-results statuses.\n"
    )
    lines.append("## Ranked candidates\n")
    lines.append("| # | Score | Tier | arXiv | Title | Cat | Code | License | Flags |")
    lines.append("|---|-------|------|-------|-------|-----|------|---------|-------|")
    for i, r in enumerate(rows, 1):
        repo = (r["signals"].get("repo") or {})
        code = best_code_link(r["signals"], default="")
        code_cell = f"[link]({code})" if code else "—"
        lic = repo.get("license_spdx") or "—"
        flags = "; ".join(r["score"]["red_flags"]) or "—"
        lines.append(
            f"| {i} | {r['score']['score']} | {r['score']['tier']} | "
            f"[{r['cand']['arxiv_id']}]({r['cand']['abs_url']}) | "
            f"{_short(r['cand']['title'], 60)} | {r['cand']['primary_category']} | "
            f"{code_cell} | {lic} | {_short(flags, 40)} |"
        )
    lines.append("\n## Shortlist details (deep-assess these next)\n")
    if not shortlist:
        lines.append("_No tier-A/B candidates. Loosen criteria or widen the date window._\n")
    for r in shortlist:
        c, s, sc = r["cand"], r["signals"], r["score"]
        repo = s.get("repo") or {}
        lines.append(f"### {c['arxiv_id']} — {c['title']}")
        lines.append(f"- **Score / tier:** {sc['score']} / {sc['tier']}")
        pl = (s.get("paper_license") or {})
        lines.append(f"- **Reuse:** {sc.get('reuse', 'unknown')}  (paper license: {pl.get('label', 'unknown')})")
        lines.append(f"- **arXiv:** {c['abs_url']}  ({c['primary_category']}; {', '.join(c['categories'])})")
        lines.append(f"- **Authors:** {', '.join(c['authors'][:6])}{' et al.' if len(c['authors']) > 6 else ''}")
        url = best_code_link(s)
        if url:
            extra = []
            if repo.get("stars") is not None and repo.get("full_name"):
                extra.append(f"{repo['stars']}★")
            if repo.get("language"):
                extra.append(repo["language"])
            if repo.get("license_spdx"):
                extra.append(repo["license_spdx"])
            if repo.get("pushed_at"):
                extra.append(f"pushed {repo['pushed_at'][:10]}")
            src = s.get("repo_source") or "abstract"
            label = "Code (UNCONFIRMED — verify in Stage C)" if src == "github-search" else "Code"
            lines.append(f"- **{label}:** {url}  ({src}{('; ' + ', '.join(extra)) if extra else ''})")
        else:
            lines.append("- **Code:** none located automatically (Stage C should web-search)")
        lines.append(f"- **Why prioritised:** {', '.join(sc['reasons']) or 'minimal signals'}")
        if sc["red_flags"]:
            lines.append(f"- **Red flags:** {', '.join(sc['red_flags'])}")
        figs = s.get("n_figures")
        lines.append(f"- **Figures (from comment):** {figs if figs is not None else 'unknown'}")
        lines.append(f"- **Abstract:** {_short(c['abstract'], 400)}")
        lines.append("")
    return "\n".join(lines) + "\n"


# --- shortlist selection -----------------------------------------------------
SCORE_DISCLAIMER = (
    "score/tier are a Stage-B triage PRIOR from cheap metadata signals, NOT "
    "verified reproducibility. Verification is Stage C (see SKILL.md)."
)


def _domain_key(primary_category: str) -> str:
    """Coarse physics-vs-ML bucket so the shortlist can stay domain-diverse."""
    cat = (primary_category or "").lower()
    if cat.startswith(("cs.", "stat.")):
        return "ml"
    if cat.startswith((
        "quant-ph", "cond-mat", "math-ph", "physics", "hep-", "gr-qc",
        "nucl-", "astro-ph", "nlin", "math.",
    )):
        return "physics"
    return "other"


def _code_confirmed(signals: dict[str, Any]) -> bool:
    """True only when the code link came from the paper itself (author-declared)."""
    return signals.get("repo_source") in ("author-declared", "pwc-official")


def best_code_link(signals: dict[str, Any], default: str | None = None) -> str | None:
    """The best code URL for a candidate: enriched repo URL, else first declared link."""
    repo_url = (signals.get("repo") or {}).get("html_url")
    declared = signals.get("declared_code_links") or []
    return repo_url or (declared[0] if declared else default)


def diversify_shortlist(rows: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Round-robin the tier-A/B rows across domain buckets, best-score-first.

    A pure top-N by score lets a strong ML run crowd out every physics paper.
    Round-robin guarantees representation while still leading with the overall
    best; within a bucket we keep score order, and buckets are visited in order
    of their own top score.
    """
    eligible = [r for r in rows if r["score"]["tier"] in ("A-strong", "B-promising")]
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in eligible:
        buckets.setdefault(_domain_key(r["cand"]["primary_category"]), []).append(r)
    for b in buckets.values():
        b.sort(key=lambda r: r["score"]["score"], reverse=True)
    order = sorted(buckets, key=lambda k: buckets[k][0]["score"]["score"], reverse=True)
    chosen: list[dict[str, Any]] = []
    idx = 0
    while len(chosen) < size and any(buckets[k] for k in order):
        b = buckets[order[idx % len(order)]]
        if b:
            chosen.append(b.pop(0))
        idx += 1
    return chosen


# --- main --------------------------------------------------------------------
def resolve_criteria(args: argparse.Namespace) -> dict[str, Any]:
    preset = PRESETS.get(args.preset, PRESETS[DEFAULT_PRESET])
    crit: dict[str, Any] = {
        "categories": list(preset["categories"]),
        "keywords": list(preset["keywords"]),
        "keyword_mode": preset["keyword_mode"],
        "exclude": [],
        "from_date": None,
        "to_date": None,
        "max_candidates": args.max_candidates,
        "shortlist_size": args.shortlist_size,
        "require_code_hint": args.require_code_hint,
        "sort_by": args.sort_by,
        "sort_order": args.sort_order,
        "weights": dict(DEFAULT_WEIGHTS),
        "preset": args.preset,
    }
    if args.criteria_file:
        loaded = json.loads(Path(args.criteria_file).read_text(encoding="utf-8"))
        for k, v in loaded.items():
            if k == "weights":
                if isinstance(v, dict):
                    crit["weights"].update(v)
                else:
                    eprint("[warn] criteria-file 'weights' is not an object; ignoring it.")
                continue
            crit[k] = v
    # CLI flags override everything.
    if args.categories:
        crit["categories"] = [c.strip() for c in args.categories.split(",") if c.strip()]
    if args.keywords:
        crit["keywords"] = [k.strip() for k in re.split(r"[;,]", args.keywords) if k.strip()]
    if args.keyword_mode:
        crit["keyword_mode"] = args.keyword_mode
    if args.exclude:
        crit["exclude"] = [e.strip() for e in args.exclude.split(",") if e.strip()]
    if args.from_date:
        crit["from_date"] = args.from_date
    if args.to_date:
        crit["to_date"] = args.to_date
    return crit


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preset", default=DEFAULT_PRESET, choices=sorted(PRESETS),
                   help=f"Domain preset (default: {DEFAULT_PRESET}).")
    p.add_argument("--categories", help="Comma-separated arXiv categories (overrides preset).")
    p.add_argument("--keywords", help="Topic keywords, ';' or ',' separated (overrides preset).")
    p.add_argument("--keyword-mode", dest="keyword_mode", choices=["OR", "AND"],
                   help="Combine keywords with OR (default) or AND.")
    p.add_argument("--exclude", help="Comma-separated terms to exclude (ANDNOT all:term).")
    p.add_argument("--from-date", dest="from_date", help="Earliest submission date YYYY-MM-DD.")
    p.add_argument("--to-date", dest="to_date", help="Latest submission date YYYY-MM-DD.")
    p.add_argument("--max-candidates", dest="max_candidates", type=int, default=60,
                   help="Max candidates to gather (default 60).")
    p.add_argument("--shortlist-size", dest="shortlist_size", type=int, default=5,
                   help="Max tier-A/B papers to put on the shortlist (default 5).")
    p.add_argument("--include", dest="include",
                   help="Comma-separated arXiv IDs to force onto the shortlist "
                        "regardless of tier (e.g. a theory paper you know has code).")
    p.add_argument("--sort-by", dest="sort_by", default="submittedDate",
                   choices=["relevance", "submittedDate", "lastUpdatedDate"],
                   help="arXiv sort field (default submittedDate).")
    p.add_argument("--sort-order", dest="sort_order", default="descending",
                   choices=["ascending", "descending"])
    p.add_argument("--require-code-hint", dest="require_code_hint", action="store_true",
                   help="Drop candidates with no code link/hint before scoring.")
    p.add_argument("--use-github", dest="use_github", action="store_true",
                   help="Enrich repos via the gh CLI (license, stars, recency).")
    p.add_argument("--no-hf", dest="use_hf", action="store_false",
                   help="Skip Hugging Face Papers enrichment.")
    p.add_argument("--no-paper-license", dest="paper_license", action="store_false",
                   help="Skip fetching each paper's arXiv license (one GET/candidate).")
    p.add_argument("--require-redistributable", dest="require_redistributable", action="store_true",
                   help="Keep only papers whose arXiv license permits re-hosting (CC-BY/SA/CC0/ND).")
    p.add_argument("--pwc-index", dest="pwc_index", default=DEFAULT_PWC_DB,
                   help=f"Papers-with-Code sqlite index for official-repo lookup (default {DEFAULT_PWC_DB}; "
                        "build with build_pwc_index.py). Ignored if missing.")
    p.add_argument("--no-pwc", dest="use_pwc", action="store_false",
                   help="Disable the Papers-with-Code index lookup.")
    p.add_argument("--criteria-file", dest="criteria_file",
                   help="JSON file with criteria/weights (CLI flags override it).")
    p.add_argument("--timeout", type=float, default=45.0, help="Per-request timeout seconds.")
    p.add_argument("--out-root", dest="out_root",
                   default="working/find-reproducible-papers",
                   help="Output root (a timestamped subfolder is created).")
    p.add_argument("--timestamp", help="Override run timestamp (default: now).")
    args = p.parse_args(argv)

    if args.use_github and not _have_gh():
        eprint("[warn] --use-github set but `gh` not found on PATH; continuing without it.")
        args.use_github = False

    crit = resolve_criteria(args)
    try:
        query = build_search_query(crit["categories"], crit["keywords"], crit["keyword_mode"],
                                   crit["exclude"], crit["from_date"], crit["to_date"])
    except ValueError as err:
        eprint(f"[error] {err}")
        return 2
    crit["search_query"] = query
    crit["use_github"] = args.use_github
    crit["use_hf"] = args.use_hf
    crit["require_redistributable"] = args.require_redistributable
    crit["paper_license_lookup"] = args.paper_license
    pwc_db = args.pwc_index if args.use_pwc else None
    crit["pwc_index"] = pwc_db if (pwc_db and Path(pwc_db).is_file()) else None
    if pwc_db and not Path(pwc_db).is_file():
        eprint(f"[warn] PwC index not found at {pwc_db}; continuing without it (build_pwc_index.py).")

    stamp = args.timestamp or now_stamp()
    out_dir = Path(args.out_root) / stamp
    if out_dir.exists():
        eprint(f"[error] {out_dir} already exists; pass a fresh --timestamp.")
        return 2
    out_dir.mkdir(parents=True)

    crit["generated"] = iso_now()
    crit["_note"] = SCORE_DISCLAIMER
    write_text(out_dir / "criteria.json", json.dumps(crit, indent=2, ensure_ascii=False) + "\n")

    eprint(f"[gather] query: {query}")
    cands = arxiv_search(query, crit["max_candidates"], crit["sort_by"],
                         crit["sort_order"], timeout=args.timeout)
    eprint(f"[gather] {len(cands)} candidates")
    write_jsonl(out_dir / "candidates.jsonl", cands)
    if not cands:
        eprint("[done] No candidates gathered (often an arXiv-API network block here). "
               "criteria.json was still written.")
        return 1

    rows: list[dict[str, Any]] = []
    for i, cand in enumerate(cands, 1):
        eprint(f"[screen] {i}/{len(cands)} {cand['arxiv_id']}")
        sig = enrich_candidate(cand, use_github=args.use_github, hf=args.use_hf,
                               timeout=args.timeout, paper_license=args.paper_license,
                               pwc_db=crit["pwc_index"])
        if crit["require_code_hint"] and not (sig["declared_code_links"]
                                              or sig["code_hint"] or sig.get("repo")):
            continue
        if args.require_redistributable and not (sig.get("paper_license") or {}).get("redistributable"):
            continue
        sc = score_candidate(cand, sig, crit["weights"])
        rows.append({"cand": cand, "signals": sig, "score": sc})

    rows.sort(key=lambda r: r["score"]["score"], reverse=True)
    write_jsonl(out_dir / "screening.jsonl",
                [{"arxiv_id": r["cand"]["arxiv_id"], **r["score"],
                  "score_kind": "screening_prior_not_verdict",
                  "signals": r["signals"], "title": r["cand"]["title"],
                  "abs_url": r["cand"]["abs_url"]} for r in rows])

    # Diversity-aware shortlist (keeps a physics+ML mix), then force-include any
    # operator-requested IDs regardless of tier.
    shortlist = diversify_shortlist(rows, crit["shortlist_size"])
    include_ids = {i.strip() for i in (args.include or "").split(",") if i.strip()}
    if include_ids:
        in_short = {r["cand"]["arxiv_id"] for r in shortlist}
        by_id = {r["cand"]["arxiv_id"]: r for r in rows}
        for arx in include_ids:
            if arx in by_id and arx not in in_short:
                shortlist.append(by_id[arx])
            elif arx not in by_id:
                eprint(f"[warn] --include {arx} not among gathered candidates; skipped.")

    write_text(out_dir / "shortlist.json", json.dumps(
        {"_note": SCORE_DISCLAIMER,
         "papers": [
            {"arxiv_id": r["cand"]["arxiv_id"], "title": r["cand"]["title"],
             "abs_url": r["cand"]["abs_url"], "score": r["score"]["score"],
             "score_kind": "screening_prior_not_verdict",
             "tier": r["score"]["tier"],
             "code": best_code_link(r["signals"]),
             "code_confirmed": _code_confirmed(r["signals"]),
             "primary_category": r["cand"]["primary_category"],
             "paper_license": (r["signals"].get("paper_license") or {}).get("label"),
             "reuse": r["score"].get("reuse"),
             "reasons": r["score"]["reasons"], "red_flags": r["score"]["red_flags"]}
            for r in shortlist]},
        indent=2, ensure_ascii=False) + "\n")

    write_text(out_dir / "screening-report.md", build_report(crit, rows, shortlist))

    eprint(f"\n[done] {len(rows)} screened, {len(shortlist)} shortlisted.")
    eprint(f"[done] Report:    {out_dir / 'screening-report.md'}")
    eprint(f"[done] Shortlist: {out_dir / 'shortlist.json'}")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
