<!-- Mirrors store docs/gaming-intelligence-eval-dataset.md · extends #237 harness / eval_clips -->

# Phase 4 — GTA eval dataset & labeling workflow

**Status.** Schema + workflow only. No fabricated human ratings. ClutchClips scores are **proposals**, not ground truth.

**Reuse.** [#237](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/237) Phase 1 harness (`scripts/gaming_phase1/`), `scripts/eval_clips.py`, `eval/labels-v2.csv` (30 unrated intervals), `eval/labeller.html`. Rubric: [entertainment rubric](gaming-intelligence-entertainment-rubric.md).

---

## Candidate source (machine)

| Source | Rows | Role |
| --- | ---: | --- |
| `eval/labels-v2.csv` | 30 | Existing pipeline nominations for `gta-online-1` — export as GI sheet |
| Job / run JSON (`clips[].start_sec/end_sec`) | variable | Fresh candidates via `candidates_from_run` |
| `eval/benchmark-2h-labels.csv` | 46 | 2h north-star sheet — still **0** human labels |
| Synthetic Phase 1 fixtures | harness only | Determinism; not entertainment GT |

Export command (leaves all human rubric fields blank):

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py export-sheet \
  --from-labels-v2 eval/labels-v2.csv \
  -o eval/gi-gta-label-sheet.csv
python3 scripts/gaming_intelligence_cli.py sheet-stats eval/gi-gta-label-sheet.csv
```

Sheet columns: candidate fields (`id,vod,game,start,end,source,clutch_rank,clutch_score`) + human fields (`hook,stakes,payoff,reaction,clarity,novelty,completeness,publish,event_tags,notes,rater,rated_at`).

---

## Labeling workflow (human)

1. Open intervals in the source VOD (owner media; not committed). Prefer `eval/labeller.html` or a spreadsheet of the exported CSV.
2. Rate **rubric dimensions 0–3** per [entertainment rubric](gaming-intelligence-entertainment-rubric.md). Do **not** copy `clutch_score` into rubric cells.
3. Set `publish` to `yes` / `no` / `maybe`.
4. Optional `event_tags` (gunfight, crash, dialogue, …) for detector eval — separate from entertainment.
5. Dual-annotator pilot on ≥20 rows when two raters available; record disagreements in `notes`.
6. Consent / use record per VOD (playback, annotation, embeddings) — owner gate from #237 PHASE1-FINDINGS.

**Explicit non-actions.** Do not invent ratings to fill the sheet. Do not scrape social platforms for labels. Do not put private media in the git tree or Project store.

---

## Metrics once rated

Reuse `eval_clips.py` (P@20/40 ranges, recall of 3s) and `scripts/gaming_phase1/metrics.py` (NDCG@5, event P/R, tIoU). Map rubric → gain: e.g. `publish=yes` → gain 3; `maybe` → 1; `no` → 0 (preregister before A/B).

---

## Census on this branch (2026-11-21)

| Asset | Human-rated |
| --- | --- |
| labels-v2 / GI export | **0 / 30** |
| benchmark-2h | **0 / 46** |
| wayin historical proxies | 15/15 competitor overlap only — not GI rubric |

R2 GTA object is reachable on research hosts via existing secrets (`head_object` OK, ~3.3 GB). Media stays out of artifacts; only timestamps/aggregates may be published.
