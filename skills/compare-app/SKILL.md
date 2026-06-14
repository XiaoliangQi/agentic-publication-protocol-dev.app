---
name: compare-app
description: Compare an APP paper agent against a general agent on the same paper by running two neutral simulated-reader chats with shared reader prompts, then anonymize and evaluate both transcripts for accuracy and informativeness.
---

# Compare APP

Use this skill to compare how well a staged APP paper agent helps a reader versus a general agent that has access to the original working repo. The simulated reader prompt is shared with `test-paper-agent` through `skills/_shared/reader_simulator.py`; only the access mode differs.

Prefer the bundled runner:

```text
skills/compare-app/scripts/run_compare_app.py <example-name-or-source-root>
```

If the argument is omitted, the runner chooses the newest source folder matching:

```text
data/example-papers/*/publication-staging/
```

## Inputs

Default layout:

```text
data/example-papers/<example-name>/
data/example-papers/<example-name>/publication-staging/
```

The staged folder must contain `AGENTS.md` and `paper/`. The original source folder must be separate from `publication-staging/`.

Useful flags:

```text
--source-root <path>
--staging-root <path>
--paper-path <path>
--max-rounds 15
--timestamp <YYYYMMDD-HHMMSS>
--model <model>
--seed <int>
--no-eval
--no-html-refresh
--reuse-general-run <existing-run-dir>
```

## What The Runner Does

- Copies the chosen paper files into the run directory as a paper-only reader context.
- Generates one neutral `question-script.json` from only those copied paper files.
- Runs two independent chats using the same shared graduate-student reader simulator:
  - `paper-agent`: launched in `publication-staging/`, follows local `AGENTS.md`/`CLAUDE.md`, and must not access the original source root.
  - `general-agent`: launched in the original source root, does not use `AGENTS.md`, and must not access `publication-staging/`.
- Sends the exact same scripted reader questions to both agents in the same order, with a minimum of five questions.
- With `--reuse-general-run`, reuses the existing run's `question-script.json` and `general-agent-chat-history.md`, then reruns only the paper-agent chat against those same questions. Use this for protocol/template iterations where the original source repo and general-agent baseline have not changed.
- Saves separate transcripts for each chat.
- Randomizes and anonymizes transcript order as `Agent A` and `Agent B`.
- Copies each agent's allowed workspace to a neutral `evaluator-workspaces/agent-a` or `agent-b` path, omits/redacts protocol identity files, and rewrites transcript path references to those neutral paths, so the evaluator can check grounding without seeing source-root versus `publication-staging` names.
- Runs a neutral evaluator without APP-specific criteria. The evaluator may inspect both neutral workspaces for fact-checking, but must not penalize one agent for citing files that exist only in its own workspace.

## Outputs

The run is saved under:

```text
working/compare-app/<example-name>/<timestamp>/
```

Artifacts:

- `question-plan.md`: raw paper-only planner output.
- `question-script.json`: exact reader questions sent to both agents.
- `paper-agent-chat-history.md`: paper-agent conversation.
- `general-agent-chat-history.md`: general-agent conversation.
- `evaluation-input.md`: anonymized randomized transcripts.
- `evaluation-report.md`: final evaluation, unless `--no-eval` is used.
- `run-summary.json`: paths, session IDs, turn counts, random seed, and hidden agent-label mapping.
- `chat-history.html` and `live-events.jsonl`: combined live view.
- `logs/*.jsonl` and `logs/*-last-message.md`: raw Codex outputs.

## Evaluation Focus

The evaluator should judge the two conversations as ordinary paper-help chats, without APP-specific criteria and without knowing which transcript came from the APP paper agent. It should score each anonymized agent on accuracy, informativeness, grounding, and honesty about uncertainty. In the written discussion and comparative verdict, it should also consider usefulness for a realistic graduate-student reader and reproduction/actionability where relevant.
