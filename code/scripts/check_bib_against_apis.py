#!/usr/bin/env python3
"""Check every entry in paper/refs.bib against authoritative APIs.

- Entries with an ``eprint`` field are checked against the arXiv API
  (title, author family names, v1 year). arXiv is treated as the citation
  basis for the evaluation-set papers, whose arXiv versions were used in
  the study. A ``doi`` on such entries is additionally resolved via
  Crossref to confirm it is real and titled consistently.
- Entries with only a ``doi`` are checked against the Crossref API
  (title, year, volume, pages, author family names).
- Web-only @misc entries get a URL liveness check.
- Books and other offline entries are listed for manual review.

Usage: python3 code/scripts/check_bib_against_apis.py [path/to/refs.bib]
"""

import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

BIB_PATH = sys.argv[1] if len(sys.argv) > 1 else "paper/refs.bib"
UA = {"User-Agent": "app-paper-bib-check/1.0 (mailto:sirui.lu.thu@gmail.com)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_bib(path):
    text = open(path).read()
    entries = []
    for m in re.finditer(r"@(\w+)\{([^,]+),", text):
        start = m.end()
        depth = 1
        i = start
        while depth and i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start : i - 1]
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", body):
            fields[fm.group(1).lower()] = fm.group(2)
        entries.append((m.group(1).lower(), m.group(2).strip(), fields))
    return entries


def norm(s):
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s or "")
    s = s.replace("{", "").replace("}", "").replace("~", " ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def name_ok(bib_fam, api_fams, i):
    """Accept exact match anywhere, or containment (compound/institutional names)."""
    if bib_fam in api_fams:
        return True
    cand = api_fams[i] if i < len(api_fams) else ""
    return bool(cand) and (bib_fam.endswith(cand) or cand.endswith(bib_fam)
                           or bib_fam in cand or cand in bib_fam)


def title_match(a, b):
    na, nb = norm(a), re.sub(r"\s+", " ", norm(b))
    na = re.sub(r"\s+", " ", na)
    return difflib.SequenceMatcher(None, na, nb).ratio()


def family_names(bib_author):
    names = []
    for part in re.split(r"\s+and\s+", bib_author or ""):
        part = part.strip()
        if not part or norm(part) in ("others", "editorial"):
            continue
        if part.startswith("{") and part.endswith("}"):
            names.append(norm(part))
        elif "," in part:
            names.append(norm(part.split(",")[0]))
        else:
            names.append(norm(part.split()[-1]))
    return names


def check_crossref(key, fields, problems, infos):
    doi = fields["doi"]
    try:
        msg = json.loads(fetch(f"https://api.crossref.org/works/{doi}"))["message"]
    except Exception as e:
        problems.append(f"{key}: DOI {doi} failed to resolve via Crossref ({e})")
        return
    cr_title = (msg.get("title") or [""])[0]
    r = title_match(fields.get("title", ""), cr_title)
    if r < 0.85:
        problems.append(f"{key}: title mismatch vs Crossref (ratio {r:.2f}): '{cr_title}'")
    issued = (msg.get("issued", {}).get("date-parts") or [[None]])[0][0]
    if "year" in fields and issued and str(issued) != fields["year"]:
        infos.append(f"{key}: year {fields['year']} vs Crossref issued {issued}")
    if "volume" in fields and msg.get("volume") and fields["volume"] != msg["volume"]:
        problems.append(f"{key}: volume {fields['volume']} vs Crossref {msg['volume']}")
    if "pages" in fields and msg.get("page"):
        if norm(fields["pages"].replace("--", "-")) != norm(msg["page"]):
            infos.append(f"{key}: pages '{fields['pages']}' vs Crossref '{msg['page']}'")
    cr_fams = [norm(a.get("family", "")) for a in msg.get("author", [])]
    bib_fams = family_names(fields.get("author", ""))
    for i, fam in enumerate(bib_fams):
        if i < len(cr_fams) and not name_ok(fam, cr_fams, i):
            problems.append(f"{key}: author {i+1} '{fam}' vs Crossref '{cr_fams[i] if i < len(cr_fams) else '?'}'")
    if cr_fams and not fields.get("author") and norm(fields.get("author", "")) != "editorial":
        infos.append(f"{key}: Crossref lists authors but entry has none")


def check_arxiv(key, fields, problems, infos):
    eid = fields["eprint"]
    try:
        xml = fetch(f"https://export.arxiv.org/api/query?id_list={eid}")
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = ET.fromstring(xml).find("a:entry", ns)
        ax_title = entry.find("a:title", ns).text
        ax_authors = [e.find("a:name", ns).text for e in entry.findall("a:author", ns)]
        ax_year = entry.find("a:published", ns).text[:4]
    except Exception as e:
        problems.append(f"{key}: arXiv {eid} lookup failed ({e})")
        return
    if "could not be found" in (ax_title or ""):
        problems.append(f"{key}: arXiv id {eid} not found")
        return
    r = title_match(fields.get("title", ""), ax_title)
    if r < 0.85:
        problems.append(f"{key}: title mismatch vs arXiv (ratio {r:.2f}): '{ax_title.strip()}'")
    bib_fams = family_names(fields.get("author", ""))
    ax_fams = [norm(n.split()[-1]) for n in ax_authors]
    if len(bib_fams) != len(ax_fams) and "others" not in norm(fields.get("author", "")):
        infos.append(f"{key}: {len(bib_fams)} authors in bib vs {len(ax_fams)} on arXiv")
    for i, fam in enumerate(bib_fams):
        if i < len(ax_fams) and not name_ok(fam, ax_fams, i):
            problems.append(f"{key}: author {i+1} '{fam}' vs arXiv '{ax_fams[i]}'")
    if "year" in fields and fields["year"] != ax_year:
        infos.append(f"{key}: year {fields['year']} vs arXiv v1 year {ax_year} (ok if citing a published/later version)")


def check_url(key, fields, problems, infos):
    url = fields.get("url") or re.sub(r"\\url\{(.*)\}", r"\1", fields.get("howpublished", ""))
    if not url.startswith("http"):
        infos.append(f"{key}: no URL to check (manual review)")
        return
    try:
        req = urllib.request.Request(url, headers=UA, method="GET")
        with urllib.request.urlopen(req, timeout=30) as r:
            infos.append(f"{key}: URL ok ({r.status})")
    except Exception as e:
        code = getattr(e, "code", None)
        if code in (301, 302, 403):
            infos.append(f"{key}: URL returned {code} (likely bot-blocked or redirect; manual ok)")
        else:
            problems.append(f"{key}: URL check failed: {url} ({e})")


def main():
    entries = parse_bib(BIB_PATH)
    problems, infos = [], []
    print(f"Checking {len(entries)} entries in {BIB_PATH}\n")
    for etype, key, fields in entries:
        time.sleep(0.4)
        if "eprint" in fields:
            check_arxiv(key, fields, problems, infos)
            if "doi" in fields and not fields["doi"].startswith("10.48550"):
                check_crossref(key, fields, problems, infos)
            print(f"  [arXiv]    {key}")
        elif "doi" in fields:
            check_crossref(key, fields, problems, infos)
            print(f"  [Crossref] {key}")
        elif "url" in fields or "howpublished" in fields:
            check_url(key, fields, problems, infos)
            print(f"  [URL]      {key}")
        else:
            infos.append(f"{key}: offline entry ({etype}), manual review")
            print(f"  [manual]   {key}")
    print("\n=== PROBLEMS ===" if problems else "\n=== NO PROBLEMS ===")
    for p in problems:
        print("  !!", p)
    print("\n=== NOTES ===")
    for n in infos:
        print("  --", n)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
