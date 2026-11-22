# Gaming AI quality / highlight rating (AS-1)

Interpretable **0–100** highlight-quality scores with nine stored components. This is an AI
opinion of the cut — **not** a virality probability, view forecast, or chance of going viral.

## Components

| Key | Label |
| --- | --- |
| `hook` | Hook |
| `intensity` | Intensity |
| `kills_clutches` | Kills / clutches |
| `funny` | Funny |
| `reactions` | Reactions |
| `audio` | Audio |
| `chat` | Chat |
| `unexpected` | Unexpected |
| `game_context` | Game context |

Defined in `app/gaming_rating.py`. Judge schema + parse: `app/ai.py` (`gaming` tool field,
`scoring_version` `judge-v3-gaming`). Editorial five (`hook` / `payoff` / `clarity` / `emotion` /
`pacing`) remain in `meta.scores` for `SCORE_WEIGHTS` / `rank_score`.

Display calibration (`app/scoring.py`) is still display-only across a job.

## Label sheet path (no fake labels)

Reuse the GI sheet from research (#262 methodology):

```bash
cd clip-api
python scripts/gaming_rating_eval.py sheet-stats eval/gi-gta-label-sheet.csv
```

`eval/gi-gta-label-sheet.csv` ships with **empty** human rating columns. Do not invent NDCG or
precision until the owner fills rows. Also see `eval/README.md` (`labels-v2.csv`) and #237 asks.

## Ablation hooks

```bash
python scripts/gaming_rating_eval.py ablate --hook 80 --intensity 70 --kills_clutches 60 \
  --funny 40 --reactions 75 --audio 65 --chat 20 --unexpected 55 --game_context 70
```

Prints full composite plus leave-one-out (`drop:`) and zero-out (`zero:`) composites. Used to
measure which components move ranking once labels exist — never to claim virality %.
