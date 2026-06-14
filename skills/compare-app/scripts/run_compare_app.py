#!/usr/bin/env python3
"""Compare an APP paper agent with a general source-repo agent.

The script runs two independent simulated-reader chats using the shared reader
simulator. One chat talks to the APP paper agent in publication-staging; the
other talks to a general agent in the original source repo. The evaluator sees
only anonymized, randomized transcripts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILLS_ROOT = Path(__file__).resolve().parents[2]
if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))

from _shared.reader_simulator import build_scripted_reader_message


UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
STATUS_RE = re.compile(r"COMPARE_APP_STATUS\s*:\s*(continue|finished|blocked)", re.IGNORECASE)
PHASE_RE = re.compile(r"COMPARE_APP_PHASE\s*:\s*([^\n\r]+)", re.IGNORECASE)
EVALUATOR_WORKSPACE_IGNORE_NAMES = {
    ".DS_Store",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "skills",
    "venv",
    ".venv",
    "working",
}
EVALUATOR_WORKSPACE_IDENTITY_NAMES = {
    ".publications.md",
    "AGENTS.md",
    "APP_PUBLICATION.json",
    "CLAUDE.md",
    "paper-agent-test.md",
    "reproduction-report.md",
    "validation-report.md",
}
EVALUATOR_TEXT_SUFFIXES = {
    ".bib",
    ".json",
    ".m",
    ".md",
    ".py",
    ".tex",
    ".txt",
    ".yaml",
    ".yml",
}
EVALUATOR_TEXT_FILENAMES = {
    ".gitignore",
    "LICENSE",
}
EVALUATOR_TEXT_REDACTIONS = {
    "agentic-publication-protocol": "reproduction protocol",
    "Agentic Publication Protocol": "reproduction protocol",
    "publication-staging/": "neutral-workspace/",
    "publication-staging": "neutral workspace",
    "APP_PUBLICATION.json": "release-manifest.json",
    ".publications.md": "release-notes.md",
    "AGENTS.md": "workspace-guide.md",
    "CLAUDE.md": "workspace-guide.md",
    "APP check": "reproduction check",
    "APP preparation": "preparation",
    "APP reproduction": "reproduction",
    "APP Validation": "Validation",
    "APP artifact": "release artifact",
    "APP state": "workflow state",
}


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


def render_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_markdownish(text: str) -> str:
    paragraphs = [part.strip() for part in text.rstrip().split("\n\n") if part.strip()]
    return "\n".join("<p>" + render_inline_markdown(part).replace("\n", "<br>") + "</p>" for part in paragraphs)


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


def render_live_html(html_path: Path, events_path: Path, title: str, auto_refresh: bool) -> None:
    refresh = '<meta http-equiv="refresh" content="5">\n' if auto_refresh else ""
    cards: list[str] = []
    for event in load_live_events(events_path):
        speaker = html.escape(str(event.get("speaker", "runner")))
        arm = html.escape(str(event.get("arm", "")))
        turn = html.escape(str(event.get("turn", "")))
        time = html.escape(str(event.get("time", "")))
        message = str(event.get("message", ""))
        cards.append(
            f"""<section class="card">
<div class="meta"><span>{arm} {speaker} turn {turn}</span><span>{time}</span></div>
<div class="message">{render_markdownish(message)}</div>
</section>"""
        )
    body = "\n".join(cards) if cards else '<p class="empty">Waiting for turns...</p>'
    write_text(
        html_path,
        f"""<!doctype html>
<html lang="en">
<head>
{refresh}<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7f9; color: #20242c; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 28px 18px; }}
.card {{ background: white; border-left: 5px solid #5277b8; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin: 16px 0; padding: 16px; }}
.meta {{ display: flex; justify-content: space-between; gap: 16px; color: #596273; font-size: 13px; margin-bottom: 10px; }}
code {{ background: #eef1f5; border-radius: 4px; padding: 1px 4px; }}
</style>
</head>
<body><main><h1>{html.escape(title)}</h1>{body}</main></body>
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

    def resume(self, name: str, session_id: str, cwd: Path, turn: int, prompt: str) -> tuple[str, Path]:
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
            if stderr:
                raw_path.with_suffix(raw_path.suffix + ".stderr").write_text(stderr, encoding="utf-8")
            output_path = None
            if "-o" in cmd:
                try:
                    output_path = Path(cmd[cmd.index("-o") + 1])
                except (IndexError, ValueError):
                    output_path = None
            if output_path is not None:
                output_path.write_text(
                    f"The Codex turn timed out after {self.turn_timeout} seconds before producing a complete response.\n\n"
                    "COMPARE_APP_STATUS: blocked\n"
                    "COMPARE_APP_PHASE: runner-timeout\n"
                    "COMPARE_APP_TOPICS: timeout\n",
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


def discover_latest_source(workspace: Path) -> Path:
    candidates = [path.parent for path in workspace.glob("data/example-papers/*/publication-staging") if (path / "AGENTS.md").is_file()]
    if not candidates:
        raise SystemExit("No source folder with publication-staging found. Pass an example name or --source-root.")
    return max(candidates, key=lambda path: (path / "publication-staging").stat().st_mtime).resolve()


def resolve_source_root(workspace: Path, arg: str | None, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
    elif arg:
        candidate = Path(arg).expanduser()
        path = candidate if candidate.exists() else workspace / "data/example-papers" / arg
    else:
        return discover_latest_source(workspace)
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()


def infer_example_name(source_root: Path) -> str:
    return source_root.name or "compare-app-run"


def resolve_paper_path(source_root: Path, staging_root: Path, explicit: str | None, workspace: Path) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = workspace / path
        return path.resolve()
    for path in [staging_root / "paper", source_root / "paper"]:
        if path.exists():
            return path.resolve()
    raise SystemExit("Could not resolve paper files. Pass --paper-path.")


def copy_paper_context(paper_path: Path, dest: Path) -> Path:
    if dest.exists():
        raise SystemExit(f"Reader paper context already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if paper_path.is_dir():
        shutil.copytree(paper_path, dest)
        return dest
    if paper_path.is_file():
        dest.mkdir(parents=True)
        shutil.copy2(paper_path, dest / paper_path.name)
        return dest
    raise SystemExit(f"Paper path not found: {paper_path}")


def label_slug(label: str) -> str:
    return label.lower().replace(" ", "-")


def copy_evaluator_workspace(source: Path, dest: Path, excluded_roots: list[Path] | None = None) -> Path:
    """Copy a workspace to a neutral path so evaluator prompts stay blind."""
    excluded = [path.resolve() for path in (excluded_roots or [])]
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def ignore(directory: str, names: list[str]) -> set[str]:
        directory_path = Path(directory).resolve()
        ignored = set(EVALUATOR_WORKSPACE_IGNORE_NAMES.intersection(names))
        ignored.update(EVALUATOR_WORKSPACE_IDENTITY_NAMES.intersection(names))
        if directory_path == source.resolve() and "AGENTS.md" in names and "README.md" in names:
            ignored.add("README.md")
        for root in excluded:
            if root.parent == directory_path and root.name in names:
                ignored.add(root.name)
        return ignored

    shutil.copytree(source, dest, ignore=ignore, symlinks=True)
    redact_evaluator_workspace(dest)
    return dest


def should_redact_text(path: Path) -> bool:
    return path.suffix in EVALUATOR_TEXT_SUFFIXES or path.name in EVALUATOR_TEXT_FILENAMES


def redact_evaluator_workspace(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or not should_redact_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        redacted = text
        for old, new in EVALUATOR_TEXT_REDACTIONS.items():
            redacted = redacted.replace(old, new)
        if redacted != text:
            path.write_text(redacted, encoding="utf-8")


def resolve_existing_run(workspace: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    if not path.is_dir():
        raise SystemExit(f"Existing compare-app run not found: {path}")
    if not (path / "run-summary.json").is_file():
        raise SystemExit(f"Existing compare-app run is missing run-summary.json: {path}")
    return path


def load_reused_general_baseline(existing_run: Path) -> tuple[list[str], Path, dict[str, Any]]:
    summary = json.loads(read_text(existing_run / "run-summary.json"))
    question_script = Path(summary.get("question_script_path", existing_run / "question-script.json"))
    if not question_script.is_absolute():
        question_script = existing_run / question_script
    if not question_script.is_file():
        question_script = existing_run / "question-script.json"
    if not question_script.is_file():
        raise SystemExit(f"Existing run is missing question-script.json: {existing_run}")
    questions = json.loads(read_text(question_script))
    if not isinstance(questions, list) or not all(isinstance(item, str) and item.strip() for item in questions):
        raise SystemExit(f"Existing question script is not a JSON string array: {question_script}")
    general_transcript = existing_run / "general-agent-chat-history.md"
    if not general_transcript.is_file():
        raise SystemExit(f"Existing run is missing general-agent-chat-history.md: {existing_run}")
    return [item.strip() for item in questions], general_transcript, summary


def validate_inputs(source_root: Path, staging_root: Path, paper_path: Path) -> None:
    if not source_root.is_dir():
        raise SystemExit(f"Source root not found: {source_root}")
    if not staging_root.is_dir():
        raise SystemExit(f"Staging root not found: {staging_root}")
    if source_root.resolve() == staging_root.resolve():
        raise SystemExit("Source root and staging root must be different.")
    if source_root.resolve() in staging_root.resolve().parents:
        pass
    if not (staging_root / "AGENTS.md").is_file():
        raise SystemExit(f"Staging root does not contain AGENTS.md: {staging_root}")
    if not paper_path.exists():
        raise SystemExit(f"Paper path not found: {paper_path}")


def build_question_plan_prompt(question_count: int) -> str:
    return f"""You are preparing exact neutral questions for a graduate student who will ask both paper-help agents the same questions.

You are in a directory containing only paper files. Inspect only these files. Do not assume access to code, data, repository docs, APP materials, or author notes.

Create exactly {question_count} standalone questions. Each question should be natural, focused, and answerable in one assistant response. Across the full set, cover:
- main claim and contribution;
- assumptions and scope;
- technical details to clarify;
- one result, figure, table, theorem, or equation to ask how to check;
- limitations or possible failure modes;
- one next-step research or sanity-check question.

Do not mention APP, benchmarks, or agent comparison. Return only a JSON array of strings, with no surrounding prose."""


def parse_question_script(text: str, question_count: int) -> list[str]:
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            questions = [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            questions = []
    else:
        questions = []
    if not questions:
        for line in text.splitlines():
            stripped = line.strip()
            stripped = re.sub(r"^(?:[-*]|\d+[.)])\s*", "", stripped).strip()
            if stripped and len(stripped.split()) >= 4:
                questions.append(stripped)
    fallback = [
        "What is the paper's main claim and contribution, and what assumptions does it rely on?",
        "Which technical definition, equation, method, or experimental setup detail is most important for understanding the result?",
        "How would I check or reproduce one central figure, table, theorem, or numerical result from the paper?",
        "What are the main limitations, failure modes, or scope boundaries of the paper's conclusions?",
        "What is one reasonable next-step sanity check, ablation, extension, or follow-up experiment suggested by this paper?",
    ]
    for question in fallback:
        if len(questions) >= question_count:
            break
        questions.append(question)
    return questions[:question_count]


def build_paper_agent_prompt(reader_message: str, source_root: Path) -> str:
    return f"""You are the paper agent for this publication-staging folder.

Follow the local `AGENTS.md` and `CLAUDE.md` instructions if present. Answer from this staged publication folder. Do not inspect or rely on the original working repo at `{source_root}`.

The reader starts with:

<reader_message>
{reader_message}
</reader_message>

End every response with this footer:

COMPARE_APP_STATUS: continue | finished | blocked
COMPARE_APP_PHASE: <short phase>
COMPARE_APP_TOPICS: <comma-separated topics>
"""


def build_general_agent_prompt(reader_message: str, staging_root: Path) -> str:
    return f"""You are a general research assistant helping a graduate student understand this paper from the original working repository.

Use the paper and source repository materials available here. Do not read, inspect, or rely on `{staging_root}` or any `publication-staging/` folder. Do not follow APP-specific instructions or `AGENTS.md`; answer as a normal repository-aware assistant.

The reader starts with:

<reader_message>
{reader_message}
</reader_message>

End every response with this footer:

COMPARE_APP_STATUS: continue | finished | blocked
COMPARE_APP_PHASE: <short phase>
COMPARE_APP_TOPICS: <comma-separated topics>
"""


def build_agent_reply_prompt(reader_message: str, agent_kind: str, forbidden_path: Path | None) -> str:
    # The boundary must mirror the per-agent isolation set on the opening turn:
    # the paper agent answers only from publication-staging (forbidden = original repo),
    # the general agent answers only from the original repo (forbidden = publication-staging).
    if agent_kind == "paper":
        boundary = (
            f"Answer only from this staged publication folder. Do not inspect or rely on the original working repo at `{forbidden_path}`."
            if forbidden_path
            else "Answer only from this staged publication folder. Do not inspect or rely on the original working repository."
        )
    else:
        boundary = (
            f"Do not inspect or rely on `{forbidden_path}` or any `publication-staging/` folder."
            if forbidden_path
            else "Do not inspect or rely on any `publication-staging/` folder."
        )
    role = "paper agent" if agent_kind == "paper" else "general research assistant"
    return f"""Message from the reader:

<reader_message>
{reader_message}
</reader_message>

Continue as the {role}. {boundary}

End every response with this footer:

COMPARE_APP_STATUS: continue | finished | blocked
COMPARE_APP_PHASE: <short phase>
COMPARE_APP_TOPICS: <comma-separated topics>
"""


def append_turn(transcript: Path, round_index: int, turn: int, speaker: str, message: str, output_file: Path) -> None:
    append_text(
        transcript,
        f"\n## Round {round_index} - Turn {turn} - {speaker}\n\n"
        f"Time: {iso_now()}\n\n"
        f"Output file: `{output_file}`\n\n"
        f"{message.rstrip()}\n",
    )


def record_turn(
    *,
    transcript: Path,
    events_path: Path,
    html_path: Path,
    html_title: str,
    auto_refresh: bool,
    arm: str,
    round_index: int,
    turn: int,
    speaker: str,
    message: str,
    output_file: Path,
) -> None:
    append_turn(transcript, round_index, turn, speaker, message, output_file)
    append_jsonl(
        events_path,
        {
            "kind": "turn",
            "arm": arm,
            "round": round_index,
            "turn": turn,
            "speaker": speaker,
            "time": iso_now(),
            "output_file": str(output_file),
            "message": message,
        },
    )
    render_live_html(html_path, events_path, html_title, auto_refresh)


def run_chat_arm(
    *,
    runner: CodexSessionRunner,
    arm: str,
    agent_kind: str,
    agent_cwd: Path,
    source_root: Path,
    staging_root: Path,
    questions: list[str],
    question_script_path: Path,
    transcript: Path,
    events_path: Path,
    html_path: Path,
    html_title: str,
    auto_refresh: bool,
) -> dict[str, Any]:
    write_text(
        transcript,
        f"# Compare APP Chat History: {arm}\n\n"
        f"Agent kind: `{agent_kind}`\n"
        f"Agent cwd: `{agent_cwd}`\n"
        f"Question script: `{question_script_path}`\n"
        f"Questions: `{len(questions)}`\n",
    )
    agent_name = f"{arm}-agent"
    reader_msg = build_scripted_reader_message(
        question=questions[0],
        round_index=1,
        total_rounds=len(questions),
        footer_prefix="COMPARE_APP",
    )
    record_turn(
        transcript=transcript,
        events_path=events_path,
        html_path=html_path,
        html_title=html_title,
        auto_refresh=auto_refresh,
        arm=arm,
        round_index=1,
        turn=1,
        speaker="reader",
        message=reader_msg,
        output_file=question_script_path,
    )

    if agent_kind == "paper":
        agent_prompt = build_paper_agent_prompt(reader_msg, source_root)
    else:
        agent_prompt = build_general_agent_prompt(reader_msg, staging_root)
    agent_session, agent_msg, agent_output = runner.start(agent_name, agent_cwd, agent_prompt)
    record_turn(
        transcript=transcript,
        events_path=events_path,
        html_path=html_path,
        html_title=html_title,
        auto_refresh=auto_refresh,
        arm=arm,
        round_index=1,
        turn=2,
        speaker="agent",
        message=agent_msg,
        output_file=agent_output,
    )

    turn = 3
    rounds_completed = 1
    reader_turns = 1
    agent_turns = 1
    final_status = "max_rounds_reached"
    agent_footer = extract_footer(agent_msg)

    for round_index, question in enumerate(questions[1:], start=2):
        if agent_footer["status"] == "blocked":
            final_status = "agent_blocked"
            break

        reader_msg = build_scripted_reader_message(
            question=question,
            round_index=round_index,
            total_rounds=len(questions),
            footer_prefix="COMPARE_APP",
        )
        reader_turns += 1
        record_turn(
            transcript=transcript,
            events_path=events_path,
            html_path=html_path,
            html_title=html_title,
            auto_refresh=auto_refresh,
            arm=arm,
            round_index=round_index,
            turn=turn,
            speaker="reader",
            message=reader_msg,
            output_file=question_script_path,
        )
        turn += 1

        forbidden = staging_root if agent_kind == "general" else source_root
        agent_msg, agent_output = runner.resume(
            agent_name,
            agent_session,
            agent_cwd,
            turn,
            build_agent_reply_prompt(reader_msg, agent_kind, forbidden),
        )
        agent_turns += 1
        record_turn(
            transcript=transcript,
            events_path=events_path,
            html_path=html_path,
            html_title=html_title,
            auto_refresh=auto_refresh,
            arm=arm,
            round_index=round_index,
            turn=turn,
            speaker="agent",
            message=agent_msg,
            output_file=agent_output,
        )
        turn += 1
        rounds_completed = round_index
        agent_footer = extract_footer(agent_msg)
        if agent_footer["status"] == "blocked":
            final_status = "agent_blocked"
            break
    else:
        final_status = "script_completed"

    return {
        "arm": arm,
        "agent_kind": agent_kind,
        "reader_session_id": None,
        "agent_session_id": agent_session,
        "reader_turns": reader_turns,
        "agent_turns": agent_turns,
        "rounds_completed": rounds_completed,
        "completion_status": final_status,
        "transcript_path": str(transcript),
    }


def anonymize_transcript(text: str) -> str:
    text = text.replace("# Compare APP Chat History:", "# Paper Help Chat History:")
    text = text.replace("COMPARE_APP_", "CHAT_")
    text = re.sub(r"paper-agent", "agent", text, flags=re.IGNORECASE)
    text = re.sub(r"general-agent", "agent", text, flags=re.IGNORECASE)
    text = re.sub(r"Agent kind: `[^`]+`\n", "", text)
    text = re.sub(r"Agent cwd: `[^`]+`\n", "", text)
    text = re.sub(r"Reader cwd: `[^`]+`\n", "", text)
    text = re.sub(r"Question script: `[^`]+`\n", "", text)
    text = re.sub(r"\nOutput file: `[^`]+`\n", "", text)
    return text


def rewrite_workspace_paths(text: str, source_workspaces: list[Path], evaluator_workspace: Path) -> str:
    replacements: dict[str, str] = {}
    for source_workspace in source_workspaces:
        replacements[str(source_workspace)] = str(evaluator_workspace)
        replacements[source_workspace.as_posix()] = evaluator_workspace.as_posix()
    rewritten = text
    for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        rewritten = rewritten.replace(old, new)
    # Fallback for base-dir mismatches: a transcript may cite absolute paths whose
    # leading directory differs from the staging/source root passed at evaluation
    # time -- e.g. the chat was generated on another machine/checkout, or is being
    # re-evaluated against a moved or archived copy. Exact-prefix replacement above
    # misses those, leaking raw absolute paths that the evaluator then penalizes as
    # "not grounded in the neutral workspace". Rewrite any absolute path ending in a
    # workspace's anchor segment (its basename, e.g. `publication-staging` or the
    # source folder name) to the neutral workspace, regardless of leading directory.
    new_posix = evaluator_workspace.as_posix()
    anchors = {sw.name for sw in source_workspaces if sw.name}
    # `publication-staging` is the protocol's canonical staging dir name and is what
    # appears in transcripts even when the eval-time staging root is a renamed copy
    # (e.g. an archived snapshot dir); anchor on it explicitly. It is forbidden in
    # general-agent transcripts, so adding it unconditionally is safe.
    anchors.add("publication-staging")

    def _replace(match: "re.Match[str]") -> str:
        # Guard: the neutral workspace path itself may contain an anchor segment
        # (run dirs are `.../compare-app/<example>/...`). Never rewrite a span that
        # is a prefix of the neutral path -- that span is part of an already-mapped
        # path, and rewriting it would duplicate the neutral root.
        span = match.group(0)
        if new_posix == span or new_posix.startswith(span + "/"):
            return span
        return new_posix

    # The path body excludes whitespace, quotes/backticks, and bracket/paren/comma
    # punctuation so a match cannot cross Markdown-link syntax (`[text](url)`) or
    # span from one path token into the next -- which would otherwise swallow an
    # already-rewritten neutral path and duplicate it.
    for anchor in sorted(anchors, key=len, reverse=True):
        pattern = re.compile(r"/[^\s`'\"()\[\]{},]*?/" + re.escape(anchor) + r"(?=[/\s`'\":)\]},]|$)")
        rewritten = pattern.sub(_replace, rewritten)
    return rewritten


def build_evaluation_input(
    transcripts: dict[str, Path],
    source_workspace_aliases: dict[str, list[Path]],
    evaluator_workspaces: dict[str, Path],
    label_mapping: dict[str, str],
    output_path: Path,
) -> None:
    parts = [
        "# Paper Conversation Evaluation Input\n\n"
        "The two transcripts below are anonymized and randomly ordered. Each agent had its own neutral workspace copy "
        "for grounding checks. Do not infer which system produced either transcript.\n"
    ]
    for label in ["Agent A", "Agent B"]:
        kind = label_mapping[label]
        path = transcripts[kind]
        parts.append(f"\n## {label} Neutral Workspace\n\n`{evaluator_workspaces[label]}`\n")
        parts.append(f"\n## {label} Transcript\n\n")
        transcript = anonymize_transcript(read_text(path))
        transcript = rewrite_workspace_paths(transcript, source_workspace_aliases[kind], evaluator_workspaces[label])
        parts.append(transcript)
        parts.append("\n")
    write_text(output_path, "".join(parts))


def build_evaluator_label_mapping(transcripts: dict[str, Path], rng: random.Random) -> dict[str, str]:
    items = list(transcripts)
    rng.shuffle(items)
    return dict(zip(["Agent A", "Agent B"], items))


def build_evaluator_workspace_copies(
    label_mapping: dict[str, str],
    source_workspaces: dict[str, Path],
    run_dir: Path,
    staging_root: Path,
) -> dict[str, Path]:
    evaluator_root = run_dir / "evaluator-workspaces"
    evaluator_workspaces: dict[str, Path] = {}
    for label, kind in label_mapping.items():
        source = source_workspaces[kind]
        try:
            staging_inside_source = staging_root.is_relative_to(source)
        except AttributeError:
            staging_inside_source = source in staging_root.parents or staging_root == source
        excluded = [staging_root] if kind == "general-agent" and staging_inside_source else []
        evaluator_workspaces[label] = copy_evaluator_workspace(source, evaluator_root / label_slug(label), excluded)
    return evaluator_workspaces


def build_evaluator_prompt(evaluation_input: Path, paper_context: Path, evaluator_workspaces: dict[str, Path]) -> str:
    workspace_lines = "\n".join(f"- {label}: `{path}`" for label, path in sorted(evaluator_workspaces.items()))
    return f"""You are a neutral evaluator of two paper-help conversations.

You may inspect:
- the paper-only reader context at `{paper_context}`;
- the neutral workspace copies for each anonymized agent:
{workspace_lines}

The two agents did not have the same filesystem view. When judging grounding, evaluate each agent's file references relative to that agent's own neutral workspace. Do not penalize an agent because a cited file or command exists only in its own workspace and not in the other workspace. Do not infer or guess which implementation, protocol, source layout, or workspace type produced either agent.

Do not use APP-specific criteria; judge these as ordinary conversations between a graduate-student reader and a paper-help assistant. Score based on factual accuracy, informativeness, appropriate grounding within each agent's available workspace, honesty about uncertainty, and usefulness.

Read the anonymized randomized transcripts here:

`{evaluation_input}`

Score Agent A and Agent B independently:
- accuracy_score: 1-10
- informativeness_score: 1-10
- grounding_score: 1-10
- honesty_score: 1-10

Discuss concrete evidence from the transcripts, factual errors, unsupported claims, useful explanations, and reproduction or checking guidance where relevant. End with a short comparative verdict. Do not guess which implementation or protocol produced each agent."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example_or_source_root", nargs="?", help="Example name under data/example-papers/ or source-root path")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--source-root", default=None, help="Original working repo/source folder")
    parser.add_argument("--staging-root", default=None, help="APP publication-staging folder")
    parser.add_argument("--paper-path", default=None, help="Paper file or directory to copy for the reader")
    parser.add_argument("--working-root", default="working/compare-app", help="Run output root")
    parser.add_argument("--timestamp", default=None, help="Run id timestamp; defaults to now")
    parser.add_argument("--max-rounds", type=int, default=5, help="Number of exact scripted reader questions per agent; floored at 5")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for run/evaluation ordering")
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--sandbox", default="danger-full-access")
    parser.add_argument("--extra-codex-arg", action="append", default=[])
    parser.add_argument("--turn-timeout", type=int, default=900, help="Seconds before a single Codex turn is marked blocked")
    parser.add_argument("--no-eval", action="store_true", help="Skip evaluator pass")
    parser.add_argument("--no-html-refresh", action="store_true", help="Disable live HTML auto-refresh")
    parser.add_argument("--reevaluate-run", default=None, help="Existing compare-app run directory to re-evaluate with current evaluator prompt")
    parser.add_argument(
        "--reuse-general-run",
        default=None,
        help="Existing compare-app run whose question script and general-agent transcript should be reused; only the paper-agent chat is rerun.",
    )
    return parser.parse_args()


def reevaluate_existing_run(args: argparse.Namespace) -> int:
    run_dir = Path(args.reevaluate_run).expanduser()
    if not run_dir.is_absolute():
        run_dir = Path(args.workspace).resolve() / run_dir
    run_dir = run_dir.resolve()
    summary_path = run_dir / "run-summary.json"
    if not summary_path.is_file():
        raise SystemExit(f"Missing run summary: {summary_path}")
    summary = json.loads(read_text(summary_path))
    workspace = Path(args.workspace).resolve()
    saved_source_root = Path(summary["source_root"]).expanduser()
    saved_staging_root = Path(summary["staging_root"]).expanduser()
    source_root = saved_source_root.resolve()
    if not source_root.exists():
        fallback_source = workspace / "data/example-papers" / str(summary.get("example_name", run_dir.parent.name))
        if fallback_source.exists():
            source_root = fallback_source.resolve()
    staging_root = saved_staging_root.resolve()
    if not staging_root.exists() and (source_root / "publication-staging").exists():
        staging_root = (source_root / "publication-staging").resolve()
    reader_paper = Path(summary["reader_paper_context"]).resolve()
    if not reader_paper.exists() and (run_dir / "reader-paper").exists():
        reader_paper = (run_dir / "reader-paper").resolve()
    transcripts = {
        "paper-agent": run_dir / "paper-agent-chat-history.md",
        "general-agent": run_dir / "general-agent-chat-history.md",
    }
    source_workspaces = {
        "paper-agent": staging_root,
        "general-agent": source_root,
    }
    source_workspace_aliases = {
        "paper-agent": list(dict.fromkeys([staging_root, saved_staging_root])),
        "general-agent": list(dict.fromkeys([source_root, saved_source_root])),
    }
    seed = summary.get("seed") if isinstance(summary.get("seed"), int) else 0
    rng = random.Random(seed)
    evaluation_input = run_dir / "evaluation-input.md"
    evaluator_label_mapping = build_evaluator_label_mapping(transcripts, rng)
    evaluator_workspaces = build_evaluator_workspace_copies(
        evaluator_label_mapping,
        source_workspaces,
        run_dir,
        staging_root,
    )
    build_evaluation_input(
        transcripts,
        source_workspace_aliases,
        evaluator_workspaces,
        evaluator_label_mapping,
        evaluation_input,
    )
    report_path = run_dir / "evaluation-report.md"
    summary["evaluation_input_path"] = str(evaluation_input)
    summary["evaluator_label_mapping"] = evaluator_label_mapping
    summary["source_workspaces"] = {key: str(value) for key, value in source_workspaces.items()}
    summary["evaluator_workspaces"] = {key: str(value) for key, value in evaluator_workspaces.items()}
    summary["reevaluated_at"] = iso_now()
    if args.no_eval:
        summary["evaluation_report_path"] = str(report_path) if report_path.exists() else None
        write_text(summary_path, json_dumps(summary))
        print(json_dumps(summary))
        return 0

    runner = CodexSessionRunner(
        codex_bin=args.codex_bin,
        logs_dir=run_dir / "logs",
        sandbox=args.sandbox,
        model=args.model,
        extra_args=args.extra_codex_arg,
        turn_timeout=args.turn_timeout,
    )
    report, report_output = runner.one_shot(
        "evaluator-reeval",
        source_root,
        build_evaluator_prompt(evaluation_input, reader_paper, evaluator_workspaces),
    )
    old_report_path = run_dir / "evaluation-report.previous.md"
    if report_path.exists() and not old_report_path.exists():
        shutil.copy2(report_path, old_report_path)
    write_text(report_path, report)
    summary["evaluation_report_path"] = str(report_path)
    summary["evaluator_output_path"] = str(report_output)
    write_text(summary_path, json_dumps(summary))
    print(json_dumps(summary))
    return 0


def main() -> int:
    args = parse_args()
    if args.reevaluate_run:
        return reevaluate_existing_run(args)
    workspace = Path(args.workspace).resolve()
    source_root = resolve_source_root(workspace, args.example_or_source_root, args.source_root)
    staging_root = Path(args.staging_root).expanduser() if args.staging_root else source_root / "publication-staging"
    if not staging_root.is_absolute():
        staging_root = workspace / staging_root
    staging_root = staging_root.resolve()
    paper_path = resolve_paper_path(source_root, staging_root, args.paper_path, workspace)
    validate_inputs(source_root, staging_root, paper_path)
    question_count = max(args.max_rounds, 5)
    reuse_general_run = resolve_existing_run(workspace, args.reuse_general_run) if args.reuse_general_run else None

    timestamp = args.timestamp or now_stamp()
    example_name = infer_example_name(source_root)
    run_dir = workspace / args.working_root / example_name / timestamp
    if run_dir.exists():
        raise SystemExit(f"Run directory already exists: {run_dir}")
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    reader_paper = copy_paper_context(paper_path, run_dir / "reader-paper")
    live_events = run_dir / "live-events.jsonl"
    live_html = run_dir / "chat-history.html"
    html_title = f"Compare APP - {example_name} - {timestamp}"
    render_live_html(live_html, live_events, html_title, not args.no_html_refresh)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 2**31)
    rng = random.Random(seed)
    runner = CodexSessionRunner(
        codex_bin=args.codex_bin,
        logs_dir=logs_dir,
        sandbox=args.sandbox,
        model=args.model,
        extra_args=args.extra_codex_arg,
        turn_timeout=args.turn_timeout,
    )

    started_at = iso_now()
    question_plan_path = run_dir / "question-plan.md"
    question_script_path = run_dir / "question-script.json"
    reused_general_summary: dict[str, Any] | None = None
    reused_general_transcript: Path | None = None
    question_plan_output: Path | None = None
    if reuse_general_run:
        questions, reused_general_source, reused_general_summary = load_reused_general_baseline(reuse_general_run)
        question_count = len(questions)
        reused_general_transcript = run_dir / "general-agent-chat-history.md"
        shutil.copy2(reused_general_source, reused_general_transcript)
        old_question_plan = reuse_general_run / "question-plan.md"
        if old_question_plan.is_file():
            shutil.copy2(old_question_plan, question_plan_path)
        else:
            write_text(question_plan_path, "Question plan reused from existing compare-app run.\n")
        write_text(question_script_path, json_dumps(questions))
        append_jsonl(
            live_events,
            {
                "kind": "runner",
                "arm": "general-agent",
                "round": 0,
                "turn": 0,
                "speaker": "runner",
                "time": iso_now(),
                "output_file": str(reused_general_transcript),
                "message": f"Reused general-agent transcript and question script from `{reuse_general_run}`.",
            },
        )
        render_live_html(live_html, live_events, html_title, not args.no_html_refresh)
    else:
        question_script_raw, question_plan_output = runner.one_shot(
            "question-planner",
            reader_paper,
            build_question_plan_prompt(question_count),
        )
        questions = parse_question_script(question_script_raw, question_count)
        write_text(question_plan_path, question_script_raw)
        write_text(question_script_path, json_dumps(questions))

    arms = [
        ("paper-agent", "paper", staging_root, run_dir / "paper-agent-chat-history.md"),
        ("general-agent", "general", source_root, run_dir / "general-agent-chat-history.md"),
    ]
    if reuse_general_run:
        arms = [arm for arm in arms if arm[0] == "paper-agent"]
    rng.shuffle(arms)
    arm_summaries: dict[str, Any] = {}
    if reuse_general_run and reused_general_transcript:
        old_arms = reused_general_summary.get("arms", {}) if isinstance(reused_general_summary, dict) else {}
        old_general = old_arms.get("general-agent", {}) if isinstance(old_arms, dict) else {}
        arm_summaries["general-agent"] = {
            "arm": "general-agent",
            "agent_kind": "general",
            "reader_session_id": old_general.get("reader_session_id"),
            "agent_session_id": old_general.get("agent_session_id"),
            "reader_turns": old_general.get("reader_turns", question_count),
            "agent_turns": old_general.get("agent_turns", question_count),
            "rounds_completed": old_general.get("rounds_completed", question_count),
            "completion_status": old_general.get("completion_status", "reused"),
            "transcript_path": str(reused_general_transcript),
            "reused_from_run": str(reuse_general_run),
        }
    for arm, agent_kind, agent_cwd, transcript in arms:
        arm_summaries[arm] = run_chat_arm(
            runner=runner,
            arm=arm,
            agent_kind=agent_kind,
            agent_cwd=agent_cwd,
            source_root=source_root,
            staging_root=staging_root,
            questions=questions,
            question_script_path=question_script_path,
            transcript=transcript,
            events_path=live_events,
            html_path=live_html,
            html_title=html_title,
            auto_refresh=not args.no_html_refresh,
        )

    transcripts = {
        "paper-agent": run_dir / "paper-agent-chat-history.md",
        "general-agent": run_dir / "general-agent-chat-history.md",
    }
    source_workspaces = {
        "paper-agent": staging_root,
        "general-agent": source_root,
    }
    source_workspace_aliases = {
        "paper-agent": [staging_root],
        "general-agent": [source_root],
    }
    if reuse_general_run and isinstance(reused_general_summary, dict):
        old_source_root = reused_general_summary.get("source_root")
        if isinstance(old_source_root, str) and old_source_root:
            source_workspace_aliases["general-agent"] = list(
                dict.fromkeys([source_root, Path(old_source_root).expanduser().resolve()])
            )
    evaluation_input = run_dir / "evaluation-input.md"
    evaluator_label_mapping = build_evaluator_label_mapping(transcripts, rng)
    evaluator_workspaces = build_evaluator_workspace_copies(
        evaluator_label_mapping,
        source_workspaces,
        run_dir,
        staging_root,
    )
    build_evaluation_input(
        transcripts,
        source_workspace_aliases,
        evaluator_workspaces,
        evaluator_label_mapping,
        evaluation_input,
    )
    ended_at = iso_now()
    summary = {
        "example_name": example_name,
        "run_id": timestamp,
        "started_at": started_at,
        "ended_at": ended_at,
        "source_root": str(source_root),
        "staging_root": str(staging_root),
        "paper_path": str(paper_path),
        "reader_paper_context": str(reader_paper),
        "question_plan_path": str(question_plan_path),
        "question_plan_output_path": str(question_plan_output) if question_plan_output else None,
        "question_script_path": str(question_script_path),
        "requested_max_rounds": args.max_rounds,
        "question_count": question_count,
        "questions": questions,
        "seed": seed,
        "arm_run_order": [arm[0] for arm in arms],
        "reuse_general_run": str(reuse_general_run) if reuse_general_run else None,
        "evaluator_label_mapping": evaluator_label_mapping,
        "source_workspaces": {key: str(value) for key, value in source_workspaces.items()},
        "evaluator_workspaces": {key: str(value) for key, value in evaluator_workspaces.items()},
        "arms": arm_summaries,
        "evaluation_input_path": str(evaluation_input),
        "chat_history_html_path": str(live_html),
        "live_events_path": str(live_events),
        "logs_dir": str(logs_dir),
    }
    summary_path = run_dir / "run-summary.json"
    write_text(summary_path, json_dumps(summary))

    if not args.no_eval:
        report, report_output = runner.one_shot(
            "evaluator",
            source_root,
            build_evaluator_prompt(evaluation_input, reader_paper, evaluator_workspaces),
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
