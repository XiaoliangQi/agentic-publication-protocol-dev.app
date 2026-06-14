#!/usr/bin/env python3
"""Regenerate the research-network figure into the generated output folder."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "paper" / "figures" / "make_research_network.py"
GENERATED = ROOT / "code" / "figure-reproduction" / "generated"

GENERATED.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    work_script = tmp_path / "make_research_network.py"
    shutil.copy2(SOURCE, work_script)
    subprocess.run([sys.executable, str(work_script)], cwd=tmp_path, check=True)
    for suffix in [".pdf", ".png", ".svg"]:
        shutil.copy2(tmp_path / f"research_network{suffix}", GENERATED / f"research_network{suffix}")
