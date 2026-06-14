---
name: find-reproducible-papers
description: Find candidate example papers for the APP protocol paper. Selects arXiv papers by topic/date, screens them cheaply for reproducibility readiness, then deep-assesses a shortlist by loading each paper and reproducing one key result. Outputs an evidence-backed recommendation; a human picks the final examples.
---

# Find Reproducible Papers

Use this dev skill to build a curated set of real arXiv papers that are
**reproducible enough to serve as examples in the APP protocol paper**
(`paper/app-paper.tex`, the "Example" section of `paper/outline-of-app-paper.md`).
The protocol paper wants one or two worked examples that demonstrate the full
publishing workflow (`reproduce-results` → `prepare-staging` → `define-paper-agent`
→ `validate-publication`) and the reader paper-agent experience. A good example
must be something an agent can actually load, set up, and reproduce **on the
author's MacBook** (Apple Silicon, CPU/MPS, no CUDA/GPU, modest RAM) — so
GPU-dependent or large-scale-compute work is disqualified, however clean its repo.

This skill finds and triages candidates and gathers evidence; it does **not**
publish anything or decide which examples go into the paper — the human decides.

## Tiered approach

Reproducibility is checked in three stages, cheapest first, so we never run code
on papers that obviously will not work:

1. **Select (Stage A)** — query the arXiv API by criteria (categories, keywords,
   date window). Deterministic, in the runner.
2. **Screen (Stage B)** — for every candidate, collect *cheap* availability
   signals without running any code (author-declared code link, GitHub repo
   metadata, Hugging Face linked artifacts, data/figure/compute hints) and score
   a transparent triage prior. Deterministic, in the runner.
3. **Deep-assess (Stage C)** — for the shortlist only, actually load each paper,
   set up its environment, and attempt to reproduce **one** key figure/result,
   recording the protocol's `reproduce-results` statuses. Agent-driven, per the
   instructions below.

**The Stage A/B score is a prior, not a verdict.** Only Stage C verifies that a
paper reproduces. Never describe a paper as "reproducible" on the strength of the
screening score alone.

## Stages A & B: the runner

Prefer the bundled runner:

```text
skills/find-reproducible-papers/scripts/find_reproducible_papers.py [options]
```

It is stdlib-only, executes no paper code, and only reads metadata. GitHub
enrichment is optional and uses the `gh` CLI when available.

### Selecting candidates (criteria)

The default `--preset project` matches the existing `data/example-papers/` papers:
quantum physics, condensed matter, math-ph, and ML. Other presets: `quant-ph`,
`cond-mat`, `ml-interp`. Everything is overridable:

```text
--preset {project,quant-ph,cond-mat,ml-interp}
--categories cond-mat.str-el,quant-ph     # arXiv categories (OR'd)
--keywords "tensor network; matrix product state"   # ';' or ',' separated topic terms
--keyword-mode {OR,AND}
--exclude review,survey                    # ANDNOT all:term
--from-date 2024-01-01 --to-date 2025-06-01
--sort-by {submittedDate,lastUpdatedDate,relevance}
--max-candidates 60
--criteria-file criteria.json             # reproducible run record (CLI flags override it)
```

Selection criteria should be about **topic and recency**, not reproducibility —
reproducibility is what the screen and deep-assess stages measure. Keep the topic
close to the project's domains so the resulting examples resemble the existing
test papers, unless the user asks to branch out.

In practice a blind newest-papers sweep surfaces almost no candidates: very few
abstracts declare a code link, especially in physics. To find candidates
efficiently, **bias the query toward code-advertising papers** and require a code
hint, e.g.:

```text
--keywords "open source; code available; publicly available; github" \
  --keyword-mode OR --require-code-hint --use-github --from-date 2024-06-01
```

This raised the author-declared hit rate from ~5% (blind sweep) to ~30% in
testing. Older papers (a year+) are also more likely to have a released, indexed
repo than today's submissions.

### Screening flags

```text
--use-github               # enrich the located repo via gh (license, stars, recency); off by default
--no-hf                    # skip Hugging Face Papers enrichment
--require-code-hint        # drop candidates with no code link/hint before scoring
--no-paper-license         # skip the per-paper arXiv license fetch (one GET/candidate)
--require-redistributable  # keep only papers whose arXiv license permits re-hosting
--shortlist-size 5         # max tier-A/B papers to carry into Stage C
--timeout 45
```

Run `--use-github` when you want license/recency/stars to count toward the score;
without it, the score relies on author-declared links and abstract/comment hints.

### License / reuse gate (copyright)

For each candidate the runner fetches the paper's **arXiv license** (from the abstract
page; the API does not carry it) and combines it with the repo license into a `reuse`
verdict, surfaced in `screening.jsonl`, `shortlist.json`, and the report:

| `reuse` | Meaning | OK to do |
|---------|---------|----------|
| `ingestable` | paper redistributable (CC-BY/SA/CC0) **and** code OSI-permissive | re-host paper + code (with attribution) |
| `paper-only` / `code-only` | only one side is redistributable | re-host that side, link the other |
| `reference-only` | neither (e.g. arXiv-default "non-exclusive" license, no code license) | **link + cite + reproduce locally; do NOT re-host** |
| `non-commercial` | paper is CC-BY-NC | non-commercial use only |

Citing and linking any paper is always fine; **re-hosting** a paper's source/PDF needs a
redistributable license (the arXiv-default license does not grant it). `--require-redistributable`
filters to re-hostable papers. This is the gate to apply before adding any found paper as a
committed example (see Guardrails).

### Scoring rubric (triage prior, documented)

Each signal adds points (negative for red flags); the total maps to a tier. The
weights live in `DEFAULT_WEIGHTS` in the runner and are echoed into `criteria.json`
so each run is reproducible and tunable via `--criteria-file`.

| Signal | Points | Meaning |
|--------|--------|---------|
| Author-declared code link | +40 | github/gitlab/zenodo/etc. URL in abstract or comment (high confidence) |
| Repo cites the arXiv id | +20 | repo whose code/README cites this arXiv id (`gh` code-search), **unconfirmed** (used only if no declared link) |
| OSI license on repo | +12 | recognised open license (needs `--use-github`) |
| Recent repo activity | +10 | pushed within ~2 years (needs `--use-github`) |
| Data/availability mentioned | +10 | "data available", zenodo/figshare, dataset/benchmark (data artifacts only) |
| Explicit code/repro statement | +8 | "code is available", "open-source", "reproducible" |
| Symbolic / CAS tooling | +8 | Mathematica/Sage/Lean/`.nb`/`.wl` etc. — a notebook is reproducible code |
| Analytic / derivation language | +6 | theorem/proof/closed-form — flags theory papers (verify by derivation checks) |
| Figures present | +6 | comment lists figures (concrete targets) |
| Hugging Face artifacts | +6 | linked models/datasets/spaces |
| Not-laptop compute | −15 **and caps tier at C** | GPU/CUDA, pre-training, foundation models, **or** physics scale (large bond dimension, many-core, large-RAM, large ED) — can't run on a MacBook, so never shortlisted regardless of repo quality |

Tiers: **A-strong** (≥60, worth a real reproduction attempt), **B-promising**
(≥35, public code located with gaps), **C-weak** (<35). A public author repo is
the dominant signal; a declared repo alone reaches tier B and a repo plus a couple
of positives reaches tier A. Red flags (no code located, no license, heavy compute)
are surfaced even when the score is otherwise high.

Two biases to keep in mind, both handled downstream rather than by inflating the prior:

- **Tier C means "no code signal found", not "no code exists."** A genuinely
  reproducible paper whose repo is only discoverable by web search (no link in the
  abstract, default run without `--use-github`) lands in tier C. Run `--use-github`
  to add the +20 search credit, and use `--include <arxiv-id>` to force a known-good
  paper onto the shortlist regardless of tier.
- **The default prior mildly favours ML.** Hugging Face artifacts (+6) are
  effectively ML-only, and the figures signal depends on the optional arXiv comment
  field, so an ML-heavy ranked top is expected — it does **not** mean physics papers
  are less reproducible. The shortlist is therefore built **diversity-aware**
  (physics and ML buckets are interleaved, best-score-first) rather than as a pure
  top-N, so a strong physics candidate survives when one exists.

### Stage A/B outputs

```text
working/find-reproducible-papers/<timestamp>/
  criteria.json          # resolved criteria + weights + arXiv query (run record)
  candidates.jsonl       # every gathered candidate with raw arXiv metadata
  screening.jsonl        # per-candidate signals + score + tier + red flags
  screening-report.md    # ranked table + shortlist details (read this first)
  shortlist.json         # { "_note": ..., "papers": [...] } to deep-assess in Stage C
```

Every machine-readable artifact carries the honesty caveat in-band: `criteria.json`
and `shortlist.json` have a top-level `_note`, and each scored record carries
`score_kind: "screening_prior_not_verdict"`. Each shortlist paper also has a
`code_confirmed` boolean (true only for author-declared links; GitHub-search hits
are `false` and must be confirmed in Stage C).

If `candidates.jsonl` is empty, the arXiv API was unreachable (a known block in
some sandboxes). The endpoint is `http://export.arxiv.org/api/query`; confirm
network/proxy access to `export.arxiv.org` and rerun. `criteria.json` is still
written so the intended query is recorded.

## Automated topic scouting (`scout_topic.py`)

To find a batch of example candidates from just a topic, use the driver:

```text
skills/find-reproducible-papers/scripts/scout_topic.py --topic "condensed matter physics" --until 10 --use-github
```

It maps the topic to arXiv categories/keywords, then screens candidates lazily —
applying the reproducibility tiers **and** the license gate — accumulating papers
that are usable as examples until `--until N` are found (or `--scan-limit` is hit).
A candidate qualifies when it has public code, reaches tier A/B (so it is not
heavy/GPU-bound), and — unless `--allow-reference-only` — has a redistributable
license. Useful flags: `--keywords`, `--from-date/--to-date`, `--scan-limit`,
`--allow-reference-only`, `--use-github`.

Output (`working/find-reproducible-papers/topic-<slug>-<timestamp>/`): `criteria.json`,
`screening.jsonl`, `topic-shortlist.json` (the N good candidates with `reuse`/license),
and `topic-report.md`. This is the cheap, deterministic front of the pipeline — it runs
**no paper code and spawns no agents**. The intended next step is a Stage-C reproduce-check
on each shortlisted paper, then (for the ones that pass) a `simulate-publication` staging run. The
human reviews the shortlist before any expensive staging.

## Papers with Code index (offline code source)

Papers with Code's API was sunset, but its dataset lives on Hugging Face
(`pwc-archive/links-between-paper-and-code`, CC-BY-SA-4.0). `build_pwc_index.py`
downloads it once (~41 MB) and builds a local `sqlite` index of `arXiv id →
repo` with an `is_official` flag:

```text
pip install pandas pyarrow      # builder only; runtime lookup is stdlib sqlite3
skills/find-reproducible-papers/scripts/build_pwc_index.py
# -> working/find-reproducible-papers/cache/pwc-links.sqlite (gitignored, regenerable)
```

Once built, the screener uses it automatically (`--pwc-index`, `--no-pwc`): an
official PwC repo is a **high-confidence code source** (`repo_source: pwc-official`,
scored like an author-declared link, `code_confirmed: true`), tried before the
noisier GitHub search.

`scout_topic.py --source pwc` inverts discovery: it lists papers that already have
**official code** from the index (title-matched to the topic), then fetches their
arXiv metadata and screens them — so the candidate set comes from PwC rather than
an arXiv search. Good for established, code-bearing examples.

Two caveats: the snapshot is **frozen (~2025)** — papers newer than that are not in
it (so `--source pwc` complements, not replaces, the live arXiv path); and the data
is **CC-BY-SA-4.0** (attribute if you redistribute the index; the built sqlite is a
local cache, not committed). PwC discovery still fetches arXiv metadata for screening
signals, so it is not fully offline (a future option is the `pwc-archive/papers-with-abstracts`
dataset for offline abstracts).

## Stage C: deep reproducibility assessment (agent-driven)

Stage C uses `code/protocol_repo/skills/load-paper` and `reproduce-results`, so before
deep-assessing make sure `code/protocol_repo/` is at the intended revision (for the
default latest-main test run `code/scripts/update-protocol-submodule.sh` once; for a
pinned test, check out that commit first). When deep-assessing several papers in
parallel, sync once before the batch.

For each paper in `shortlist.json` `papers` (default ≤5), verify reproducibility
for real. Keep the cost bounded: reproduce **one** key figure/result per paper,
not the whole paper. You may do these inline, or spawn one subagent per
shortlisted paper for parallelism — each writes its own assessment file.

For each shortlisted paper:

1. **Load the paper.** Use the protocol's `code/protocol_repo/skills/load-paper` (its
   arXiv mode, `load-paper/arxiv.md`, fetches metadata + LaTeX source and searches
   for associated public code). It creates the import at `papers/arxiv-<id>/`; use
   that same root for cloning and the assessment file. Do **not** rely on Papers
   with Code for code discovery — that service was sunset and now redirects to
   Hugging Face; use the author-declared link from screening (note `code_confirmed`
   in `shortlist.json`), the GitHub repo, Hugging Face linked artifacts, and a web
   search instead.
2. **Locate and inspect the code/data.** Confirm the screening's code link is
   real (GitHub-search hits have `code_confirmed: false` and must be verified).
   Clone the repo into `papers/arxiv-<id>/code/external/`. Read `README`,
   environment files, scripts/notebooks, and any data-availability notes. Identify
   the most tractable key figure or numerical result to target. **For a
   theory/analytic paper** (theorem/proof/derivation, often with Mathematica, Sage,
   Lean, or GAP scripts), target a key derivation/identity instead of a figure, per
   `code/protocol_repo/skills/reproduce-results/paper-types.md` (Theory-only path) — the
   `data/example-papers/modular-tensor-category` example is the template.
3. **Set up the environment.** Follow the project's safe-install posture: attempt
   safe, project-scoped installs (e.g. into a venv under the run sandbox); ask
   before risky, global, proprietary, credentialed, or very large installs.
   **Estimate runtime and peak memory first** from the README/config/scripts
   (bond dimension, lattice/system size, core count, RAM, training time) and check
   for **GPU/CUDA dependence** — the target is a MacBook (Apple Silicon, CPU/MPS,
   no GPU, modest RAM). Absence of a screening red flag does **not** imply light
   compute. If the work needs a GPU or exceeds the MacBook's budget, record
   `blocked-heavy-compute` instead of attempting the run.
4. **Attempt to reproduce one key figure/result** (or derivation, for theory).
   Run the smallest path that regenerates a real paper figure, headline number, or
   checked identity. Compare to the published value. Record the exact commands,
   outputs, and any diffs.
5. **Record a status** using the protocol's `reproduce-results` vocabulary
   verbatim, so the assessment maps directly onto what `reproduce-results` would
   later capture if the paper becomes an example:

   ```text
   reproduced | runs-but-differs | blocked-missing-data | blocked-heavy-compute
   | blocked-broken-code | blocked-dependency | manual-only
   ```

6. **Assess example fit beyond reproduction.** Judge **scope** (one headline
   result vs. a sprawling multi-task/multi-dataset benchmark) and sketch 2–3
   concrete reader paper-agent questions the paper could support, to confirm a
   meaningful chat is possible. This gives the curation step real evidence for the
   "self-contained scope" and "workflow demonstrability" criteria.
7. **Write a per-paper assessment** to `papers/arxiv-<id>/assessment.md`:
   load result; confirmed code/data URLs; license; environment-setup result; the
   targeted figure/result/derivation; commands run; reproduction status + evidence;
   compute/data realism; scope + sample reader questions; and notes on honesty
   (what was assumed vs. verified).

Be explicit about uncertainty and never claim a reproduction that did not run.
"`blocked-*`" is a legitimate, useful outcome — it tells us the paper is a poor
example candidate, which is exactly what this skill is for.

## Stage C output: curate example recommendations

After deep-assessing the shortlist, write the deliverable:

```text
working/find-reproducible-papers/<timestamp>/example-recommendations.md
```

For each deep-assessed paper give a clear **recommend / maybe / reject** verdict
for use as a protocol-paper example, backed by the reproduction evidence, judged
against APP-example fit (not just reproducibility):

- **Reproducible by an agent in a sandbox** — the core requirement (Stage C
  status `reproduced` or `runs-but-differs`, ideally light setup).
- **Runs on a MacBook** — Apple Silicon, CPU/MPS, no CUDA/GPU, modest RAM. GPU
  pre-training / foundation-model / cluster-scale work is disqualified.
- **A concrete result to reproduce** — clear figures/tables for a computational
  paper, or a tractable symbolic derivation/identity for a theory paper; either
  shows off the `reproduce-results` step.
- **Public code + data + a permissive/known license** — so it could be re-staged.
- **Self-contained scope** — one clear result, not a sprawling benchmark.
- **Workflow demonstrability** — the full publish workflow and a reader
  paper-agent chat would be meaningful on it.
- **Domain fit / diversity** — resembles the project's examples; a physics + ML
  pair is more compelling than two near-duplicates.

End with a short recommendation block: which one or two papers to take forward as
protocol-paper examples and why, plus what is still unverified. The human decides
whether any of these papers actually go into the paper. Once a paper is chosen,
the natural next step is to run it through `simulate-publication` / `test-paper-agent` (or
the protocol's `publish-paper`) to produce the staged example and transcripts the
paper's "Example" section needs.

## Guardrails

- **Dev-only.** This skill discovers and triages candidates. It does not publish,
  does not create public repos, `APP_PUBLICATION.json`, or `.publications.md`, and
  does not stage anything as a real release.
- **Copyright / reuse.** Citing + linking a paper is always fine. **Re-hosting** a
  paper's source/PDF requires a redistributable license (CC-BY/SA/CC0); the
  arXiv-default "non-exclusive" license does **not** grant it, and an unlicensed
  repo is all-rights-reserved. Before committing any found paper as an example,
  check the `reuse` verdict: `ingestable` → re-host with attribution;
  `reference-only` → link + cite + reproduce locally, do not re-host. (Not legal
  advice; when unsure, prefer reference-only or ask the authors.)
- **Screening score ≠ reproducibility.** Only Stage C verifies. Report the
  distinction every time.
- **No paper code runs in Stages A/B.** The runner reads metadata only.
- **Respect the source repos and their licenses.** Note the license in each
  assessment; flag missing/incompatible licenses as a reason against using a
  paper as an example.
- **Do not modify `code/protocol_repo/`.** It is the pinned public submodule. If the
  assessment surfaces a protocol or skill gap (e.g. the stale Papers-with-Code
  reference in `load-paper`'s arXiv mode, `load-paper/arxiv.md`), record it as a
  note for the maintainer rather than editing the submodule here.
- Keep all candidates, screening output, assessments, and recommendations under
  `working/find-reproducible-papers/<timestamp>/`.

## Integration with other skills

- `code/protocol_repo/skills/load-paper` — load each shortlisted arXiv paper (Stage C).
- `code/protocol_repo/skills/reproduce-results` — the source of the reproduction status
  vocabulary; the natural follow-up once a paper is selected as an example.
- `skills/simulate-publication`, `skills/test-paper-agent`, `skills/compare-app` — run the
  full publishing simulation and reader paper-agent tests on a chosen example to
  generate the transcripts and staged package the protocol paper's example needs.
