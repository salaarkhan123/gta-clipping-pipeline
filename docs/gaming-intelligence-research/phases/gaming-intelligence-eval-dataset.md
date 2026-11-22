<!-- Mirrors store docs/gaming-intelligence-eval-dataset.md -->

# Phase 4 — GTA eval dataset & labeling

30 candidates exported from existing pipeline (`labels-v2`). Human schema: quality/entertainment/context (1–5), platform suitability, `genuine_highlight`, `clutch_correct`. Clutch scores are proposals only.

| Tool | Path |
| --- | --- |
| Sheet | `clip-api/eval/gi-gta-label-sheet.csv` |
| Labeller | `clip-api/eval/gi-labeller.html` |
| Workflow | [labeling-workflow](gaming-intelligence-labeling-workflow.md) |
| Compare | [comparison-framework](gaming-intelligence-comparison-framework.md) |

**Census:** 0/30 complete human ratings → `compare` status `blocked_no_human_labels`.
