#!/usr/bin/env python3
"""Print compare-app table rows and aggregate means from the staged summary."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "data" / "compare-app-benchmark" / "data" / "data_summary.json"
SCRIPT = ROOT / "code" / "scripts" / "plot_compare_app_aspects.py"

subprocess.run(
    [
        sys.executable,
        str(SCRIPT),
        "plot-summary",
        "--summary-path",
        str(SUMMARY),
        "--out-stem",
        str(ROOT / "code" / "figure-reproduction" / "generated" / "compare_app_average_aspects"),
    ],
    check=True,
)
