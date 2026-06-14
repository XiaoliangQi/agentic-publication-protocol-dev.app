#!/usr/bin/env python3
"""Build a publishable Hugging Face dataset from the compare-app clean re-eval.

Publishes ONLY the public arXiv papers (the 11 in the paper's Table); the
confidential / ongoing-research examples are deliberately excluded. Each record
carries the arXiv link and the official GitHub source repo.

Output:
    <out>/README.md                                      dataset card (HF YAML header)
    <out>/compare-app-benchmark/data/compare_app.jsonl   one row per paper
    <out>/compare-app-benchmark/paper-records/<slug>/    conversation/eval files
    <out>/example-papers/<slug>/                         optional source-material placeholders

Usage:
    python3 code/scripts/build_compare_app_dataset.py [--out DIR]
    python3 code/scripts/build_compare_app_dataset.py --paper attention-tomography --run-tag 20260609-main-noPR29 --out /tmp/app-dataset-test
"""
import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
RUN_TAG = "20260613-pr34-rerun-pathfix"
EVALUATOR_MODEL = "Codex CLI, gpt-5.5, reasoning effort xhigh"
LICENSE = "cc-by-4.0"

# Public papers only (paper Table order): slug, arxiv, title, github
PAPERS = [
    ("attention-tomography", "2006.12469", "Attention-based Quantum Tomography",
     "https://github.com/KimGroup/AQT"),
    ("balloon-qnet", "2412.03356", "Free-space model for a balloon-based quantum network",
     "https://github.com/RajaYehia/balloon_qnet"),
    ("circuit-cutting-mlft", "2005.12702", "Quantum Circuit Cutting with Maximum Likelihood Tomography",
     "https://github.com/Quantum-Software-Tools/QSPLIT-MLFT"),
    ("fermion-entanglement", "1703.10587", "Particle partition entanglement of one dimensional spinless fermions",
     "https://github.com/DelMaestroGroup/PartEntFermions"),
    ("mbr-states", "2411.03110", "Multiple-basis representation of quantum states",
     "https://github.com/patrickemonts/multiple-basis-representation"),
    ("metrology-hierarchy", "2203.09758", "Optimal Strategies of Quantum Metrology with a Strict Hierarchy",
     "https://github.com/qiushi-liu/strategies_in_metrology"),
    ("oam-gkp-metrology", "2605.13271", "OAM-Induced Lattice Rotation Reveals a Fractional Optimum in Fault-Tolerant GKP Quantum Sensing",
     "https://github.com/simanshukumar369/oam-gkp-quantum-metrology"),
    ("qfi-certification", "2306.12711", "Certifying the quantum Fisher information from a given set of mean values: a semidefinite programming approach",
     "https://github.com/anubhavks/SDP_QFI_partialinfo"),
    ("qpsq-learning", "2310.02075", "Learning Quantum Processes with Quantum Statistical Queries",
     "https://github.com/chirag-w/qpsq-learning"),
    ("spinchain-entanglement", "2007.06989", "Emergent entanglement structures and self-similarity in quantum spin chains",
     "https://github.com/matteoacrossi/emergent-entanglement-structures"),
    ("topological-floquet", "2012.01459", "Topological two-dimensional Floquet lattice on a single superconducting qubit",
     "https://github.com/AdamSmith-physics/qubit-topological-floquet"),
]
ASPECTS = ["accuracy", "informativeness", "grounding", "honesty"]

# Strip internal dev plumbing (repo names, run tags, workspace paths) from any
# text that ships in the public dataset, leaving clean relative paths.
_ABS_PREFIX = r"/(?:home|Users)/[^`\s)\]]+"

_SCRUB = [
    (re.compile(_ABS_PREFIX + r"/working/staging-archive/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/?"), "publication-staging/"),
    (re.compile(_ABS_PREFIX + r"/working/compare-app/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/evaluator-workspaces/agent-[ab]/?"), ""),
    (re.compile(_ABS_PREFIX + r"/working/compare-app/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/?"), ""),
    (re.compile(_ABS_PREFIX + r"/data/example-papers/[A-Za-z0-9._-]+/publication-staging/?"), "publication-staging/"),
    (re.compile(_ABS_PREFIX + r"/data/example-papers/[A-Za-z0-9._-]+/?"), ""),
    (re.compile(r"/home/[A-Za-z0-9._-]+/working/staging-archive/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/?"), "publication-staging/"),
    (re.compile(r"/home/[A-Za-z0-9._-]+/working/compare-app/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/evaluator-workspaces/agent-[ab]/?"), ""),
    (re.compile(r"/home/[A-Za-z0-9._-]+/working/compare-app/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/?"), ""),
    (re.compile(r"/home/[A-Za-z0-9._-]+/data/example-papers/[A-Za-z0-9._-]+/publication-staging/?"), "publication-staging/"),
    (re.compile(r"/home/[A-Za-z0-9._-]+/data/example-papers/[A-Za-z0-9._-]+/?"), ""),
    (re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/?"), ""),
]


def scrub(text: str) -> str:
    for pat, repl in _SCRUB:
        text = pat.sub(repl, text)
    return text


def scrub_evaluation_input(text: str, slug: str) -> str:
    text = re.sub(
        _ABS_PREFIX + rf"/working/compare-app/{re.escape(slug)}/"
        r"[A-Za-z0-9._-]+/evaluator-workspaces/(agent-[ab])",
        r"evaluator-workspaces/\1",
        text,
    )
    return scrub(text)


def clean_run_summary(summary: dict) -> dict:
    summary = json.loads(json.dumps(summary))
    if isinstance(summary.get("arms"), dict):
        summary["arms"].get("general-agent", {}).pop("reused_from_run", None)
        summary["arms"].get("general-agent", {}).pop("transcript_path", None)
        summary["arms"].get("paper-agent", {}).pop("transcript_path", None)
    for key in [
        "chat_history_html_path",
        "evaluation_input_path",
        "evaluator_output_path",
        "evaluator_workspaces",
        "live_events_path",
        "question_plan_path",
        "question_script_path",
        "reuse_general_run",
    ]:
        summary.pop(key, None)
    summary["evaluation_report_path"] = "evaluation-report.md"
    summary["logs_dir"] = "logs"
    summary["paper_path"] = "publication-staging/paper"
    summary["reader_paper_context"] = "reader-paper"
    summary["source_root"] = "source"
    summary["source_workspaces"] = {
        "general-agent": "source",
        "paper-agent": "publication-staging",
    }
    summary["staging_root"] = "publication-staging"
    return summary


def aspect_scores(text, label):
    m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text)
    if not m:
        b = re.search(rf"\*\*{label}\*\*(.*?)(?=\*\*Agent|\*\*Comparative|\Z)", text, re.S)
        nums = re.findall(r"_score:\s*(\d+)", b.group(1)) if b else []
        if len(nums) < 4:
            raise ValueError(f"no scores for {label}")
        vals = [int(x) for x in nums[:4]]
    else:
        vals = [int(m.group(i)) for i in range(1, 5)]
    return dict(zip(ASPECTS, vals))


def build(out: Path, run_tag: str = RUN_TAG, paper_slugs: Optional[list[str]] = None):
    selected_papers = PAPERS
    if paper_slugs:
        wanted = set(paper_slugs)
        known = {slug for slug, *_ in PAPERS}
        unknown = sorted(wanted - known)
        if unknown:
            raise ValueError(f"unknown paper slug(s): {', '.join(unknown)}")
        selected_papers = [paper for paper in PAPERS if paper[0] in wanted]

    benchmark = out / "compare-app-benchmark"
    (benchmark / "data").mkdir(parents=True, exist_ok=True)
    rows = []
    for slug, arxiv, title, github in selected_papers:
        d = REPO / "working" / "compare-app" / slug / run_tag
        if not d.exists():
            raise FileNotFoundError(f"missing run directory: {d}")
        questions = json.loads((d / "question-script.json").read_text())
        report = (d / "evaluation-report.md").read_text(encoding="utf-8")
        summary = json.loads((d / "run-summary.json").read_text())
        lm = summary["evaluator_label_mapping"]
        by_kind = {lm["Agent A"]: aspect_scores(report, "Agent A"),
                   lm["Agent B"]: aspect_scores(report, "Agent B")}
        pa, ga = by_kind["paper-agent"], by_kind["general-agent"]
        pav, gav = sum(pa.values()) / 4, sum(ga.values()) / 4
        # Public artifacts: question script, question plan, evaluation input,
        # both transcripts, evaluation report, and run summary.
        dst = benchmark / "paper-records" / slug
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(d / "question-script.json", dst / "question-script.json")
        shutil.copy2(d / "question-plan.md", dst / "question-plan.md")
        (dst / "evaluation-input.md").write_text(
            scrub_evaluation_input((d / "evaluation-input.md").read_text(encoding="utf-8"), slug),
            encoding="utf-8",
        )
        (dst / "run-summary.json").write_text(
            json.dumps(clean_run_summary(summary), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paper_transcript = scrub((d / "paper-agent-chat-history.md").read_text(encoding="utf-8"))
        general_transcript = scrub((d / "general-agent-chat-history.md").read_text(encoding="utf-8"))
        report = scrub(report)
        (dst / "paper-agent-chat-history.md").write_text(paper_transcript, encoding="utf-8")
        (dst / "general-agent-chat-history.md").write_text(general_transcript, encoding="utf-8")
        (dst / "evaluation-report.md").write_text(report, encoding="utf-8")
        rows.append({
            "example": slug,
            "arxiv_id": arxiv,
            "arxiv_url": f"https://arxiv.org/abs/{arxiv}",
            "paper_title": title,
            "code_repo": github,
            "questions": questions,
            "paper_agent_transcript": paper_transcript,
            "general_agent_transcript": general_transcript,
            "evaluation_report": report,
            "paper_agent_scores": pa,
            "general_agent_scores": ga,
            "paper_agent_avg": round(pav, 2),
            "general_agent_avg": round(gav, 2),
            "result": "APP" if pav > gav else ("general" if gav > pav else "tie"),
            "evaluator_model": EVALUATOR_MODEL,
            "evaluation_input_path": f"compare-app-benchmark/paper-records/{slug}/evaluation-input.md",
            "evaluator_label_mapping": lm,
        })
    with (benchmark / "data" / "compare_app.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    app = sum(r["result"] == "APP" for r in rows)
    pmean = sum(r["paper_agent_avg"] for r in rows) / len(rows)
    gmean = sum(r["general_agent_avg"] for r in rows) / len(rows)
    card = f"""---
license: {LICENSE}
task_categories:
- question-answering
language:
- en
tags:
- agentic-publication-protocol
- llm-evaluation
- quantum-physics
- reproducibility
pretty_name: APP compare-app benchmark
size_categories:
- n<1K
configs:
- config_name: default
  data_files: compare-app-benchmark/data/compare_app.jsonl
---

# APP compare-app benchmark

Paired reader conversations and blinded evaluations comparing an **Agentic
Publication Protocol (APP) paper agent** against a **general repository-aware
agent**, on {len(rows)} quantum-physics papers.

For each paper, a neutral reader asks the same scripted questions to both agents;
the two transcripts are anonymized and scored by a blinded evaluator on
accuracy, informativeness, grounding, and honesty (1-10).

- **Evaluator:** {EVALUATOR_MODEL}
- **Result:** APP paper agent wins {app}/{len(rows)}; mean overall {pmean:.2f} (APP) vs {gmean:.2f} (general).

## Files

- `compare-app-benchmark/data/compare_app.jsonl` - one row per paper (questions, both transcripts, per-aspect scores, evaluator label mapping, evaluation-input path, and source links).
- `compare-app-benchmark/paper-records/<example>/` - the question script, question plan, evaluation input, both agent transcripts, evaluation report, and run summary for that paper.
- `example-papers/<example>/` - source paper/code materials and processed APP `publication-staging/` packages for selected redistributable examples.

## Source papers

Each record links the original arXiv paper and its official code repository:

| Example | arXiv | Code |
| --- | --- | --- |
""" + "\n".join(
        f"| {s} | [{a}](https://arxiv.org/abs/{a}) | [{g.split('github.com/')[-1]}]({g}) |"
        for s, a, _, g in PAPERS
    ) + """

## Bundled source materials

The dataset may include source materials and processed APP staging packages for
the following redistributable examples:

| Example | arXiv | Authors | Paper license | Code/data license | Included |
| --- | --- | --- | --- | --- | --- |
| `balloon-qnet` | [2412.03356](https://arxiv.org/abs/2412.03356) | Ilektra Karakosta-Amarantidou, Raja Yehia, Matteo Schiavon | CC BY 4.0 | MIT | source paper/code and APP `publication-staging/` |
| `mbr-states` | [2411.03110](https://arxiv.org/abs/2411.03110) | Adrian Perez-Salinas, Patrick Emonts, Jordi Tura, Vedran Dunjko | CC BY 4.0 | MIT | source paper/code and APP `publication-staging/` |
| `oam-gkp-metrology` | [2605.13271](https://arxiv.org/abs/2605.13271) | Simanshu Kumar, Nandan S. Bisht | CC BY 4.0 | MIT | source paper/code and APP `publication-staging/` |
| `qpsq-learning` | [2310.02075](https://arxiv.org/abs/2310.02075) | Chirag Wadhwa, Mina Doosti | CC BY 4.0 | Apache-2.0 | source paper/code and APP `publication-staging/` |

The `publication-staging/` folders are processed derivative organizations
created for APP evaluation. They may include added README files, agent
instructions, reproduction notes, validation notes, wrappers, and cached-output
checks. They are not endorsed by the original paper authors unless explicitly
stated.

## Licensing

The generated benchmark records, APP staging notes, and other dataset-created
documentation are released under CC BY 4.0.

Bundled upstream code retains its original software license, as listed above.
Bundled upstream paper materials retain their original CC BY 4.0 license.

For papers not listed in "Bundled source materials", this dataset provides only
generated benchmark records and links to arXiv/GitHub. It does not redistribute
their paper PDFs, LaTeX source, figures, source code, or original datasets.

## Third-party materials

The underlying papers and code repositories remain the property of their
respective authors and retain their original licenses. Links are provided for
citation, attribution, and reproducibility context. Inclusion of source
materials or processed APP staging packages does not imply endorsement by the
original authors.
"""
    (out / "README.md").write_text(card, encoding="utf-8")

    example_root = out / "example-papers"
    example_root.mkdir(parents=True, exist_ok=True)
    example_readme = example_root / "README.md"
    if not example_readme.exists():
        example_readme.write_text(
            "# Example Paper Source Materials\n\n"
            "This directory is reserved for redistributable source paper/code materials and\n"
            "processed APP `publication-staging/` packages used by the compare-app benchmark.\n\n"
            "Each example subdirectory should preserve upstream license files and include any\n"
            "additional attribution or provenance notes needed for the bundled materials.\n",
            encoding="utf-8",
        )
    for slug in ["balloon-qnet", "mbr-states", "oam-gkp-metrology", "qpsq-learning"]:
        placeholder_dir = example_root / slug
        placeholder_dir.mkdir(parents=True, exist_ok=True)
        keep = placeholder_dir / ".gitkeep"
        if not any(placeholder_dir.iterdir()):
            keep.touch()

    print(f"wrote {len(rows)} papers from {run_tag} -> {out}")
    print(f"APP wins {app}/{len(rows)} | mean {pmean:.2f} / {gmean:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "datasets"))
    ap.add_argument("--run-tag", default=RUN_TAG)
    ap.add_argument("--paper", action="append", dest="papers",
                    help="Paper slug to include. Repeat to include multiple papers. Defaults to all public papers.")
    a = ap.parse_args()
    build(Path(a.out), run_tag=a.run_tag, paper_slugs=a.papers)
