#!/usr/bin/env python3
"""Run a simulate-publication simulation using separate Codex CLI sessions.

This script starts a simulated-author Codex session first, then starts a
publishing-agent Codex session with the author's opening message. It alternates
messages between them, records raw Codex JSONL logs, writes a readable chat
transcript, verifies final sandbox artifacts before accepting completion, and
then runs a final evaluator pass.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
STATUS_RE = re.compile(
    r"APP_CHAT_STATUS\s*:\s*(ready_for_evaluation|final_signoff|continue|blocked|finished|complete)",
    re.IGNORECASE,
)
PHASE_RE = re.compile(r"APP_PHASE\s*:\s*([^\n\r]+)", re.IGNORECASE)
FINAL_PHASE = "final-dev-sandbox-result"


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def iter_values(obj: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(obj, dict):
        for value in obj.values():
            values.append(value)
            values.extend(iter_values(value))
    elif isinstance(obj, list):
        for value in obj:
            values.append(value)
            values.extend(iter_values(value))
    return values


def extract_session_id(jsonl: str) -> str | None:
    preferred_keys = {
        "session_id",
        "conversation_id",
        "thread_id",
        "rollout_id",
    }
    fallback: str | None = None
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            for key, value in event.items():
                if key in preferred_keys and isinstance(value, str) and UUID_RE.fullmatch(value):
                    return value
            for value in iter_values(event):
                if isinstance(value, str):
                    match = UUID_RE.search(value)
                    if match and fallback is None:
                        fallback = match.group(0)
    return fallback


def extract_skills(text: str) -> list[str]:
    skills = sorted(set(re.findall(r"\b[a-z][a-z0-9-]*(?:/[A-Z]+\.md|\.md)?\b", text)))
    known = {
        "publish-paper",
        "reproduce-results",
        "prepare-staging",
        "define-paper-agent",
        "release-outcome",
        "validate-publication",
        "load-paper-agent",
        "extract-chat-context",
        "simulate-publication",
        "AGENTS.md",
        "CLAUDE.md",
        "PROTOCOL.md",
        "SKILL.md",
    }
    return [skill for skill in skills if skill in known]


def extract_footer(text: str) -> dict[str, str | None]:
    status_match = STATUS_RE.search(text)
    phase_match = PHASE_RE.search(text)
    return {
        "status": status_match.group(1).strip().lower() if status_match else None,
        "phase": phase_match.group(1).strip().lower() if phase_match else None,
    }


def render_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_markdownish(text: str) -> str:
    lines = text.rstrip().splitlines()
    out: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append("<p>" + render_inline_markdown(" ".join(paragraph)) + "</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            close_list()
            out.append("<h4>" + render_inline_markdown(stripped[4:]) + "</h4>")
        elif stripped.startswith("## "):
            flush_paragraph()
            close_list()
            out.append("<h3>" + render_inline_markdown(stripped[3:]) + "</h3>")
        elif stripped.startswith("# "):
            flush_paragraph()
            close_list()
            out.append("<h2>" + render_inline_markdown(stripped[2:]) + "</h2>")
        elif stripped.startswith("- "):
            flush_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + render_inline_markdown(stripped[2:]) + "</li>")
        else:
            close_list()
            paragraph.append(stripped)
    flush_paragraph()
    close_list()
    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    return "\n".join(out)


def mathjax_head() -> str:
    return """<script>
window.MathJax = {
  tex: {
    inlineMath: [['\\\\(', '\\\\)'], ['$', '$']],
    displayMath: [['\\\\[', '\\\\]'], ['$$', '$$']],
    processEscapes: true
  },
  options: {
    skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
  }
};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
"""


def load_live_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def render_live_html(
    *,
    html_path: Path,
    events_path: Path,
    example: str,
    timestamp: str,
    auto_refresh: bool,
) -> None:
    events = load_live_events(events_path)
    refresh = '<meta http-equiv="refresh" content="5">\n' if auto_refresh else ""
    cards: list[str] = []
    for event in events:
        kind = event.get("kind", "turn")
        speaker = str(event.get("speaker", "runner"))
        turn = event.get("turn")
        time = html.escape(str(event.get("time", "")))
        skills = html.escape(str(event.get("skills", "")))
        message = str(event.get("message", ""))
        title = f"Turn {turn} - {speaker}" if turn else speaker
        css_kind = "runner" if kind != "turn" else speaker
        cards.append(
            f"""
<section class="card {html.escape(css_kind)}">
  <div class="meta">
    <span>{html.escape(title)}</span>
    <span>{time}</span>
  </div>
  {f'<div class="skills">Detected skills/files: {skills}</div>' if skills else ''}
  <div class="message">
    {render_markdownish(message)}
  </div>
</section>
"""
        )

    body = "\n".join(cards) if cards else "<p class=\"empty\">Waiting for the first turn...</p>"
    write_text(
        html_path,
        f"""<!doctype html>
<html lang="en">
<head>
{refresh}<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulate Publication Chat - {html.escape(example)} - {html.escape(timestamp)}</title>
{mathjax_head()}
<style>
:root {{
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --ink: #1f2933;
  --muted: #667085;
  --line: #d8dee8;
  --author: #e8f3ff;
  --publisher: #eef8ed;
  --runner: #fff4df;
}}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
header {{
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 16px 24px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(8px);
}}
h1 {{
  margin: 0;
  font-size: 20px;
  letter-spacing: 0;
}}
.sub {{
  margin-top: 4px;
  color: var(--muted);
  font-size: 13px;
}}
main {{
  max-width: 980px;
  margin: 0 auto;
  padding: 20px;
}}
.card {{
  margin: 0 0 16px;
  padding: 16px 18px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}}
.simulated-author {{ border-left: 5px solid #4088d5; background: var(--author); }}
.publishing-agent {{ border-left: 5px solid #4f9d5d; background: var(--publisher); }}
.runner {{ border-left: 5px solid #d08b2c; background: var(--runner); }}
.meta {{
  display: flex;
  gap: 12px;
  justify-content: space-between;
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 8px;
}}
.skills {{
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 10px;
}}
.message p {{ margin: 0 0 10px; }}
.message ul {{ margin: 0 0 10px 22px; padding: 0; }}
.message h2, .message h3, .message h4 {{ margin: 14px 0 8px; }}
code {{
  padding: 1px 4px;
  border-radius: 4px;
  background: rgba(17, 24, 39, 0.08);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
}}
pre {{
  overflow-x: auto;
  padding: 12px;
  border-radius: 6px;
  background: #111827;
  color: #f9fafb;
}}
.empty {{ color: var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>Simulate Publication Direct Chat</h1>
  <div class="sub">Example: {html.escape(example)} · Run: {html.escape(timestamp)} · Auto-refresh: {'on' if auto_refresh else 'off'}</div>
</header>
<main>
{body}
</main>
</body>
</html>
""",
    )


def write_dev_sandbox_result(
    sandbox_dir: Path,
    publication_staging: Path,
    publisher_message: str,
    checks: dict[str, Any],
) -> Path:
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    dev_result = sandbox_dir / "DEV_SANDBOX_RESULT.md"
    dev_result.write_text(
        "\n".join(
            [
                "# Dev-Sandbox Result",
                "",
                f"Written by: `skills/simulate-publication/scripts/run_codex_chat.py`",
                f"Written at: {iso_now()}",
                "",
                "Outcome: publishing agent reported final dev-sandbox result.",
                "",
                f"Publication staging path: `{publication_staging}`",
                "",
                "Runner guardrail checks:",
                f"- publication staging exists: `{checks['publication_staging_exists']}`",
                f"- `APP_PUBLICATION.json` absent: `{checks['app_publication_json_absent']}`",
                f"- `.publications.md` absent: `{checks['publications_md_absent']}`",
                "",
                "Final publishing-agent message:",
                "",
                "```text",
                publisher_message.rstrip(),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return dev_result


def completion_check(sandbox_dir: Path, publication_staging: Path, publisher_message: str) -> dict[str, Any]:
    footer = extract_footer(publisher_message)
    dev_result = sandbox_dir / "DEV_SANDBOX_RESULT.md"
    guardrail_roots = [sandbox_dir, publication_staging]
    app_publication_files = sorted(
        str(path)
        for root in guardrail_roots
        if root.exists()
        for path in root.rglob("APP_PUBLICATION.json")
    )
    publications_md_files = sorted(
        str(path)
        for root in guardrail_roots
        if root.exists()
        for path in root.rglob(".publications.md")
    )
    checks = {
        "publisher_status": footer["status"],
        "publisher_phase": footer["phase"],
        "status_ready_for_evaluation": footer["status"] == "ready_for_evaluation",
        "phase_final_dev_sandbox_result": footer["phase"] == FINAL_PHASE,
        "publication_staging_exists": publication_staging.is_dir(),
        "app_publication_json_absent": not app_publication_files,
        "publications_md_absent": not publications_md_files,
        "app_publication_json_files": app_publication_files,
        "publications_md_files": publications_md_files,
    }
    if all(
        [
            checks["status_ready_for_evaluation"],
            checks["phase_final_dev_sandbox_result"],
            checks["publication_staging_exists"],
            checks["app_publication_json_absent"],
            checks["publications_md_absent"],
        ]
    ):
        try:
            write_dev_sandbox_result(sandbox_dir, publication_staging, publisher_message, checks)
            checks["dev_sandbox_result_write_error"] = None
        except OSError as exc:
            checks["dev_sandbox_result_write_error"] = str(exc)
    checks["dev_sandbox_result_exists"] = dev_result.is_file()
    checks["accepted"] = all(
        [
            checks["status_ready_for_evaluation"],
            checks["phase_final_dev_sandbox_result"],
            checks["dev_sandbox_result_exists"],
            checks["publication_staging_exists"],
            checks["app_publication_json_absent"],
            checks["publications_md_absent"],
        ]
    )
    return checks


class CodexSessionRunner:
    def __init__(
        self,
        *,
        codex_bin: str,
        workspace: Path,
        logs_dir: Path,
        sandbox: str,
        approval: str,
        model: str | None,
        extra_args: list[str],
        turn_timeout: int | None,
    ) -> None:
        self.codex_bin = codex_bin
        self.workspace = workspace
        self.logs_dir = logs_dir
        self.sandbox = sandbox
        self.approval = approval
        self.model = model
        self.extra_args = extra_args
        self.turn_timeout = turn_timeout

    def _base_cmd(self) -> list[str]:
        cmd = [
            self.codex_bin,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            str(self.workspace),
            "-s",
            self.sandbox,
        ]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.extend(self.extra_args)
        return cmd

    def start(self, name: str, prompt: str) -> tuple[str, str, Path]:
        output_path = self.logs_dir / f"{name}-turn-001-last-message.md"
        cmd = self._base_cmd() + ["-o", str(output_path), "-"]
        raw = self._run(cmd, prompt, self.logs_dir / f"{name}-turn-001.jsonl")
        session_id = extract_session_id(raw)
        if not session_id:
            raise RuntimeError(f"Could not discover Codex session id for {name}. See logs.")
        return session_id, read_text(output_path), output_path

    def resume(self, name: str, session_id: str, turn: int, prompt: str) -> tuple[str, Path]:
        output_path = self.logs_dir / f"{name}-turn-{turn:03d}-last-message.md"
        cmd = [
            self.codex_bin,
            "exec",
            "resume",
            "--json",
            "--skip-git-repo-check",
            "-o",
            str(output_path),
        ]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.extend(self.extra_args)
        cmd.extend([session_id, "-"])
        raw_path = self.logs_dir / f"{name}-turn-{turn:03d}.jsonl"
        self._run(cmd, prompt, raw_path)
        return read_text(output_path), output_path

    def one_shot(self, name: str, prompt: str) -> tuple[str, Path]:
        output_path = self.logs_dir / f"{name}-last-message.md"
        cmd = self._base_cmd() + ["-o", str(output_path), "-"]
        self._run(cmd, prompt, self.logs_dir / f"{name}.jsonl")
        return read_text(output_path), output_path

    def _run(self, cmd: list[str], prompt: str, raw_path: Path) -> str:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace,
                check=False,
                timeout=self.turn_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raw_path.write_text(stdout, encoding="utf-8")
            timeout_path = raw_path.with_suffix(raw_path.suffix + ".timeout")
            timeout_path.write_text(
                f"Timed out after {self.turn_timeout} seconds: {' '.join(cmd)}\n",
                encoding="utf-8",
            )
            if stderr:
                raw_path.with_suffix(raw_path.suffix + ".stderr").write_text(stderr, encoding="utf-8")
            output_path = None
            if "-o" in cmd:
                try:
                    output_path = Path(cmd[cmd.index("-o") + 1])
                except (IndexError, ValueError):
                    output_path = None
            if output_path is not None:
                speaker = "publishing agent" if "publishing-agent" in raw_path.name else "simulated author"
                status = "APP_CHAT_STATUS: blocked"
                output_path.write_text(
                    f"The {speaker} turn timed out after {self.turn_timeout} seconds before producing a complete response. "
                    "Treat this as a runner/model timeout, not as a completed APP workflow.\n\n"
                    f"{status}\n"
                    "APP_PHASE: runner-timeout\n"
                    "APP_SKILLS_USED: none\n",
                    encoding="utf-8",
                )
            return stdout
        raw_path.write_text(proc.stdout, encoding="utf-8")
        if proc.stderr:
            raw_path.with_suffix(raw_path.suffix + ".stderr").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(
                f"Codex command failed with exit code {proc.returncode}: {' '.join(cmd)}\n"
                f"stderr saved next to {raw_path}"
            )
        return proc.stdout


def build_publisher_prompt(
    args: argparse.Namespace,
    run_dir: Path,
    sandbox_dir: Path,
    publication_staging: Path,
    author_message: str,
) -> str:
    return f"""The author asked:

<author_message>
{author_message}
</author_message>

Use the APP skills from {args.protocol_repo}/skills/ when relevant, especially:
- publish-paper
- reproduce-results
- prepare-staging
- define-paper-agent
- validate-publication
- release-outcome
- extract-chat-context when the author wants chat/session context

Current working directory is the source paper folder:
{args.example_path}

Hard guardrails:
- Dev-sandbox mode only.
- No GitHub publication.
- No public repo creation.
- No APP_PUBLICATION.json.
- No .publications.md APP compliance record.
- Create the dev-sandbox publication candidate at ./publication-staging/.
- Treat ./publication-staging/ as the effective staged root.
- Do not write runner artifacts yourself. The runner will write the final dev-sandbox outcome note at: {sandbox_dir / "DEV_SANDBOX_RESULT.md"} after accepting your final message.
- Keep runner artifacts outside the candidate under: {run_dir}
- Do not modify {args.protocol_repo}.
- Treat these guardrails as standing instructions. Do not ask the author to
  reconfirm them at every checkpoint, and do not repeat the full forbidden
  artifact list unless it is directly relevant to the current decision or final
  outcome.
- Follow the modular APP workflow: reproduce/check existing results first, prepare staging second, define paper-agent docs third, run full validation fourth, then use release-outcome only for final review/freeze and dev-sandbox outcome.
- Work in bounded conversational checkpoints. In a single publishing-agent turn, complete at most one major checkpoint: intake/questions, reproduce-results summary, staging plan, staging creation summary, paper-agent docs review, validation/test summary, or final dev-sandbox result.
- Stop and ask the author for the next approval or decision whenever the next checkpoint would depend on author judgment. Do not continue from reproduction into staging, or from staging into paper-agent docs, in the same turn unless the author already explicitly approved that transition in the immediately preceding message.
- Ask for concrete author decisions about the next checkpoint. Avoid ritual
  confirmations such as "please confirm this is still dev-sandbox only" unless
  the author has requested a release-like action or the next step could create a
  forbidden artifact.
- If a checkpoint requires long file operations, do the smallest useful slice, report concrete files/results/blockers, and leave `APP_CHAT_STATUS: continue` rather than trying to finish the whole APP workflow in one response.
- In reproduce-results, check existing results only. Do not propose improvements, new experiments, or new results.
- Ask the author explicitly whether they want publication-safe chat/session context included. If yes and they do not have it ready, provide extraction instructions or use extract-chat-context when available.
- Explain APP concepts in plain language; do not assume the author knows PROTOCOL.md.

End every response with this machine-readable footer:

APP_CHAT_STATUS: continue | ready_for_evaluation | blocked
APP_PHASE: <short phase>
APP_SKILLS_USED: <comma-separated skill/file names>

Only use `APP_CHAT_STATUS: ready_for_evaluation` when all are true:
- `./publication-staging/` exists.
- No `APP_PUBLICATION.json` exists.
- No `.publications.md` exists.
- The final footer phase is exactly `APP_PHASE: final-dev-sandbox-result`.
- Your final message contains the dev-sandbox outcome summary, including remaining blockers and confirmation that no real-publication artifacts were created.
"""


def build_author_opening_prompt(author_prompt: str) -> str:
    return f"""Use this role prompt as your source of truth:

<simulated_author_prompt>
{author_prompt}
</simulated_author_prompt>

You are talking directly to a publishing agent. Start the conversation as the user/author. Ask the publishing agent to help prepare this paper through the APP workflow. Include enough initial intent to make the conversation realistic, but let the publishing agent ask follow-up questions.

Standing boundary: approve only dev-sandbox outcomes. Do not approve real public release, GitHub publication, APP_PUBLICATION.json, or .publications.md. Mention this boundary once in the opening request if it fits naturally; after that, assume the publishing agent remembers it. Do not restate the full boundary in routine checkpoint approvals unless the publishing agent asks for or implies a real public release, GitHub action, APP_PUBLICATION.json, or .publications.md.

License behavior: if the publishing agent asks about license/reuse terms, answer with a concrete license choice grounded in the example prompt or source folder. If the prompt/source folder does not specify a license, choose a reasonable test license instead of deferring: prefer MIT for code and CC-BY-4.0 for paper/data, or a combined root LICENSE that states component-specific terms. Say that the license choice is for the dev-sandbox test package the first time you choose it; do not repeat that caveat in every later approval unless licensing or release status is the topic.

Dependency behavior: if validation is blocked by missing packages or tools, authorize safe project-scoped installation attempts when the run environment allows them. Tell the publishing agent to ask before risky, global, proprietary, credentialed, unusually large, or system-invasive installs, and to record any install commands and failures.

Conversation style: behave like a busy but thoughtful paper author. Respond to
the agent's actual question, make concrete decisions, add domain-specific
corrections when needed, and avoid boilerplate. A short approval can be one or
two sentences plus the footer.

End every response with this machine-readable footer:

APP_CHAT_STATUS: continue | final_signoff | blocked
APP_PHASE: <short phase>
APP_SKILLS_USED: <comma-separated skill/file names or none>
"""


def build_author_reply_prompt(publisher_message: str) -> str:
    return f"""The publishing agent says:

<publishing_agent_message>
{publisher_message}
</publishing_agent_message>

Reply as the author. Respond to the publishing agent's concrete question or
request. Keep the established dev-sandbox boundary in mind silently; do not
repeat the full guardrail list during ordinary approvals. Restate or enforce the
boundary only if the publishing agent proposes something release-like, asks for
public approval, or seems confused about the allowed scope.

Use natural author behavior: make decisions, answer briefly when the question is
straightforward, and add substantive paper-specific corrections or preferences
only when they matter.

End every response with this machine-readable footer:

APP_CHAT_STATUS: continue | final_signoff | blocked
APP_PHASE: <short phase>
APP_SKILLS_USED: <comma-separated skill/file names or none>
"""


def build_resume_prompt(speaker: str, other: str, other_message: str) -> str:
    return f"""Message from {other}:

<{other}_message>
{other_message}
</{other}_message>

Continue the conversation as {speaker}. Reply to {other}. The dev-sandbox
constraints are already established standing instructions; follow them without
repeating them unless the current message raises a release-scope issue.

If you are the publishing agent, keep this turn bounded to one major checkpoint. Do not combine reproduction, staging, paper-agent docs, validation, and final outcome in one turn. When you finish the current checkpoint, summarize it briefly, ask the author for the next needed approval or decision, and use `APP_CHAT_STATUS: continue` unless the final dev-sandbox result is actually complete. Ask for the next concrete decision; do not ask the author to reconfirm the standing sandbox guardrails.

If you are the author, approve, revise, or reject the requested checkpoint in a
human way. Avoid boilerplate guardrail repetition unless you are correcting a
scope problem.

End with the required APP_CHAT_STATUS, APP_PHASE, and APP_SKILLS_USED footer."""


def build_completion_repair_prompt(checks: dict[str, Any]) -> str:
    return f"""The runner checked your completion claim and did not accept it.

Completion check:

```json
{json.dumps(checks, indent=2, sort_keys=True)}
```

Continue as publishing-agent. Repair the missing final dev-sandbox procedure if possible. Only claim completion when:
- `APP_CHAT_STATUS: ready_for_evaluation`
- `APP_PHASE: final-dev-sandbox-result`
- `publication-staging/` exists in the source paper folder
- no `APP_PUBLICATION.json` exists
- no `.publications.md` exists
- your message contains the final dev-sandbox outcome summary. The runner writes `sandbox/DEV_SANDBOX_RESULT.md` after accepting your final message.

If you cannot repair it, explain the blocker and use `APP_CHAT_STATUS: blocked`."""


def build_evaluator_prompt(
    args: argparse.Namespace,
    run_dir: Path,
    sandbox_dir: Path,
    publication_staging: Path,
) -> str:
    return f"""You are the APP evaluator for a direct Codex-session simulate-publication run.

Inspect these artifacts:
- Chat history: {run_dir / "chat-history.md"}
- Run summary: {run_dir / "run-summary.json"}
- Sandbox: {sandbox_dir}
- Publication candidate tree: {publication_staging}
- Protocol repo: {args.protocol_repo}

Evaluate:
- What worked well in the protocol and skills.
- Whether the direct Codex-session conversation was realistic and whether author decisions shaped the staged output.
- Whether the conversation captured skills/files used.
- Where the publishing agent got confused.
- Whether dev-sandbox mode stayed isolated from real publishing.
- Whether `publication-staging/` was treated as the effective root.
- Whether validation and paper-agent testing were meaningful.
- Whether the modular step boundaries were followed: reproduce-results, prepare-staging, define-paper-agent, validate-publication, release-outcome.
- Whether reproduce-results focused on existing results only and avoided suggesting improvements/new results.
- Whether the publishing agent explicitly asked about chat/session context and explained extraction options.
- Whether the publishing agent explained APP concepts and the staging folder in author-friendly language.
- Whether the publishing agent attempted direct figure/table reproduction before downgrading to selected/manual reproduction.
- Whether it created `code/figure-reproduction/README.md` and per-figure scripts, and whether those scripts were validated independently when possible.
- Whether `AGENTS.md` and README point to the figure reproduction map and accurately summarize statuses.
- Whether author interaction burden was reasonable.
- Whether outputs are complete enough for a reader agent.

Distinguish protocol/spec problems, skill instruction problems, template problems, example-project problems, runner/script problems, and publishing-agent execution mistakes.

Return a concise report with run metadata, outcome summary, what worked well, things needing improvement with priority, concrete suggested changes with protocol_repo paths where applicable, and open questions."""


def append_turn(transcript: Path, turn: int, speaker: str, message: str, output_file: Path) -> None:
    skills = extract_skills(message)
    skills_line = ", ".join(skills) if skills else "not detected"
    append_text(
        transcript,
        f"\n## Turn {turn} - {speaker}\n\n"
        f"Time: {iso_now()}\n\n"
        f"Output file: `{output_file}`\n\n"
        f"Detected skills/files: {skills_line}\n\n"
        f"{message.rstrip()}\n",
    )


def record_turn(
    *,
    transcript: Path,
    events_path: Path,
    html_path: Path,
    example: str,
    timestamp: str,
    auto_refresh: bool,
    turn: int,
    speaker: str,
    message: str,
    output_file: Path,
) -> None:
    append_turn(transcript, turn, speaker, message, output_file)
    skills = extract_skills(message)
    append_jsonl(
        events_path,
        {
            "kind": "turn",
            "turn": turn,
            "speaker": speaker,
            "time": iso_now(),
            "output_file": str(output_file),
            "skills": ", ".join(skills) if skills else "not detected",
            "message": message,
        },
    )
    render_live_html(
        html_path=html_path,
        events_path=events_path,
        example=example,
        timestamp=timestamp,
        auto_refresh=auto_refresh,
    )


def record_runner_event(
    *,
    transcript: Path,
    events_path: Path,
    html_path: Path,
    example: str,
    timestamp: str,
    auto_refresh: bool,
    title: str,
    payload: dict[str, Any],
) -> None:
    message = f"```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"
    append_text(
        transcript,
        f"\n## {title}\n\nTime: {iso_now()}\n\n{message}\n",
    )
    append_jsonl(
        events_path,
        {
            "kind": "runner",
            "speaker": title,
            "time": iso_now(),
            "message": message,
        },
    )
    render_live_html(
        html_path=html_path,
        events_path=events_path,
        example=example,
        timestamp=timestamp,
        auto_refresh=auto_refresh,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", help="Example folder name under data/example-papers/")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--protocol-repo", default="code/protocol_repo", help="Protocol repo path")
    parser.add_argument("--examples-root", default="data/example-papers", help="Examples root")
    parser.add_argument("--working-root", default="working/simulate-publication", help="Run output root")
    parser.add_argument("--timestamp", default=None, help="Run id timestamp; defaults to now")
    parser.add_argument("--max-turns", type=int, default=80, help="Maximum total agent turns before evaluation")
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--sandbox", default="danger-full-access")
    parser.add_argument("--approval", default="never")
    parser.add_argument("--extra-codex-arg", action="append", default=[])
    parser.add_argument("--turn-timeout", type=int, default=1200, help="Seconds before a single Codex turn is marked blocked")
    parser.add_argument("--no-eval", action="store_true", help="Skip evaluator pass")
    parser.add_argument("--no-html-refresh", action="store_true", help="Disable live HTML auto-refresh")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    args.workspace = str(workspace)
    args.protocol_repo = str((workspace / args.protocol_repo).resolve())
    examples_root = workspace / args.examples_root
    example_path = examples_root / args.example
    args.example_path = str(example_path.resolve())
    if not example_path.is_dir():
        raise SystemExit(f"Example folder not found: {example_path}")

    timestamp = args.timestamp or now_stamp()
    run_dir = workspace / args.working_root / args.example / timestamp
    sandbox_dir = run_dir / "sandbox"
    logs_dir = run_dir / "logs"
    publication_staging = example_path / "publication-staging"
    source_working_dir = example_path / "working"
    prompt_path = workspace / args.working_root / args.example / "simulated-author-prompt.md"
    if not prompt_path.is_file():
        raise SystemExit(f"Missing simulated-author prompt: {prompt_path}")

    if run_dir.exists():
        raise SystemExit(f"Run output folder already exists, refusing to overwrite it: {run_dir}")

    if publication_staging.exists() or publication_staging.is_symlink():
        if publication_staging.is_dir() and not publication_staging.is_symlink():
            shutil.rmtree(publication_staging)
        else:
            publication_staging.unlink()

    if source_working_dir.exists() or source_working_dir.is_symlink():
        if source_working_dir.is_dir() and not source_working_dir.is_symlink():
            shutil.rmtree(source_working_dir)
        else:
            source_working_dir.unlink()

    sandbox_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    transcript = run_dir / "chat-history.md"
    live_events = run_dir / "live-events.jsonl"
    live_html = run_dir / "chat-history.html"
    write_text(
        transcript,
        "# Simulate Publication Direct Codex Chat History\n\n"
        f"Example: `{args.example}`\n"
        f"Run: `{timestamp}`\n"
        "Mode: `dev-sandbox`\n"
        f"Publishing cwd: `{example_path.resolve()}`\n"
        f"Publication candidate: `{publication_staging.resolve()}`\n"
        "Conversation mode: two persistent Codex CLI sessions\n",
    )
    render_live_html(
        html_path=live_html,
        events_path=live_events,
        example=args.example,
        timestamp=timestamp,
        auto_refresh=not args.no_html_refresh,
    )

    author_runner = CodexSessionRunner(
        codex_bin=args.codex_bin,
        workspace=example_path.resolve(),
        logs_dir=logs_dir,
        sandbox=args.sandbox,
        approval=args.approval,
        model=args.model,
        extra_args=args.extra_codex_arg,
        turn_timeout=args.turn_timeout,
    )
    publisher_runner = CodexSessionRunner(
        codex_bin=args.codex_bin,
        workspace=example_path.resolve(),
        logs_dir=logs_dir,
        sandbox=args.sandbox,
        approval=args.approval,
        model=args.model,
        extra_args=args.extra_codex_arg,
        turn_timeout=args.turn_timeout,
    )
    evaluator_runner = CodexSessionRunner(
        codex_bin=args.codex_bin,
        workspace=workspace,
        logs_dir=logs_dir,
        sandbox=args.sandbox,
        approval=args.approval,
        model=args.model,
        extra_args=args.extra_codex_arg,
        turn_timeout=args.turn_timeout,
    )

    started_at = iso_now()
    author_prompt = read_text(prompt_path)
    author_session, author_msg, author_output = author_runner.start(
        "simulated-author",
        build_author_opening_prompt(author_prompt),
    )
    record_turn(
        transcript=transcript,
        events_path=live_events,
        html_path=live_html,
        example=args.example,
        timestamp=timestamp,
        auto_refresh=not args.no_html_refresh,
        turn=1,
        speaker="simulated-author",
        message=author_msg,
        output_file=author_output,
    )

    publisher_session, publisher_msg, publisher_output = publisher_runner.start(
        "publishing-agent",
        build_publisher_prompt(args, run_dir, sandbox_dir, publication_staging, author_msg),
    )
    record_turn(
        transcript=transcript,
        events_path=live_events,
        html_path=live_html,
        example=args.example,
        timestamp=timestamp,
        auto_refresh=not args.no_html_refresh,
        turn=2,
        speaker="publishing-agent",
        message=publisher_msg,
        output_file=publisher_output,
    )

    turn = 3
    publishing_turns = 1
    author_turns = 1
    final_status = "max_turns_reached"
    last_msg = publisher_msg
    final_completion_check: dict[str, Any] | None = None
    initial_publisher_footer = extract_footer(publisher_msg)
    if initial_publisher_footer["status"] == "blocked":
        final_status = "blocked_by_publishing_agent"
        turn = args.max_turns + 1
    while turn <= args.max_turns:
        author_msg, author_output = author_runner.resume(
            "simulated-author",
            author_session,
            turn,
            build_author_reply_prompt(last_msg),
        )
        author_turns += 1
        record_turn(
            transcript=transcript,
            events_path=live_events,
            html_path=live_html,
            example=args.example,
            timestamp=timestamp,
            auto_refresh=not args.no_html_refresh,
            turn=turn,
            speaker="simulated-author",
            message=author_msg,
            output_file=author_output,
        )
        turn += 1
        author_footer = extract_footer(author_msg)
        if author_footer["status"] == "blocked":
            final_status = "blocked_by_simulated_author"
            break

        publisher_msg, publisher_output = publisher_runner.resume(
            "publishing-agent",
            publisher_session,
            turn,
            build_resume_prompt("publishing agent", "author", author_msg),
        )
        publishing_turns += 1
        record_turn(
            transcript=transcript,
            events_path=live_events,
            html_path=live_html,
            example=args.example,
            timestamp=timestamp,
            auto_refresh=not args.no_html_refresh,
            turn=turn,
            speaker="publishing-agent",
            message=publisher_msg,
            output_file=publisher_output,
        )
        turn += 1

        publisher_footer = extract_footer(publisher_msg)
        if publisher_footer["status"] == "blocked":
            final_status = "blocked_by_publishing_agent"
            break
        if publisher_footer["status"] in {"ready_for_evaluation", "finished", "complete"}:
            final_completion_check = completion_check(sandbox_dir, publication_staging, publisher_msg)
            record_runner_event(
                transcript=transcript,
                events_path=live_events,
                html_path=live_html,
                example=args.example,
                timestamp=timestamp,
                auto_refresh=not args.no_html_refresh,
                title="Runner Completion Check",
                payload=final_completion_check,
            )
            if final_completion_check["accepted"]:
                final_status = "ready_for_evaluation"
                break
            if turn > args.max_turns:
                final_status = "completion_claim_failed_artifact_check"
                break
            publisher_msg, publisher_output = publisher_runner.resume(
                "publishing-agent",
                publisher_session,
                turn,
                build_completion_repair_prompt(final_completion_check),
            )
            publishing_turns += 1
            record_turn(
                transcript=transcript,
                events_path=live_events,
                html_path=live_html,
                example=args.example,
                timestamp=timestamp,
                auto_refresh=not args.no_html_refresh,
                turn=turn,
                speaker="publishing-agent",
                message=publisher_msg,
                output_file=publisher_output,
            )
            turn += 1
            final_completion_check = completion_check(sandbox_dir, publication_staging, publisher_msg)
            record_runner_event(
                transcript=transcript,
                events_path=live_events,
                html_path=live_html,
                example=args.example,
                timestamp=timestamp,
                auto_refresh=not args.no_html_refresh,
                title="Runner Completion Recheck",
                payload=final_completion_check,
            )
            if final_completion_check["accepted"]:
                final_status = "ready_for_evaluation"
            else:
                final_status = "completion_claim_failed_artifact_check"
            break
        last_msg = publisher_msg

    ended_at = iso_now()
    dev_result = sandbox_dir / "DEV_SANDBOX_RESULT.md"
    summary = {
        "example": args.example,
        "example_path": str(example_path),
        "protocol_repo_path": args.protocol_repo,
        "run_id": timestamp,
        "mode": "dev-sandbox",
        "conversation_mode": "two_persistent_codex_cli_sessions",
        "started_at": started_at,
        "ended_at": ended_at,
        "sandbox_path": str(sandbox_dir),
        "publication_staging_path": str(publication_staging),
        "chat_history_path": str(transcript),
        "chat_history_html_path": str(live_html),
        "live_events_path": str(live_events),
        "publishing_agent_session_id": publisher_session,
        "simulated_author_session_id": author_session,
        "publishing_agent_turns": publishing_turns,
        "simulated_author_turns": author_turns,
        "completion_status": final_status,
        "completion_check": final_completion_check,
        "dev_sandbox_result_exists": dev_result.is_file(),
        "publication_staging_exists": publication_staging.is_dir(),
        "guardrail_artifacts": {
            "app_publication_json_exists": any(sandbox_dir.rglob("APP_PUBLICATION.json"))
            or (publication_staging.exists() and any(publication_staging.rglob("APP_PUBLICATION.json"))),
            "publications_md_exists": any(sandbox_dir.rglob(".publications.md"))
            or (publication_staging.exists() and any(publication_staging.rglob(".publications.md"))),
        },
        "logs_dir": str(logs_dir),
    }
    summary_path = run_dir / "run-summary.json"
    write_text(summary_path, json_dumps(summary))

    if not args.no_eval:
        report, report_output = evaluator_runner.one_shot(
            "evaluator",
            build_evaluator_prompt(args, run_dir, sandbox_dir, publication_staging),
        )
        write_text(run_dir / "evaluation-report.md", report)
        summary["evaluation_report_path"] = str(run_dir / "evaluation-report.md")
        summary["evaluator_output_path"] = str(report_output)
        write_text(summary_path, json_dumps(summary))

    print(json_dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
