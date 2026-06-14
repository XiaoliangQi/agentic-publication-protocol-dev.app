**Validation Transcript**

1. **Ground truth vs. secondary context**  
   The ground truth is the publication repository’s included manuscript, code, and data, especially `paper/app-paper.tex`, `paper/app-paper.pdf`, `code/`, and `data/`. Supplementary materials and bundled skills in `supplementary/` and `skills/` are useful operational context, but secondary.

2. **Main contribution / thesis**  
   The paper argues for the Agentic Publication Protocol: a lightweight publication format that bundles a paper with code, data, environment notes, reproduction instructions, and `AGENTS.md` so readers can interact with a grounded paper agent. Its thesis is that scientific publications should carry operational know-how, not only static final claims.

3. **Exact reproduction / compile commands**  
   From the repository root, reproduce the compare-app table:

   ```bash
   python3 code/figure-reproduction/table_compare_app_scores.py
   ```

   From the repository root, reproduce the compare-app average figure:

   ```bash
   python3 code/figure-reproduction/fig_compare_app_average_aspects.py
   ```

   Compile the paper from `paper/`:

   ```bash
   latexmk -pdf -interaction=nonstopmode -halt-on-error app-paper.tex
   ```

4. **Reproduction limitations / manual-only items**  
   Per `code/figure-reproduction/README.md`, the Draw.io workflow figures are `manual-only`: `paper/figures/publication-repo-structure.drawio`, `paper/figures/publish_workflow.drawio`, `paper/figures/publish_paper_steps.drawio`, and `paper/figures/auto_improvement_workflow.drawio` require Draw.io export. The compare-app average figure regenerates from `data/compare-app-benchmark/data/data_summary.json`, but generated PDF/PNG files are not expected to be byte-identical to committed artifacts. The research-network PNG reproduced byte-identically in validation, while PDF/SVG may differ due to backend metadata. Bibliography API checks require network access and may produce manual-review notes for bot-blocked URLs.

Assessment: The local `AGENTS.md` instructions were sufficient to answer these smoke-test questions from repository-local sources.