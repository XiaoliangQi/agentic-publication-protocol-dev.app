#!/usr/bin/env python3
"""Run a direct Codex chat to test an APP paper-agent.

The script starts a grad-student user session and a paper-agent session. Both
sessions are launched with their working directory set to the APP publication
staging folder so local paths are realistic; only the paper-agent prompt tells
the agent to follow AGENTS.md/CLAUDE.md. The conversation is recorded as
Markdown, live-refreshing HTML, JSONL events, raw Codex logs, and a final
evaluator report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))

from _shared.reader_simulator import build_reader_opening_prompt, build_reader_reply_prompt


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
STATUS_RE = re.compile(
    r"PAPER_AGENT_TEST_STATUS\s*:\s*(continue|finished|blocked)",
    re.IGNORECASE,
)
PHASE_RE = re.compile(r"PAPER_AGENT_TEST_PHASE\s*:\s*([^\n\r]+)", re.IGNORECASE)


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
    preferred = {"session_id", "conversation_id", "thread_id", "rollout_id"}
    fallback: str | None = None
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            for key, value in event.items():
                if key in preferred and isinstance(value, str) and UUID_RE.fullmatch(value):
                    return value
            for value in iter_values(event):
                if isinstance(value, str):
                    match = UUID_RE.search(value)
                    if match and fallback is None:
                        fallback = match.group(0)
    return fallback


def extract_footer(text: str) -> dict[str, str | None]:
    status = STATUS_RE.search(text)
    phase = PHASE_RE.search(text)
    return {
        "status": status.group(1).strip().lower() if status else None,
        "phase": phase.group(1).strip().lower() if phase else None,
    }


def extract_files(text: str) -> list[str]:
    known = {
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "PROTOCOL.md",
        "SKILL.md",
        "code/figure-reproduction/README.md",
        "DEV_SANDBOX_RESULT.md",
    }
    return [item for item in sorted(known) if item in text]


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


def load_live_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
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
    paper_name: str,
    timestamp: str,
    auto_refresh: bool,
) -> None:
    refresh = '<meta http-equiv="refresh" content="5">\n' if auto_refresh else ""
    cards: list[str] = []
    for event in load_live_events(events_path):
        kind = event.get("kind", "turn")
        speaker = str(event.get("speaker", "runner"))
        turn = event.get("turn")
        time = html.escape(str(event.get("time", "")))
        files = html.escape(str(event.get("files", "")))
        message = str(event.get("message", ""))
        title = f"Round {event.get('round')} · Turn {turn} - {speaker}" if turn else speaker
        css_kind = "runner" if kind != "turn" else speaker
        cards.append(
            f"""
<section class="card {html.escape(css_kind)}">
  <div class="meta">
    <span>{html.escape(title)}</span>
    <span>{time}</span>
  </div>
  {f'<div class="files">Mentioned files: {files}</div>' if files else ''}
  <div class="message">
    {render_markdownish(message)}
  </div>
</section>
"""
        )

    body = "\n".join(cards) if cards else '<p class="empty">Waiting for the first turn...</p>'
    write_text(
        html_path,
        f"""<!doctype html>
<html lang="en">
<head>
{refresh}<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paper-Agent Test - {html.escape(paper_name)} - {html.escape(timestamp)}</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f7f8fa;
  --panel: #ffffff;
  --ink: #1f2933;
  --muted: #667085;
  --line: #d8dee8;
  --user: #e9f2ff;
  --agent: #eef8ed;
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
h1 {{ margin: 0; font-size: 20px; letter-spacing: 0; }}
.sub {{ margin-top: 4px; color: var(--muted); font-size: 13px; }}
main {{ max-width: 980px; margin: 0 auto; padding: 20px; }}
.card {{
  margin: 0 0 16px;
  padding: 16px 18px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}}
.grad-student-user {{ border-left: 5px solid #4088d5; background: var(--user); }}
.paper-agent {{ border-left: 5px solid #4f9d5d; background: var(--agent); }}
.runner {{ border-left: 5px solid #d08b2c; background: var(--runner); }}
.meta {{
  display: flex;
  gap: 12px;
  justify-content: space-between;
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 8px;
}}
.files {{ color: var(--muted); font-size: 13px; margin-bottom: 10px; }}
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
  <h1>Paper-Agent Direct Chat Test</h1>
  <div class="sub">Paper: {html.escape(paper_name)} · Run: {html.escape(timestamp)} · Auto-refresh: {'on' if auto_refresh else 'off'}</div>
</header>
<main>
{body}
</main>
</body>
</html>
""",
    )


class CodexSessionRunner:
    def __init__(
        self,
        *,
        codex_bin: str,
        logs_dir: Path,
        sandbox: str,
        model: str | None,
        extra_args: list[str],
        turn_timeout: int | None,
    ) -> None:
        self.codex_bin = codex_bin
        self.logs_dir = logs_dir
        self.sandbox = sandbox
        self.model = model
        self.extra_args = extra_args
        self.turn_timeout = turn_timeout

    def _base_cmd(self, cwd: Path) -> list[str]:
        cmd = [
            self.codex_bin,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            str(cwd),
            "-s",
            self.sandbox,
        ]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.extend(self.extra_args)
        return cmd

    def start(self, name: str, cwd: Path, prompt: str) -> tuple[str, str, Path]:
        output_path = self.logs_dir / f"{name}-turn-001-last-message.md"
        cmd = self._base_cmd(cwd) + ["-o", str(output_path), "-"]
        raw = self._run(cmd, prompt, self.logs_dir / f"{name}-turn-001.jsonl", cwd)
        session_id = extract_session_id(raw)
        if not session_id:
            raise RuntimeError(f"Could not discover Codex session id for {name}. See logs.")
        return session_id, read_text(output_path), output_path

    def resume(
        self,
        name: str,
        session_id: str,
        cwd: Path,
        turn: int,
        prompt: str,
    ) -> tuple[str, Path]:
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
        self._run(cmd, prompt, self.logs_dir / f"{name}-turn-{turn:03d}.jsonl", cwd)
        return read_text(output_path), output_path

    def one_shot(self, name: str, cwd: Path, prompt: str) -> tuple[str, Path]:
        output_path = self.logs_dir / f"{name}-last-message.md"
        cmd = self._base_cmd(cwd) + ["-o", str(output_path), "-"]
        self._run(cmd, prompt, self.logs_dir / f"{name}.jsonl", cwd)
        return read_text(output_path), output_path

    def _run(self, cmd: list[str], prompt: str, raw_path: Path, cwd: Path) -> str:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
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
            raw_path.with_suffix(raw_path.suffix + ".timeout").write_text(
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
                speaker = "paper-agent" if "paper-agent" in raw_path.name else "grad-student user"
                output_path.write_text(
                    f"The {speaker} turn timed out after {self.turn_timeout} seconds before producing a complete response.\n\n"
                    "PAPER_AGENT_TEST_STATUS: blocked\n"
                    "PAPER_AGENT_TEST_PHASE: runner-timeout\n"
                    "PAPER_AGENT_TEST_TOPICS: timeout\n",
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


def discover_latest_paper(workspace: Path) -> Path:
    candidates = [
        path
        for pattern in ["data/example-papers/*/publication-staging"]
        for path in workspace.glob(pattern)
        if (path / "AGENTS.md").is_file()
    ]
    if not candidates:
        raise SystemExit("No APP staging folder found. Pass a paper folder explicitly.")
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def infer_paper_name(paper_path: Path) -> str:
    parts = paper_path.parts
    for marker in ("simulate-publication", "improve-app"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return parts[index + 1]
    if paper_path.name == "publication-staging" and paper_path.parent.name:
        return paper_path.parent.name
    if paper_path.name == "publication-staging" and len(paper_path.parts) >= 3:
        return paper_path.parent.parent.parent.name
    return paper_path.name


def validate_paper_folder(paper_path: Path) -> None:
    if not paper_path.is_dir():
        raise SystemExit(f"Paper folder not found: {paper_path}")
    missing = [name for name in ["AGENTS.md", "README.md", "paper"] if not (paper_path / name).exists()]
    if missing:
        raise SystemExit(f"Paper folder does not look APP-ready; missing: {', '.join(missing)}")


def build_user_opening_prompt(max_rounds: int) -> str:
    return build_reader_opening_prompt(
        max_rounds=max_rounds,
        footer_prefix="PAPER_AGENT_TEST",
        counterpart_label="paper-agent",
        access_mode="package",
    )


def build_paper_agent_prompt(user_message: str) -> str:
    return f"""You are the paper agent for this publication-staging folder.

Follow the local `AGENTS.md` and `CLAUDE.md` instructions if present. 

The user starts with:

<grad_student_user_message>
{user_message}
</grad_student_user_message>

End every response with this footer:

PAPER_AGENT_TEST_STATUS: continue | finished | blocked
PAPER_AGENT_TEST_PHASE: <short phase>
PAPER_AGENT_TEST_TOPICS: <comma-separated topics>
"""


def build_user_reply_prompt(paper_message: str, round_index: int, max_rounds: int) -> str:
    return build_reader_reply_prompt(
        agent_message=paper_message,
        round_index=round_index,
        max_rounds=max_rounds,
        footer_prefix="PAPER_AGENT_TEST",
        counterpart_label="paper-agent",
        access_mode="package",
    )


def build_paper_reply_prompt(user_message: str) -> str:
    return f"""Message from grad-student-user:

<grad_student_user_message>
{user_message}
</grad_student_user_message>

Continue as paper-agent. 
End every response with this footer:

PAPER_AGENT_TEST_STATUS: continue | finished | blocked
PAPER_AGENT_TEST_PHASE: <short phase>
PAPER_AGENT_TEST_TOPICS: <comma-separated topics>
"""


def build_evaluator_prompt(args: argparse.Namespace, run_dir: Path, paper_path: Path) -> str:
    return f"""You are the evaluator for a direct paper-agent test.

Inspect:
- Chat history: {run_dir / "chat-history.md"}
- Run summary: {run_dir / "run-summary.json"}
- Paper folder under test: {paper_path}
- Protocol repo: {args.protocol_repo}

Evaluate:
- whether the grad-student user behaved realistically;
- whether the paper-agent answered from `AGENTS.md`, `CLAUDE.md`, `README.md`, paper files, code, data, and figure-reproduction notes;
- whether answers were concrete, grounded, and useful for understanding;
- whether reproduction guidance was actionable and honest about blockers;
- whether the paper-agent could help with a quick next-step research question without overclaiming;
- whether any answers invented facts or failed to acknowledge missing information;
- whether the APP paper package itself needs improvement;
- whether `PROTOCOL.md`, templates, publish-paper, reproduce-results, prepare-staging, define-paper-agent, validate-publication, release-outcome, or load-paper-agent skills should change.

Return a concise report with run metadata, outcome summary, what worked well, issues by priority, concrete suggested changes with paths where possible, and open questions."""


def append_turn(transcript: Path, round_index: int, turn: int, speaker: str, message: str, output_file: Path) -> None:
    files = extract_files(message)
    files_line = ", ".join(files) if files else "not detected"
    append_text(
        transcript,
        f"\n## Round {round_index} · Turn {turn} - {speaker}\n\n"
        f"Time: {iso_now()}\n\n"
        f"Output file: `{output_file}`\n\n"
        f"Mentioned files: {files_line}\n\n"
        f"{message.rstrip()}\n",
    )


def record_turn(
    *,
    transcript: Path,
    events_path: Path,
    html_path: Path,
    paper_name: str,
    timestamp: str,
    auto_refresh: bool,
    round_index: int,
    turn: int,
    speaker: str,
    message: str,
    output_file: Path,
) -> None:
    append_turn(transcript, round_index, turn, speaker, message, output_file)
    files = extract_files(message)
    append_jsonl(
        events_path,
        {
            "kind": "turn",
            "round": round_index,
            "turn": turn,
            "speaker": speaker,
            "time": iso_now(),
            "output_file": str(output_file),
            "files": ", ".join(files) if files else "not detected",
            "message": message,
        },
    )
    render_live_html(
        html_path=html_path,
        events_path=events_path,
        paper_name=paper_name,
        timestamp=timestamp,
        auto_refresh=auto_refresh,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_folder", nargs="?", help="APP publication/staging folder to test")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--protocol-repo", default="code/protocol_repo", help="Protocol repo path")
    parser.add_argument("--working-root", default="working/test-paper-agent", help="Run output root")
    parser.add_argument("--timestamp", default=None, help="Run id timestamp; defaults to now")
    parser.add_argument("--max-rounds", type=int, default=15, help="Maximum user/paper-agent exchanges")
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--sandbox", default="danger-full-access")
    parser.add_argument("--extra-codex-arg", action="append", default=[])
    parser.add_argument("--turn-timeout", type=int, default=900, help="Seconds before a single Codex turn is marked blocked")
    parser.add_argument("--no-eval", action="store_true", help="Skip evaluator pass")
    parser.add_argument("--no-html-refresh", action="store_true", help="Disable live HTML auto-refresh")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    args.workspace = str(workspace)
    args.protocol_repo = str((workspace / args.protocol_repo).resolve())
    paper_path = Path(args.paper_folder).expanduser() if args.paper_folder else discover_latest_paper(workspace)
    if not paper_path.is_absolute():
        paper_path = workspace / paper_path
    paper_path = paper_path.resolve()
    validate_paper_folder(paper_path)

    timestamp = args.timestamp or now_stamp()
    paper_name = infer_paper_name(paper_path)
    run_dir = workspace / args.working_root / paper_name / timestamp
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    transcript = run_dir / "chat-history.md"
    live_events = run_dir / "live-events.jsonl"
    live_html = run_dir / "chat-history.html"
    write_text(
        transcript,
        "# Paper-Agent Direct Codex Chat History\n\n"
        f"Paper: `{paper_name}`\n"
        f"Paper folder: `{paper_path}`\n"
        f"Run: `{timestamp}`\n"
        f"Max rounds: `{args.max_rounds}`\n"
        "Conversation mode: two persistent Codex CLI sessions\n",
    )
    render_live_html(
        html_path=live_html,
        events_path=live_events,
        paper_name=paper_name,
        timestamp=timestamp,
        auto_refresh=not args.no_html_refresh,
    )

    runner = CodexSessionRunner(
        codex_bin=args.codex_bin,
        logs_dir=logs_dir,
        sandbox=args.sandbox,
        model=args.model,
        extra_args=args.extra_codex_arg,
        turn_timeout=args.turn_timeout,
    )

    started_at = iso_now()
    user_session, user_msg, user_output = runner.start(
        "grad-student-user",
        paper_path,
        build_user_opening_prompt(args.max_rounds),
    )
    record_turn(
        transcript=transcript,
        events_path=live_events,
        html_path=live_html,
        paper_name=paper_name,
        timestamp=timestamp,
        auto_refresh=not args.no_html_refresh,
        round_index=1,
        turn=1,
        speaker="grad-student-user",
        message=user_msg,
        output_file=user_output,
    )

    paper_session, paper_msg, paper_output = runner.start(
        "paper-agent",
        paper_path,
        build_paper_agent_prompt(user_msg),
    )
    record_turn(
        transcript=transcript,
        events_path=live_events,
        html_path=live_html,
        paper_name=paper_name,
        timestamp=timestamp,
        auto_refresh=not args.no_html_refresh,
        round_index=1,
        turn=2,
        speaker="paper-agent",
        message=paper_msg,
        output_file=paper_output,
    )

    turn = 3
    rounds_completed = 1
    user_turns = 1
    paper_turns = 1
    final_status = "max_rounds_reached"
    last_user_footer = extract_footer(user_msg)
    last_paper_footer = extract_footer(paper_msg)

    for round_index in range(2, args.max_rounds + 1):
        if last_user_footer["status"] in {"finished", "blocked"}:
            final_status = f"user_{last_user_footer['status']}"
            break
        if last_paper_footer["status"] == "blocked":
            final_status = "paper_agent_blocked"
            break

        user_msg, user_output = runner.resume(
            "grad-student-user",
            user_session,
            paper_path,
            turn,
            build_user_reply_prompt(paper_msg, round_index, args.max_rounds),
        )
        user_turns += 1
        record_turn(
            transcript=transcript,
            events_path=live_events,
            html_path=live_html,
            paper_name=paper_name,
            timestamp=timestamp,
            auto_refresh=not args.no_html_refresh,
            round_index=round_index,
            turn=turn,
            speaker="grad-student-user",
            message=user_msg,
            output_file=user_output,
        )
        turn += 1
        last_user_footer = extract_footer(user_msg)
        if last_user_footer["status"] in {"finished", "blocked"}:
            final_status = f"user_{last_user_footer['status']}"
            rounds_completed = round_index
            break

        paper_msg, paper_output = runner.resume(
            "paper-agent",
            paper_session,
            paper_path,
            turn,
            build_paper_reply_prompt(user_msg),
        )
        paper_turns += 1
        record_turn(
            transcript=transcript,
            events_path=live_events,
            html_path=live_html,
            paper_name=paper_name,
            timestamp=timestamp,
            auto_refresh=not args.no_html_refresh,
            round_index=round_index,
            turn=turn,
            speaker="paper-agent",
            message=paper_msg,
            output_file=paper_output,
        )
        turn += 1
        rounds_completed = round_index
        last_paper_footer = extract_footer(paper_msg)
        if last_paper_footer["status"] == "blocked":
            final_status = "paper_agent_blocked"
            break
    else:
        final_status = "max_rounds_reached"

    ended_at = iso_now()
    summary = {
        "paper_name": paper_name,
        "paper_path": str(paper_path),
        "protocol_repo_path": args.protocol_repo,
        "run_id": timestamp,
        "conversation_mode": "two_persistent_codex_cli_sessions",
        "conversation_cwd": str(paper_path),
        "started_at": started_at,
        "ended_at": ended_at,
        "max_rounds": args.max_rounds,
        "rounds_completed": rounds_completed,
        "completion_status": final_status,
        "chat_history_path": str(transcript),
        "chat_history_html_path": str(live_html),
        "live_events_path": str(live_events),
        "logs_dir": str(logs_dir),
        "grad_student_user_session_id": user_session,
        "paper_agent_session_id": paper_session,
        "grad_student_user_turns": user_turns,
        "paper_agent_turns": paper_turns,
        "has_agents_md": (paper_path / "AGENTS.md").is_file(),
        "has_claude_md": (paper_path / "CLAUDE.md").is_file(),
        "has_figure_reproduction_readme": (paper_path / "code" / "figure-reproduction" / "README.md").is_file(),
    }
    summary_path = run_dir / "run-summary.json"
    write_text(summary_path, json_dumps(summary))

    if not args.no_eval:
        report, report_output = runner.one_shot(
            "evaluator",
            workspace,
            build_evaluator_prompt(args, run_dir, paper_path),
        )
        report_path = run_dir / "evaluation-report.md"
        write_text(report_path, report)
        summary["evaluation_report_path"] = str(report_path)
        summary["evaluator_output_path"] = str(report_output)
        write_text(summary_path, json_dumps(summary))

    print(json_dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
