# Environment

Tested locally on macOS with Python 3, matplotlib, Git, GitHub CLI, and TeX
Live/latexmk available.

From the repository root, the plotting script can be run with:

```bash
python3 code/scripts/plot_compare_app_aspects.py plot-summary \
  --summary-path data/compare-app-benchmark/data/data_summary.json \
  --out-stem code/figure-reproduction/generated/compare_app_average_aspects
```

The paper can be compiled from `paper/` with:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error app-paper.tex
```

The bibliography audit can be run from the repository root with:

```bash
python3 code/scripts/check_bib_against_apis.py paper/refs.bib
```

Manual or external requirements:

- Draw.io is required to regenerate the `.drawio` workflow figures.
- Network access is required for the bibliography API audit.
- Some URL checks may return 403 because of bot blocking; this was observed
  during validation and treated as manual-review notes, not missing sources.

Local generated outputs should stay untracked. The intended generated output
directory is `code/figure-reproduction/generated/`.
