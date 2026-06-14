# APP Publication Validation Report

Date: 2026-06-14

Repository root validated: this APP publication repository.

Validation stage: `full`

Result: `passed`

## Passed Checks

- Required APP root files are present: `AGENTS.md`, `CLAUDE.md`, `README.md`,
  `LICENSE`, `paper/`, `code/`, `data/`, `environment/`, `supplementary/`, and
  `skills/`.
- `AGENTS.md` frontmatter declares APP protocol version `1.0.0`, paper format
  `latex`, and publication version `1.0.0`, matching the intended tag
  `v1.0.0`.
- `CLAUDE.md` delegates to `AGENTS.md`.
- Paths named in `AGENTS.md` and `README.md` resolve from the repository root.
- `code/protocol_repo/` is a Git submodule pinned to APP protocol release
  `v1.0.0`.
- `data/README.md` documents the included compact summary and the external
  Hugging Face dataset.
- The Hugging Face dataset URL returned HTTP 200 during validation.
- `environment/README.md` documents tested tools, runner commands, and manual
  requirements.
- `code/figure-reproduction/README.md` lists all paper figures and the
  compare-app table with final APP statuses.
- Python scripts compile with `python3 -m py_compile`.
- Bundled skill script entry points respond to `--help` successfully:
  `skills/compare-app/scripts/run_compare_app.py`,
  `skills/find-reproducible-papers/scripts/build_pwc_index.py`,
  `skills/find-reproducible-papers/scripts/find_reproducible_papers.py`,
  `skills/find-reproducible-papers/scripts/scout_topic.py`,
  `skills/simulate-publication/scripts/run_codex_chat.py`, and
  `skills/test-paper-agent/scripts/run_paper_agent_chat.py`.
- The protocol-update helper responds to `--help` successfully:
  `code/scripts/update-protocol-submodule.sh --help`.
- The bundled `compare-app` unit test passed:
  `python3 skills/compare-app/scripts/test_rewrite_workspace_paths.py`.
- Skill runner defaults were checked against the publication layout. The
  `test-paper-agent` and `simulate-publication` runners now default to
  `--protocol-repo code/protocol_repo`, matching the public submodule location.
- A bounded live smoke test of the bundled `test-paper-agent` skill passed with
  `--max-rounds 1`, `--no-eval`, and outputs written outside the release tree
  under `/tmp/app-skill-test-paper-agent`. The final default-path run detected
  `AGENTS.md`, `CLAUDE.md`, and `code/figure-reproduction/README.md`, resolved
  `protocol_repo_path` to `code/protocol_repo`, completed one
  reader/paper-agent round, and produced
  `completion_status: max_rounds_reached` as expected for the one-round bound.
- A deterministic smoke test of the bundled `compare-app` runner passed using a
  fake Codex executable and outputs outside the release tree. The runner
  generated a five-question script, ran both the general-agent and paper-agent
  arms to `script_completed`, and wrote the expected run summary, transcripts,
  logs, live-event file, and evaluator workspaces.
- A deterministic smoke test of the bundled `simulate-publication` runner passed
  on a minimal temporary example using the default `--protocol-repo` setting.
  The run resolved the protocol repository to `code/protocol_repo`, completed
  one simulated-author turn and one publishing-agent turn, and ended with
  `completion_status: max_turns_reached`, as expected for the two-turn bound.
- A lightweight smoke test of the bundled `find-reproducible-papers` runner
  passed with one arXiv candidate and optional Hugging Face, paper-license, and
  Papers-with-Code enrichment disabled. The runner wrote `criteria.json`,
  `candidates.jsonl`, `screening.jsonl`, `screening-report.md`, and
  `shortlist.json` under a temporary output directory.
- `data/compare-app-benchmark/data/data_summary.json` parses as valid JSON.
- The compare-app table rows and means regenerate from
  `data/compare-app-benchmark/data/data_summary.json` using
  `python3 code/figure-reproduction/table_compare_app_scores.py`.
- The paper compiles from `paper/` with
  `latexmk -pdf -interaction=nonstopmode -halt-on-error app-paper.tex`.
- Bibliography API audit was previously rerun after title correction and
  reported `=== NO PROBLEMS ===`; remaining output consisted of notes such as
  bot-blocked URLs or published-version year/page differences.
- A fresh paper-agent smoke test was run from the repository root in a read-only
  Codex session and saved as `supplementary/paper-agent-test.md`. The test
  correctly identified ground truth, summarized the paper, named reproduction
  commands, and reported manual-only or backend-dependent limitations.
- Privacy/path scan found no private filesystem paths, obvious credentials, or
  token patterns in the publication-facing files checked.
- Hidden/generated artifact scan found no `.DS_Store`, `.ipynb_checkpoints`,
  `__pycache__`, `node_modules`, or common cache directories in
  publication-owned files outside the `code/protocol_repo/` submodule.
- The unused `paper/figures/legacy/` directory was removed before release; no
  publication-facing paper, README, agent, or validation file references it.

## Manual Verification Needed

- Draw.io workflow figures are source-available as `.drawio` files but require
  Draw.io export. They are marked `manual-only` in
  `code/figure-reproduction/README.md`.
- Some bibliography URL checks may return 403 because of bot blocking. These
  are documented as manual-review notes rather than missing sources.

## Non-Blocking Reproduction Caveats

- Regenerated compare-app average-aspect figure files are semantically
  consistent with the paper but are not expected to be byte-identical to the
  committed figure artifacts.
- The research-network PNG reproduced byte-identically in development
  validation. PDF and SVG outputs may differ byte-for-byte because of backend
  metadata.
- TeX compilation emits non-fatal warnings about included PDF versions,
  duplicate destinations, and minor overfull/underfull boxes.
- Full end-to-end scientific runs of `simulate-publication`, `compare-app`, and
  `find-reproducible-papers` were not performed during release validation
  because they are multi-agent, network-dependent, or require example source
  workspaces that are intentionally not included in this first release. Their
  entry points, default paths, and runner orchestration were tested as described
  above.

## Issues Needing Changes

None.

## Public-Release Blockers

None.

## Sandbox-Only Deferrals

None.

## Summary

Full APP validation passed for this publication repository. The repository is
ready for author release approval, public commit/tag, and creation of the
`v1.0.0` GitHub release manifest.
