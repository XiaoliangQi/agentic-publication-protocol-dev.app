---
name: simulate-publication
description: Run a dev-sandbox APP publication simulation on an example paper from data/example-papers using two persistent Codex CLI sessions, one publishing agent and one simulated-author agent, then save the direct chat transcript and produce an evaluator report on protocol/skill improvements.
---

# Simulate Publication

Use this skill to regression-test and improve the Agentic Publication Protocol implementation. The workflow simulates a real author directly interacting with `/publish-paper`, but it must use **dev-sandbox mode only** and must never create a public publication repo or APP compliance record.

Prefer the bundled runner:

```text
skills/simulate-publication/scripts/run_codex_chat.py <example-name>
```

The runner creates two persistent Codex CLI sessions:

- `publishing-agent`: uses the APP protocol skills to prepare a dev-sandbox publication candidate.
- `simulated-author`: acts as the author of the source paper using the cached author prompt.

The simulated-author session starts the conversation as the user/author by asking for APP publication help. The publishing session is launched from `data/example-papers/<example-name>/`, receives only the sandbox guardrails and skill location, and prepares a dev-sandbox candidate in `publication-staging/`. The script then alternates messages between the two sessions, records raw Codex JSONL logs and last-message files, saves Markdown and HTML transcripts, writes `run-summary.json`, and runs an evaluator pass at the end.

For live viewing, open the generated HTML transcript while the run is active:

```text
working/simulate-publication/<example-name>/<timestamp>/chat-history.html
```

It refreshes every five seconds by default and is kept for later review.

## Inputs

The user should provide, or you should infer, an example paper folder under:

```text
data/example-papers/<example-name>/
```

Use these local roots:

- Protocol repo: `code/protocol_repo/`
- Source example: `data/example-papers/<example-name>/`
- Publication candidate: `data/example-papers/<example-name>/publication-staging/`
- Run output: `working/simulate-publication/<example-name>/<timestamp>/`
- Reusable cached simulated-author prompt: `working/simulate-publication/<example-name>/simulated-author-prompt.md`

If the example folder is ambiguous, ask for the example name.

## Core Rule

The publishing workflow must run from the source folder:

```text
cd data/example-papers/<example-name>
```

The publishing Codex session is instructed to use the skills in `../../../code/protocol_repo/skills/`, especially:

- `publish-paper`
- `reproduce-results`
- `prepare-staging`
- `define-paper-agent`
- `validate-publication`
- `release-outcome`
- `load-paper-agent`
- `extract-chat-context` if relevant

It must create the candidate under `./publication-staging/`, treat that folder as the effective staged root, and write the final dev-sandbox outcome note under the run sandbox. It must not publish to GitHub, create a public repo, create `APP_PUBLICATION.json`, or write `.publications.md` as an APP compliance record. Any sandbox log must be clearly marked as an implementation test artifact.

## Workflow

### 1. Prepare Run Directory

Create:

```text
working/simulate-publication/<example-name>/<timestamp>/
working/simulate-publication/<example-name>/<timestamp>/sandbox/
working/simulate-publication/<example-name>/<timestamp>/logs/
```

Use a sortable timestamp such as `YYYYMMDD-HHMMSS`.

Use a fresh timestamp for every run. The script refuses to start if `working/simulate-publication/<example-name>/<timestamp>/` already exists, so a test run never overwrites a previous transcript, logs, summary, sandbox result, or evaluation report.

Before starting a new run, remove stale source-side generated outputs:

```text
data/example-papers/<example-name>/publication-staging/
data/example-papers/<example-name>/working/
```

Do not delete previous run reports. If retrying a failed test, use a new timestamp rather than reusing the old run directory.

### 2. Build Or Reuse Simulated-Author Prompt

First check:

```text
working/simulate-publication/<example-name>/simulated-author-prompt.md
```

If it exists, read it and use it.

If it does not exist, inspect the example folder thoroughly enough to create it:

- paper source, PDF, draft, slides, notes;
- code structure, scripts, notebooks, tests;
- dependency and environment files;
- data, figures, generated outputs;
- README or project documentation;
- field context visible from the paper and repo.

Then write `simulated-author-prompt.md`. The prompt must instruct the simulated author to:

- act as an author of this specific work;
- know the paper's claims, figures, code, data, limitations, and intended contribution;
- answer like a cooperative but realistic researcher;
- provide author intent and publication preferences when asked;
- answer license/reuse questions with a concrete license choice rather than deferring, even in dev-sandbox mode;
- authorize safe, project-scoped dependency installation attempts for validation when asked, while requiring permission or refusal for risky, proprietary, global, credentialed, unusually large, or system-invasive installs;
- correct the publishing agent when it misunderstands the work;
- avoid inventing facts not supported by the example folder;
- explicitly say when information is unknown or not present in the source folder;
- approve only dev-sandbox publication outcomes, never real public release.

Also include a short "source briefing" section summarizing the paper, code, likely field, and important files.

### 3. Run Two Direct Codex Sessions

Run:

```text
skills/simulate-publication/scripts/run_codex_chat.py <example-name>
```

Optional useful flags:

```text
--timestamp <YYYYMMDD-HHMMSS>
--max-turns <N>      # default: 80
--turn-timeout <N>   # default: 1200 seconds
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
runner. When running multiple examples in parallel, sync `code/protocol_repo/` once
before the batch and then launch all runners against the same checkout. The
runner itself does not update, commit, push, or otherwise mutate `code/protocol_repo/`.

The script uses `codex exec` to start the simulated-author session first, then starts the publishing-agent session with that author opening message. It then uses `codex exec resume <session-id>` to continue each side. It saves:

- `chat-history.md`: readable transcript of both agents.
- `chat-history.html`: browser-friendly transcript that updates after every completed turn.
- `live-events.jsonl`: structured event stream used to render the HTML view.
- `run-summary.json`: machine-readable run metadata, session IDs, guardrail checks, and output paths.
- `logs/*.jsonl`: raw Codex CLI JSONL event logs.
- `logs/*-last-message.md`: each agent's final message for each turn.
- `evaluation-report.md`: evaluator output, unless `--no-eval` is passed.

### 4. Conversation Requirements

The publishing and author sessions should talk directly in the same style a real user would interact with `/publish-paper`. The runner should not decide scientific content for them; it only alternates messages and records the transcript.

The first turn must be from `simulated-author`, phrased like a real author/user asking the publishing agent to prepare the paper through the APP workflow. It does not need to mention dev-sandbox mode; the publisher harness prompt supplies that guardrail.

Use these required checkpoints unless the run fails earlier. Keep each publishing-agent turn bounded: it should complete at most one major checkpoint, summarize the result, and stop for the next author decision or approval. This is especially important after the modular `publish-paper` refactor, because reproduction, staging, paper-agent docs, validation, and final outcome can each become too large for one reliable Codex turn.

1. **Opening brief**
   - Publishing agent asks the simulated author for initial publication intent: canonical paper, target repository name, what to include/exclude, sensitive files, supplementary material permissions, license/reuse terms, expected reproduction limits, and author-note preferences.
   - Publishing agent explicitly asks whether the author wants to include publication-safe chat/session context, and explains extraction options if the author does not already have it ready.
   - Publishing agent explains the APP workflow and staging folder in plain language, without assuming the author has read `PROTOCOL.md`.
   - Simulated author answers before staging begins.
2. **Discovery questions**
   - Ask the publishing agent to inspect the source and return only questions or a proposed decision table.
   - Publishing agent asks substantive questions directly to the simulated author.
   - Require author answers before staging files that depend on those answers.
3. **Result reproduction review**
   - Publishing agent uses `reproduce-results` to check existing figures, tables, experiments, and analytic derivations before staging.
   - Publishing agent must not suggest improvements, new experiments, or new results as part of this workflow.
   - Publishing agent summarizes reproduced/runs-but-differs/blocked/manual statuses for the simulated author.
   - Publishing agent should stop after the reproduction summary/report and ask for author confirmation before moving into staging.
4. **Staging plan review**
   - Ask the publishing agent for a concise staging plan and file inclusion/exclusion list.
   - Publishing agent sends the plan to the simulated author for approval, corrections, or constraints.
   - Only after author approval should the publishing agent build `publication-staging/`.
   - After staging, publishing agent provides a plain-language summary of top-level folders and what is ground truth versus optional context.
   - Publishing agent should stop after the staging summary and ask for review before drafting paper-agent docs.
5. **Drafted paper-agent materials review**
   - After `AGENTS.md`, README, author note, know-how, or staged skills are drafted, ask the simulated author to review the claims, voice, limits, and sensitive-material handling.
   - Prefer a batched review with concise excerpts/summaries for all author-sensitive materials, so the simulation does not spend many turns approving one section at a time.
   - Require the publishing agent to amend the staged files based on the author response.
   - Publishing agent should stop after drafting or amending these materials, rather than proceeding directly into full validation.
6. **Validation and paper-agent test review**
   - Ask the publishing agent to run validation and local paper-agent testing.
   - If validation is blocked by missing dependencies, the simulated author should tell the publishing agent to attempt safe, project-scoped installs when the run authorization allows it, and to ask before risky/global/proprietary installs.
   - Publishing agent sends a short validation summary to the simulated author and asks whether the reported limitations are accurate.
   - If the author flags a mismatch, send it back to the publishing agent for correction.
   - Publishing agent should stop after validation/test summary and wait for final dev-sandbox signoff.
7. **Final dev-sandbox signoff**
   - Ask the simulated author whether the result is acceptable as a dev-sandbox test artifact only.
   - The publishing agent uses `release-outcome` only as a lightweight final review/freeze and dev-sandbox outcome step, not as a second validator.
   - The publishing agent may then write the final dev-sandbox result.

The transcript/evaluator must detect and flag these protocol failures:

- publishing agent finishes or stages author-dependent files before author approval;
- publishing agent writes questions to a file but does not ask the simulated author in the direct chat;
- author answers arrive after final staging but are not incorporated;
- validation claims success without command evidence or with unresolved known issues;
- publishing agent fails to ask about license/reuse terms before staging, or the simulated author defers licensing instead of making a concrete sandbox test choice;
- real-publication artifacts are created.

If one of these failures happens, keep the run useful: record it in `chat-history.md`, ask the publishing agent to repair the run if possible, and include the failure in `run-summary.json`.

Keep the conversation going until one of these happens:

- the publishing agent completes dev-sandbox prepare, validation, local paper-agent testing, and reports a final dev-sandbox outcome that the runner accepts;
- the publishing agent reaches a blocker that the simulated author cannot resolve;
- a clear protocol or skill failure prevents progress.

The runner must not accept completion based only on a model claim. The publishing-agent message must have:

```text
APP_CHAT_STATUS: ready_for_evaluation
APP_PHASE: final-dev-sandbox-result
```

and the runner must verify:

- `data/example-papers/<example-name>/publication-staging/` exists;
- no `APP_PUBLICATION.json` exists under the sandbox or `publication-staging/`;
- no `.publications.md` exists under the sandbox or `publication-staging/`.

When those checks pass, the runner writes `sandbox/DEV_SANDBOX_RESULT.md` from the accepted final publishing-agent message. The nested publishing-agent session should not write this external runner artifact itself, because its project root is the source paper folder.

If the publishing agent claims completion before these checks pass, the runner should record a completion-check failure in `chat-history.md` and give the publishing agent one repair turn. If the repair still fails, set `completion_status` to `completion_claim_failed_artifact_check` in `run-summary.json`.

The script must preserve speaker labels and timestamps in a transcript file:

```text
working/simulate-publication/<example-name>/<timestamp>/chat-history.md
```

Suggested format:

```markdown
# Simulate Publication Chat History

Example: <example-name>
Run: <timestamp>
Mode: dev-sandbox

## Turn 1 - simulated-author
...

## Turn 2 - publishing-agent
...
```

Also save any useful machine-readable metadata to:

```text
working/simulate-publication/<example-name>/<timestamp>/run-summary.json
```

Include at least example path, protocol repo path, sandbox path, start/end time, completion status, and key output files.

Also include:

- number of publishing-agent turns and simulated-author turns;
- author decision checkpoints completed;
- whether any checkpoint was skipped;
- whether the publishing agent proceeded before author approval;
- whether validation found privacy, reproducibility, or paper-agent usability issues;
- whether any author answer arrived after staging and whether staging was amended.

### 5. Preserve Sandbox Outputs

Do not reset or delete the sandbox before evaluation. Preserve:

- `publication-staging/` or equivalent candidate tree;
- validation reports;
- dev-sandbox logs;
- paper-agent test notes;
- any failure state.

The evaluator needs these artifacts.

### 6. Run The Evaluator

After the simulated publication ends, run a third Codex evaluator pass. The bundled script does this automatically unless `--no-eval` is passed.

Give it:

- `chat-history.md`;
- `run-summary.json`;
- the publication candidate path and sandbox output path;
- `code/protocol_repo/PROTOCOL.md`;
- relevant skills under `code/protocol_repo/skills/`;
- relevant templates under `code/protocol_repo/template/`.

Ask it to evaluate:

- What worked well in the protocol and skills.
- Where the publishing agent got confused.
- Where the simulated author had to compensate for missing instructions.
- Whether the multi-round discussion was realistic and whether author decisions shaped the staged output.
- Whether the direct Codex-session conversation enforced the required checkpoints.
- Whether transcript/logs captured which skills or protocol files were used.
- Whether dev-sandbox mode stayed isolated from real publishing.
- Whether `publication-staging/` was treated as the effective root.
- Whether validation and paper-agent testing were meaningful.
- Whether the publishing agent attempted direct figure/table reproduction before downgrading to selected/manual reproduction.
- Whether it created `code/figure-reproduction/README.md` and per-figure scripts, and whether those were validated independently when possible.
- Whether `AGENTS.md` and README point to the figure reproduction map and accurately summarize statuses.
- Whether the author interaction burden was reasonable.
- Whether outputs were complete enough for a reader agent.
- Concrete improvement recommendations for `PROTOCOL.md`, skills, templates, and sandbox workflow.

The evaluator must distinguish:

- protocol/spec problems;
- skill instruction problems;
- template problems;
- example-project problems;
- publishing-agent execution mistakes.

### 7. Save Final Report

Save the evaluator output to:

```text
working/simulate-publication/<example-name>/<timestamp>/evaluation-report.md
```

The report must include:

- run metadata;
- brief outcome summary;
- what worked well;
- things that need improvement;
- severity or priority for each issue;
- concrete suggested changes, with file paths in `code/protocol_repo/` where applicable;
- open questions for the real protocol maintainer.

End by reporting the paths to:

- `simulated-author-prompt.md`;
- `chat-history.md`;
- `run-summary.json`;
- sandbox output;
- `evaluation-report.md`.

## Guardrails

- Dev-sandbox mode only.
- No GitHub publication.
- No public repo creation.
- No `APP_PUBLICATION.json` creation.
- No `.publications.md` APP compliance record.
- Do not modify `code/protocol_repo/` during the simulation unless the user explicitly asks for fixes after reading the evaluation report.
- Keep run transcripts, logs, summaries, and evaluator reports under `working/simulate-publication/<example-name>/`.
- The generated publication candidate may live at `data/example-papers/<example-name>/publication-staging/` for realistic source-folder testing.
- Do not allow a simulated publication to count as successful unless the publishing agent waited for author input at the required checkpoints or explicitly recorded why a checkpoint was not applicable.
