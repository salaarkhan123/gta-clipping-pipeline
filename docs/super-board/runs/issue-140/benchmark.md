# Premium thumbnail benchmark (#140)

## Run 1: 2026-11-17, stopped at $0.00

Command (from `clip-api/`, keys loaded by Settings from its settings file, never printed):

```
python scripts/premium_thumb_bench.py <out> \
  --video ~/Downloads/GTA\ Benchmark/GTA_Benchmark_2Hours.mkv eval/benchmark-2h-labels.csv \
  --video ~/Downloads/wayin-benchmark/source-videos/<Zias & B Lou React To Drake - ICEMAN>.webm eval/wayin-zias-iceman.csv \
  --per-video 14 6 --max-usd 3.0 --max-calls 40
```

| Check | Result |
|---|---|
| Model id | `gemini-nano-banana-2.1`: the stable id on Google's model page; `GET /v1beta/models/gemini-nano-banana-2.1` answered 200 for this key |
| Gemini calls | 3, each answered **429**: "Rate limit exceeded for model gemini-nano-banana-2.1 (limit: 0 requests per day on Free Tier). Please upgrade your tier". The key's Google project has no billing, so this model has a quota of 0 |
| BFL fallback | 1 call, answered **402** `{"detail":"Insufficient credits"}`: marked "fallback unavailable (no balance)" and not called again |
| Generations | 3 tried, 0 made; the script stopped after 3 failures in a row, as designed |
| Spend | $0.00 (a 429 and a 402 are not billed) |
| Latency, quality | not measured: no image came back |

What the run did prove: the key reaches the model, the request reached Google's quota check rather than a 400
(the body was not rejected as malformed), the retry went to the fallback once, the fallback's "no balance" answer
was recognised, and the spending guard stopped the run.

## To finish it (owner)

1. Google AI Studio: turn on billing for the project of `GEMINI_API_KEY` (paid tier). The free tier has a quota of
   0 for Nano Banana 2.1.
2. Optional: add credit to the BFL account of `BFL_API_KEY` (about $1 covers the fallback's share).
3. Run the command above (about 20 x $0.055 = $1.10; capped at $3.00 and 40 calls). It writes
   `results.json`, `summary.md` and `sheet-N.jpg` (free left, premium right) in `<out>`.
