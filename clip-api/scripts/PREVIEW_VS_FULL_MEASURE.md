# Preview vs full render measurement (Wave A1 / S2)

Measure TTFC and encode cost of `render=preview` against `render=full` on the same upload. This is the PR-A1 harness from the performance research roadmap — scaffolding only until staging runs a real ~2h VOD.

## What to compare

| Field | Where | Meaning |
|---|---|---|
| `first_clip_sec` | `job_timings.py --json` | Queue included: seconds until the first clip is watchable |
| `stages.render` / `render_sec` | fine stage row `render` | Encode time for all clips |
| `total_sec` | job result | Queue + run end-to-end |

Do **not** change `max_clips`, `clip_length`, template, weights, or source between the pair.

## Staging recipe

From `clip-api/`:

```bash
python scripts/measure_preview_vs_full.py --dry-run \
  --api "$STAGING_API" --upload-id "$UPLOAD_ID" --max-clips 10 --clip-length 30
```

Follow the printed `recipe` steps (two `POST /v1/clips`, poll, save `preview.json` / `full.json`). Then:

```bash
python scripts/job_timings.py preview.json --json
python scripts/job_timings.py full.json --json
python scripts/job_timings.py preview.json --baseline full.json --md
python scripts/measure_preview_vs_full.py --preview-job preview.json --full-job full.json
```

Paste the markdown table and the harness JSON into the speed PR. Label claim status from the harness `claim` block.

## Local short fixture (smoke)

No 2h VOD on agent VMs. For a parse/smoke check only:

```bash
python scripts/measure_preview_vs_full.py --local /path/to/short.mp4 \
  --transcriber none --max-clips 2 --clip-length 10 --out-dir /tmp/pvf
```

The report always sets `claim.2h_vod` to `not measured` for local runs.

## Claim labels

- **measured** — pair came from finished job JSON (or a local dual run); source length ≥ ~110 min marks `2h_vod` measured.
- **not measured** — default for 2h VOD until staging fills real numbers. Never invent timings.
