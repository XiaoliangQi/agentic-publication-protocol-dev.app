#!/usr/bin/env python3
"""Extract and plot compare-app per-aspect scores for the paper.

Step 1 extracts scores from compare-app evaluation artifacts into a compact JSON
summary. Step 2 plots directly from that summary and prints the LaTeX table rows
and aggregate means used in the paper.

By default, extraction uses `data/compare-app-benchmark/data/compare_app.jsonl`.
To extract directly from a workspace run, pass `--input-root working/compare-app
--run-tag <tag>`.

Usage:
    python3 code/scripts/plot_compare_app_aspects.py extract-summary
    python3 code/scripts/plot_compare_app_aspects.py plot-summary
    python3 code/scripts/plot_compare_app_aspects.py extract-summary --from-records --input-root working/compare-app --run-tag 20260613-pr34-rerun-pathfix
"""
import argparse
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_ROOT = REPO / "data" / "compare-app-benchmark" / "paper-records"
DEFAULT_JSONL = REPO / "data" / "compare-app-benchmark" / "data" / "compare_app.jsonl"
DEFAULT_SUMMARY = REPO / "data" / "compare-app-benchmark" / "data" / "data_summary.json"
DEFAULT_OUT_STEM = REPO / "paper" / "figures" / "compare_app_average_aspects"
ASPECT_KEYS = ["accuracy", "informativeness", "grounding", "honesty"]
ASPECT_LABELS = ["Accuracy", "Informativeness", "Grounding", "Honesty"]
APP_BLUE = "#2e6e9e"
GEN_ORANGE = "#c87d1f"

# 11 public papers, in the paper's Table order: (arxiv id, cite key, example slug)
PUBLIC = [
    ("2006.12469", "cha2020attention", "attention-tomography"),
    ("2412.03356", "karakosta2024freespace", "balloon-qnet"),
    ("2005.12702", "perlin2020circuit", "circuit-cutting-mlft"),
    ("1703.10587", "barghathi2017particle", "fermion-entanglement"),
    ("2411.03110", "perezsalinas2024multiple", "mbr-states"),
    ("2203.09758", "liu2022optimal", "metrology-hierarchy"),
    ("2605.13271", "kumar2026oam", "oam-gkp-metrology"),
    ("2306.12711", "mullerrigat2023certifying", "qfi-certification"),
    ("2310.02075", "wadhwa2023learning", "qpsq-learning"),
    ("2007.06989", "sokolov2020emergent", "spinchain-entanglement"),
    ("2012.01459", "malz2020topological", "topological-floquet"),
]


def aspect_scores(report_text, label):
    """Return [acc, info, grnd, hon] for an anonymized agent label."""
    m = re.search(
        rf"\|\s*{re.escape(label)}\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        report_text,
    )
    if m:
        return [int(m.group(i)) for i in range(1, 5)]
    block = re.search(
        rf"\*\*{label}\*\*(.*?)(?=\*\*Agent|\*\*Comparative|\Z)", report_text, re.S
    )
    if block:
        nums = re.findall(r"_score:\s*(\d+)", block.group(1))
        if len(nums) >= 4:
            return [int(x) for x in nums[:4]]
    raise ValueError(f"could not parse aspect scores for {label}")


def record_dir(input_root, slug, run_tag=None):
    """Return the artifact directory for one paper slug."""
    if run_tag:
        return input_root / slug / run_tag
    return input_root / slug


def load(input_root, slug, run_tag=None):
    d = record_dir(input_root, slug, run_tag)
    if not d.exists():
        if run_tag:
            hint = f"missing run directory for {slug}: {d}"
        else:
            hint = (
                f"missing record directory for {slug}: {d}\n"
                "For workspace runs, pass --input-root working/compare-app --run-tag <tag>."
            )
        raise FileNotFoundError(hint)
    report = (d / "evaluation-report.md").read_text(encoding="utf-8")
    mapping = json.loads((d / "run-summary.json").read_text())["evaluator_label_mapping"]
    by_kind = {mapping["Agent A"]: aspect_scores(report, "Agent A"),
               mapping["Agent B"]: aspect_scores(report, "Agent B")}
    return by_kind["paper-agent"], by_kind["general-agent"], mapping, d


def selected_public(papers):
    if not papers:
        return PUBLIC
    wanted = set(papers)
    known = {slug for _, _, slug in PUBLIC}
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(f"unknown paper slug(s): {', '.join(unknown)}")
    return [paper for paper in PUBLIC if paper[2] in wanted]


def display_path(path):
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def resolve_path(path):
    path = Path(path)
    if not path.is_absolute():
        path = REPO / path
    return path


def score_dict(scores):
    return dict(zip(ASPECT_KEYS, scores))


def score_list(scores):
    return [scores[key] for key in ASPECT_KEYS]


def average(scores):
    return sum(score_list(scores)) / len(ASPECT_KEYS)


def result_label(paper_scores, general_scores):
    pa = average(paper_scores)
    ga = average(general_scores)
    return "APP" if pa > ga else ("general" if ga > pa else "tie")


def extract_summary(input_root, run_tag=None, papers=None):
    input_root = resolve_path(input_root)
    source = display_path(input_root)
    if run_tag:
        source = f"{source}/<slug>/{run_tag}"
    else:
        source = f"{source}/<slug>"

    rows = []
    for aid, cite, slug in selected_public(papers):
        paper_scores, general_scores, mapping, artifact_dir = load(input_root, slug, run_tag)
        paper_scores = score_dict(paper_scores)
        general_scores = score_dict(general_scores)
        rows.append({
            "slug": slug,
            "arxiv_id": aid,
            "cite_key": cite,
            "artifact_dir": display_path(artifact_dir),
            "evaluator_label_mapping": mapping,
            "paper_agent_scores": paper_scores,
            "general_agent_scores": general_scores,
            "paper_agent_avg": round(average(paper_scores), 2),
            "general_agent_avg": round(average(general_scores), 2),
            "result": result_label(paper_scores, general_scores),
        })

    return {
        "schema_version": 1,
        "description": "Compare-app per-paper evaluation scores used to plot average aspect scores.",
        "source": {
            "input_records": source,
            "run_tag": run_tag,
        },
        "aspects": ASPECT_KEYS,
        "papers": rows,
    }


def public_metadata_by_slug():
    return {slug: {"arxiv_id": aid, "cite_key": cite} for aid, cite, slug in PUBLIC}


def extract_summary_from_jsonl(jsonl_path, papers=None):
    jsonl_path = resolve_path(jsonl_path)
    wanted = set(papers or [])
    known = {slug for _, _, slug in PUBLIC}
    unknown = sorted(wanted - known)
    if unknown:
        raise ValueError(f"unknown paper slug(s): {', '.join(unknown)}")

    meta = public_metadata_by_slug()
    rows = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            slug = record["example"]
            if wanted and slug not in wanted:
                continue
            if slug not in meta:
                raise ValueError(f"JSONL contains unknown public paper slug: {slug}")
            paper_scores = {
                key: int(record["paper_agent_scores"][key])
                for key in ASPECT_KEYS
            }
            general_scores = {
                key: int(record["general_agent_scores"][key])
                for key in ASPECT_KEYS
            }
            rows.append({
                "slug": slug,
                "arxiv_id": record.get("arxiv_id", meta[slug]["arxiv_id"]),
                "cite_key": meta[slug]["cite_key"],
                "artifact_dir": record.get("evaluation_input_path", ""),
                "evaluator_label_mapping": record.get("evaluator_label_mapping", {}),
                "paper_agent_scores": paper_scores,
                "general_agent_scores": general_scores,
                "paper_agent_avg": round(average(paper_scores), 2),
                "general_agent_avg": round(average(general_scores), 2),
                "result": result_label(paper_scores, general_scores),
            })

    order = {slug: i for i, (_, _, slug) in enumerate(PUBLIC)}
    rows.sort(key=lambda row: order[row["slug"]])
    return {
        "schema_version": 1,
        "description": "Compare-app per-paper evaluation scores used to plot average aspect scores.",
        "source": {
            "input_records": display_path(jsonl_path),
            "run_tag": None,
        },
        "aspects": ASPECT_KEYS,
        "papers": rows,
    }


def write_summary(args):
    if not args.from_records:
        summary = extract_summary_from_jsonl(args.input_jsonl, papers=args.papers)
    else:
        summary = extract_summary(args.input_root, run_tag=args.run_tag, papers=args.papers)
    summary_path = resolve_path(args.summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {display_path(summary_path)}")
    print(f"papers: {len(summary['papers'])}")
    print(f"input records: {summary['source']['input_records']}")


def read_summary(summary_path):
    summary_path = resolve_path(summary_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    missing = [key for key in ["schema_version", "aspects", "papers"] if key not in summary]
    if missing:
        raise ValueError(f"summary missing required field(s): {', '.join(missing)}")
    if summary["aspects"] != ASPECT_KEYS:
        raise ValueError(f"expected aspects {ASPECT_KEYS}, got {summary['aspects']}")
    return summary, summary_path


def print_table_and_means(summary):
    paper_rows, gen_rows = [], []
    source = summary.get("source", {}).get("input_records", "unknown")
    print(f"% input summary source: {source}")
    print("% --- compare-app Table rows (regenerated; paste into table:compare-app) ---")
    for row in summary["papers"]:
        p = score_list(row["paper_agent_scores"])
        g = score_list(row["general_agent_scores"])
        paper_rows.append(p)
        gen_rows.append(g)
        pa, ga = sum(p) / 4, sum(g) / 4
        res = row.get("result", "APP" if pa > ga else ("general" if ga > pa else "tie"))
        head = f"arXiv:{row['arxiv_id']} \\cite{{{row['cite_key']}}}"
        print(f"            {head:<56}& {p[0]:<4}& {p[1]:<5}& {p[2]:<5}& {p[3]:<4}& "
              f"{pa:.2f} & {g[0]:<4}& {g[1]:<5}& {g[2]:<5}& {g[3]:<4}& {ga:.2f} & {res:<7}\\\\")

    P = np.array(paper_rows, float)
    G = np.array(gen_rows, float)
    pmean, gmean = P.mean(axis=0), G.mean(axis=0)
    print("\n% aspect means (APP / general):")
    for a, pm, gm in zip(ASPECT_LABELS, pmean, gmean):
        print(f"%   {a:<16} {pm:.2f} / {gm:.2f}")
    print(f"% overall mean: APP {P.mean():.2f} / general {G.mean():.2f}")
    return pmean, gmean


def plot_summary(args):
    summary, summary_path = read_summary(args.summary_path)
    print(f"% summary: {display_path(summary_path)}")
    pmean, gmean = print_table_and_means(summary)

    x = np.arange(len(ASPECT_LABELS))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10, 5))
    b1 = ax.bar(x - w / 2, pmean, w, label="APP agent", color=APP_BLUE)
    b2 = ax.bar(x + w / 2, gmean, w, label="General agent", color=GEN_ORANGE)
    for bars in (b1, b2):
        ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=12)
    ax.set_ylim(0, 10)
    ax.set_ylabel("Mean score", fontsize=14)
    ax.set_xticks(x, ASPECT_LABELS, fontsize=13)
    ax.tick_params(axis="y", labelsize=12)
    ax.legend(loc="upper center", ncol=2, frameon=False, fontsize=13,
              bbox_to_anchor=(0.5, 1.10))
    ax.yaxis.grid(True, color="0.9")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    out_stem = resolve_path(args.out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_stem.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out_stem.with_suffix(".png"), dpi=200, bbox_inches="tight")
    print(f"\nwrote {out_stem}.pdf and {out_stem}.png")


def add_extract_args(parser):
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        default=DEFAULT_JSONL,
        help="JSONL dataset file containing per-paper scores.",
    )
    parser.add_argument(
        "--from-records",
        action="store_true",
        help="Extract from per-paper record directories instead of --input-jsonl.",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DEFAULT_INPUT_ROOT,
        help=(
            "Directory containing per-paper records, used with --from-records. "
            "For workspace runs use working/compare-app."
        ),
    )
    parser.add_argument(
        "--run-tag",
        help=(
            "Optional run tag for workspace layout: <input-root>/<slug>/<run-tag>. "
            "Omit for dataset layout: <input-root>/<slug>."
        ),
    )
    parser.add_argument(
        "--paper",
        action="append",
        dest="papers",
        help="Paper slug to include. Repeat to include multiple papers. Defaults to all public papers.",
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_SUMMARY,
        help="Path for the extracted JSON summary.",
    )


def add_plot_args(parser):
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=DEFAULT_SUMMARY,
        help="Path to the JSON score summary produced by extract-summary.",
    )
    parser.add_argument(
        "--out-stem",
        type=Path,
        default=DEFAULT_OUT_STEM,
        help="Output path without extension for the PDF/PNG figure.",
    )


def main():
    ap = argparse.ArgumentParser(
        description="Extract compare-app score summaries and plot aspect means."
    )
    sub = ap.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract-summary", help="Extract per-paper scores into a JSON summary.")
    add_extract_args(extract)
    extract.set_defaults(func=write_summary)

    plot = sub.add_parser("plot-summary", help="Plot aspect means from a JSON summary.")
    add_plot_args(plot)
    plot.set_defaults(func=plot_summary)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
