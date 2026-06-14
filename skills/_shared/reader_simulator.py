"""Shared graduate-student reader simulator prompts for APP test harnesses."""

from __future__ import annotations

from typing import Literal


AccessMode = Literal["package", "paper_only"]


def _footer(prefix: str) -> str:
    return f"""{prefix}_STATUS: continue | finished | blocked
{prefix}_PHASE: <short phase>
{prefix}_TOPICS: <comma-separated topics>"""


def _access_instructions(access_mode: AccessMode, paper_context: str | None) -> str:
    if access_mode == "package":
        return """You are in the publication-staging folder. Briefly inspect reader-facing files such as `README.md`, the `paper/` directory, and any obvious code or reproduction notes. Then start a natural conversation with the paper agent. Ask for help understanding the paper and how to use the package."""
    if access_mode == "paper_only":
        context = (
            f"\nUse this paper-only question plan as guidance:\n\n<question_plan>\n{paper_context.strip()}\n</question_plan>\n"
            if paper_context
            else ""
        )
        return f"""You are in a folder containing only the paper files made available to a normal reader. Inspect only these paper files before asking questions. Do not inspect source code, data folders, APP files, `AGENTS.md`, `README.md`, publication-staging metadata, or the original working repository. You do not know about APP or any comparison experiment.{context}"""
    raise ValueError(f"Unsupported reader access mode: {access_mode}")


def build_reader_opening_prompt(
    *,
    max_rounds: int,
    footer_prefix: str,
    counterpart_label: str,
    access_mode: AccessMode,
    paper_context: str | None = None,
) -> str:
    """Build the first-turn prompt for the shared simulated reader."""
    return f"""You are a graduate student reading this paper for the first time.

You have general background in the paper's field, but you are not specially familiar with this paper. You are a neutral reader: you do not know about publication protocols, agent benchmarks, or any comparison being run. Ask natural, focused questions as a real reader would.

{_access_instructions(access_mode, paper_context)}

Across at most {max_rounds} rounds, cover the things a real reader would care about:
- the paper's main claim, assumptions, and contribution;
- technical details you need clarified, such as definitions, equations, methods, data, or experiments;
- how to reproduce, check, or sanity-check one specific figure, table, theorem, or result when relevant;
- limitations, failure modes, or scope boundaries;
- one plausible next-step research question, sanity check, or follow-up experiment.

Ask one or two focused questions at a time. If an answer from {counterpart_label} is vague, ask for concrete evidence, file paths, commands, equations, assumptions, or caveats when useful. Finish only after the conversation has covered broad understanding, technical details, result checking, limitations, and next-step research, or if there is a real blocker.

End every response with this footer:

{_footer(footer_prefix)}
"""


def build_reader_reply_prompt(
    *,
    agent_message: str,
    round_index: int,
    max_rounds: int,
    footer_prefix: str,
    counterpart_label: str,
    access_mode: AccessMode,
    paper_context: str | None = None,
) -> str:
    """Build a follow-up prompt for the shared simulated reader."""
    access_reminder = (
        "Continue to use only the paper files and the conversation so far. Do not inspect source code, data folders, APP files, `AGENTS.md`, `README.md`, publication-staging metadata, or the original working repository."
        if access_mode == "paper_only"
        else "Continue as the reader of the paper package."
    )
    context = (
        f"\nPaper-only question plan, for continuity:\n\n<question_plan>\n{paper_context.strip()}\n</question_plan>\n"
        if paper_context
        else ""
    )
    return f"""Message from {counterpart_label}:

<agent_message>
{agent_message}
</agent_message>

Continue as the neutral graduate-student reader. This is round {round_index} of at most {max_rounds}. {access_reminder}{context}

Ask the next realistic reader question. Make sure the full conversation covers broad understanding, technical details, result or reproduction checking when relevant, limitations, and a quick next-step research question. If those are already covered and the answer quality is sufficient, finish the test.

End every response with this footer:

{_footer(footer_prefix)}
"""


def build_scripted_reader_message(
    *,
    question: str,
    round_index: int,
    total_rounds: int,
    footer_prefix: str,
) -> str:
    """Format an exact scripted reader question for fair pairwise comparisons."""
    status = "finished" if round_index >= total_rounds else "continue"
    return f"""Question {round_index} of {total_rounds}:

{question.strip()}

{footer_prefix}_STATUS: {status}
{footer_prefix}_PHASE: scripted-question-{round_index}
{footer_prefix}_TOPICS: scripted reader question {round_index}
"""
