#!/usr/bin/env python3
"""Regenerate the compare-app average-aspect figure from the staged summary."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "data" / "compare-app-benchmark" / "data" / "data_summary.json"
OUT_STEM = ROOT / "code" / "figure-reproduction" / "generated" / "compare_app_average_aspects"
SCRIPT = ROOT / "code" / "scripts" / "plot_compare_app_aspects.py"

subprocess.run(
    [
        sys.executable,
        str(SCRIPT),
        "plot-summary",
        "--summary-path",
        str(SUMMARY),
        "--out-stem",
        str(OUT_STEM),
    ],
    check=True,
)
