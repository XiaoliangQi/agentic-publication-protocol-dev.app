# Figure and Table Reproduction

Run commands from the repository root.

Generated outputs are written to `code/figure-reproduction/generated/`, which is
ignored by Git.

| Figure/Table | Paper artifact | Script | Inputs | Generated output | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Fig. `publication-repo-structure` | `paper/figures/publication-repo-structure.pdf` | none | `paper/figures/publication-repo-structure.drawio` | none | `manual-only` | Requires Draw.io export; Draw.io was not installed during validation. |
| Fig. `publication-workflow` | `paper/figures/publish_workflow.pdf` | none | `paper/figures/publish_workflow.drawio` | none | `manual-only` | Requires Draw.io export; Draw.io was not installed during validation. |
| Fig. `publication-workflow` | `paper/figures/publish_paper_steps.pdf` | none | `paper/figures/publish_paper_steps.drawio` | none | `manual-only` | Requires Draw.io export; Draw.io was not installed during validation. |
| Fig. `auto-improvement-workflow` | `paper/figures/auto_improvement_workflow.pdf` | none | `paper/figures/auto_improvement_workflow.drawio` | none | `manual-only` | Requires Draw.io export; Draw.io was not installed during validation. |
| Table `compare-app` | table in `paper/app-paper.tex` | `table_compare_app_scores.py` | `data/compare-app-benchmark/data/data_summary.json` | terminal table rows and means | `reproduced` | Values reproduce the paper table and aggregate means. |
| Fig. `compare-app-average` | `paper/figures/compare_app_average_aspects.pdf`, `.png` | `fig_compare_app_average_aspects.py` | `data/compare-app-benchmark/data/data_summary.json` | `generated/compare_app_average_aspects.pdf`, `.png` | `runs-but-differs` | Regenerated files are semantically consistent but not byte-identical to committed artifacts. |
| Fig. `research-network` | `paper/figures/research_network.pdf`, `.png`, `.svg` | `fig_research_network.py` | `paper/figures/make_research_network.py` | `generated/research_network.pdf`, `.png`, `.svg` | `runs-but-differs` | PNG reproduced byte-identically in the dev validation; PDF/SVG differed, likely from backend metadata. |

Example:

```bash
python3 code/figure-reproduction/table_compare_app_scores.py
python3 code/figure-reproduction/fig_compare_app_average_aspects.py
python3 code/figure-reproduction/fig_research_network.py
```
