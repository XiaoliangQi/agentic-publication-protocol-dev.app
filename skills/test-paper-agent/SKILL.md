---
name: test-paper-agent
description: Test an APP paper-agent by running a direct Codex CLI conversation between a grad-student user agent and the paper agent launched inside an APP-compliant publication folder, then save live HTML/Markdown transcripts and an evaluator report.
---

# Test Paper Agent

Use this skill to evaluate whether an APP publication can actually support a reader agent in realistic use. It starts two persistent Codex CLI sessions:

- `grad-student-user`: a graduate student in the paper's field who has general background but is not specially familiar with this paper.
- `paper-agent`: a Codex session launched with `-C <paper-folder>`, so it works from the APP publication folder and follows its `AGENTS.md`/`CLAUDE.md`.

Both conversation agents are launched in the same `publication-staging/` folder so file paths and local environment are realistic. Only the paper-agent prompt tells the agent to follow `AGENTS.md`/`CLAUDE.md`; the grad-student user prompt should inspect reader-facing materials such as `README.md`, `paper/`, and reproduction notes. The runner alternates their messages, records Markdown and live HTML transcripts, and asks a third evaluator agent to judge the result.

Prefer the bundled runner:

```text
skills/test-paper-agent/scripts/run_paper_agent_chat.py [paper-folder]
```

If `paper-folder` is omitted, the runner chooses the newest folder matching:

```text
data/example-papers/*/publication-staging/
```

## Inputs

The paper folder should be an APP publication or dev-sandbox staging folder containing at least:

```text
AGENTS.md
paper/
README.md
```

Useful examples:

```text
skills/test-paper-agent/scripts/run_paper_agent_chat.py \
  data/example-papers/sae-analysis/publication-staging
```

Optional flags:

```text
--max-rounds 15
--timestamp <YYYYMMDD-HHMMSS>
--model <model>
--no-eval
--no-html-refresh
```

Before starting a run, make sure `code/protocol_repo/` is at the intended protocol
revision. For the default latest-main test, run this once:

```text
code/scripts/update-protocol-submodule.sh
```

For a pinned protocol test, update or check out that commit before launching the
runner. When running multiple paper-agent tests in parallel, sync `code/protocol_repo/`
once before the batch and then launch all runners against the same checkout. The
runner itself does not update, commit, push, or otherwise mutate `code/protocol_repo/`.

## Outputs

The run is saved under:

```text
working/test-paper-agent/<paper-name>/<timestamp>/
```

Artifacts:

- `chat-history.md`: full conversation.
- `chat-history.html`: auto-refreshing browser view while the run is active; kept for later review.
- `live-events.jsonl`: event stream used to render the HTML.
- `run-summary.json`: paper path, session IDs, turn counts, status, output paths.
- `logs/*.jsonl`: raw Codex CLI event logs.
- `logs/*-last-message.md`: last message from each turn.
- `evaluation-report.md`: third-agent evaluation, unless `--no-eval` is used.

## Conversation Rules

The grad-student user starts the conversation. The questions should mix:

- generic understanding questions about the paper's problem, claims, assumptions, and contribution;
- technical-detail questions about definitions, equations, methods, data, or experiments;
- reproduction questions, including at least one request about reproducing or checking a specific figure/table when the paper has figures/tables;
- a quick next-step research question, such as a small ablation, extension, sanity check, or follow-up experiment.

The paper-agent should answer from the staged APP paper folder. It should cite or refer to relevant local files and commands when useful, especially `AGENTS.md`, `README.md`, paper sources, code, data, and figure-reproduction materials. It should say when something is unknown, blocked, or not supported by the staged materials.

The conversation should continue until one of these happens:

- the grad-student user decides the test has covered understanding, technical details, reproduction, and next-step research;
- the paper-agent reaches a real blocker;
- the maximum number of rounds is reached.

Every message should end with:

```text
PAPER_AGENT_TEST_STATUS: continue | finished | blocked
PAPER_AGENT_TEST_PHASE: <short phase>
PAPER_AGENT_TEST_TOPICS: <comma-separated topics>
```

The runner records the status but does not require exact success; the evaluator determines quality.

## Evaluation Focus

The evaluator should inspect the transcript, run summary, paper folder, `AGENTS.md`, protocol repo, and any figure-reproduction materials. It should report:

- whether the paper agent helped a realistic graduate-student reader understand the paper;
- whether answers were grounded in the APP publication rather than invented;
- whether the agent found and used `AGENTS.md`/`CLAUDE.md`, paper files, code, data, and figure-reproduction notes;
- whether reproduction guidance was actionable and honest about blockers;
- whether the agent could support quick next-step research without overclaiming;
- what worked well in the APP materials;
- what should improve in `PROTOCOL.md`, templates, modular workflow skills (`publish-paper`, `reproduce-results`, `prepare-staging`, `define-paper-agent`, `validate-publication`, `release-outcome`), or the staged paper package.
