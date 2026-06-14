# Data

This first APP publication includes the compact summary needed to reproduce the
compare-app score table and average-aspect figure in the paper.

Included local data:

- `compare-app-benchmark/data/data_summary.json` - per-paper scores for all 11
  public papers on accuracy, informativeness, grounding, and honesty, with
  averages for the APP paper agent and the general repository-aware agent.
- `example-papers/` - intentionally empty in this release. Future runs can add
  public source examples here and generate working artifacts from them.

The full public benchmark dataset, including `compare_app.jsonl`, question
plans, transcripts, evaluation reports, and run summaries, is hosted on Hugging
Face:

- https://huggingface.co/datasets/phynics/agentic-publication-protocol-dataset

The compact summary records:

- 11 public quantum-physics papers.
- Evaluator model: Codex CLI, gpt-5.5, reasoning effort xhigh.
- Criteria: accuracy, informativeness, grounding, honesty.
- Result: APP paper agent wins 11/11; mean overall score 9.25 versus 8.50 for
  the general repository-aware agent.

The plotting entry point is:

```bash
python3 code/scripts/plot_compare_app_aspects.py plot-summary \
  --summary-path data/compare-app-benchmark/data/data_summary.json
```
