# 2. Dataset collection and labeling specification

## Dataset A — Online reference clips

**Purpose.** Study characteristics of successful published gaming content.  
**Not** ground-truth highlight quality. Popularity must not be treated as GT.

| Spec | Value |
| --- | --- |
| Games | GTA, Warzone, Fortnite, Valorant, Counter-Strike 2 |
| Target | **30 clips per game** (150 total pilot) |
| Template | `clip-api/eval/datasets/dataset-a-template.csv` |
| Manifest | `clip-api/eval/datasets/dataset-a-manifest.json` |

### Required metadata (when a clip is ingested)

- Permission / consent record ID (only content we have permission to use)
- Source / platform / opaque ID
- Publisher date, game, duration
- Engagement fields **if available** (views, likes, age at measurement) — blank if unknown; never invent
- Creator audience size at post when known (confounder)
- Editing characteristics and other confounders (title/thumbnail/collab/etc.)

### Rules

1. Confirm ownership or permission before ingest; log source, account, time (product rule).
2. Do not download around blocks, DRM, or age gates.
3. Do not interpret high views as proof the underlying play is a high-quality highlight.
4. Keep Dataset A analysis separate from Dataset B highlight-quality claims.
5. Raw media stays out of Git.

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py init-dataset-a -o eval/datasets/dataset-a-template.csv
python3 scripts/gaming_intelligence_cli.py dataset-census A eval/datasets/dataset-a-template.csv
```

---

## Dataset B — ClutchClips evaluation

**Purpose.** Evaluate highlight detection/ranking on permitted raw gameplay.  
**Pilot target.** 30 candidate clips per game (same five titles).

| Spec | Value |
| --- | --- |
| Template | `clip-api/eval/datasets/dataset-b-template.csv` |
| Manifest | `clip-api/eval/datasets/dataset-b-manifest.json` |
| Splits | `development` · `held_out_eval` grouped by **source recording** |
| Streamer separation | Prefer streamer-disjoint splits (`validate-splits`) |

### Required machine fields

- `source_recording_id`, timestamps, `streamer_id` (pseudonym)
- `model_version`, `code_version`, detector scores JSON
- `candidate_source` (baseline | gi | grid | gap_hunt | ordinary_draw)
- `is_ordinary_or_weak` — deliberately include ordinary gameplay and weak moments
- `permission_record_id`

### Split rules

1. Assign held-out by **recording ID**, not by random clip.
2. Near-duplicates / same match travel together.
3. **Never train or optimize** using held-out evaluation labels.
4. Eval denylist VODs (`phase1/fixtures/denylist-eval-ids.json`) stay evaluation-only.

```bash
python3 scripts/gaming_intelligence_cli.py init-dataset-b -o eval/datasets/dataset-b-template.csv
python3 scripts/gaming_intelligence_cli.py validate-splits eval/datasets/dataset-b-template.csv
```

Existing GTA sheet (`eval/gi-gta-label-sheet.csv`, 30 proposals from one VOD) is the **first Dataset B-style pilot seed**. It is proposal-biased until gap-hunt / ordinary draws are added.

---

## Human labeling (1–5 rubric)

Use `clip-api/eval/gi-labeller.html`. Dimensions stay **separate** — no automatic weighted composite for claims.

| Dimension | 1 | 3 | 5 |
| --- | --- | --- | --- |
| **Entertainment quality** | Boring / skip | Mildly watchable | Strong entertainment |
| **Gameplay significance** | Routine / filler | Notable for mode | Decisive / rare play |
| **Opening hook** | No reason to stay | Weak tease | Immediate stop-scroll |
| **Context / understandability** | Needs full VOD | Partial with effort | Self-contained for cold viewers |
| **Editing suitability** | Unusable cut | Fixable with trim | Clean publishable boundaries |
| **Genuine highlight** | `no` / `maybe` / `yes` | — | Classification, not 1–5 |

Optional legacy: `quality_1_5`, platform suitability, `clutch_correct`.

### Dual-rater protocol

1. Two independent reviewers with distinct `rater` ids; blind to system scores and engagement.
2. Compute agreement: `gaming_intelligence_cli.py agreement --primary a.csv --secondary b.csv`
3. Flag absolute ordinal diffs ≥2 and categorical mismatches for adjudication.
4. Reliability gate: weighted kappa ≥0.6 on ≥10 pairs (or categorical agreement ≥0.8).
5. **Never** fabricate ratings or copy model predictions into human fields.

A row is complete (v2) when entertainment, gameplay significance, opening hook, context, editing suitability, and genuine highlight are filled.
