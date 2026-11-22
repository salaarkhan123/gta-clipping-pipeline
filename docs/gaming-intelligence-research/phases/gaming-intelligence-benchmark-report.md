<!-- Mirrors store docs/gaming-intelligence-benchmark-report.md -->

# Phase 6 — Benchmark report

**Date.** 2026-11-21 · branch `cursor/gaming-intelligence-research-8a00` · host CPU only.  
**Rules.** Measured vs estimated labeled. No false significance. No GPU purchase. Experimental weights remain **0**.

---

## Measured (this run)

| What | Result | Method |
| --- | --- | --- |
| GI unit tests | **18 passed** (`test_gaming_intelligence` + `test_gaming_phase1`) | `pytest -q` |
| Hook overhead (disabled) | median **~0.004 ms** / 40 candidates (n=80) | `gaming_intelligence_cli.py cpu-bench` |
| Hook overhead (enabled, all family weights 0) | median **~0.22 ms** / 40 candidates | same |
| Order change at weight 0 | **false** | unit test |
| Identity when `GI_ENABLED` unset | **true** | unit test |
| Label sheet export | **30** candidates, **0** human-rated | `export-sheet --from-labels-v2` |
| R2 GTA object | `head_object` **OK** (~3311 MB) | boto3; media **not** downloaded into store/PR |
| Eval inventory (#237 harness) | labels-v2 rated **0/30**; wayin **15/15**; HUD regions **0** | `inventory` / pin tests |

Artifact: CPU bench JSON written locally during the run (`kind=measured_cpu_gi_hook_overhead`). Not a quality claim.

---

## Not measured (honest gaps)

| Claim | Status |
| --- | --- |
| YAMNet / CLAP / PaddleOCR gaming P/R | **Gap** — needs labelled seconds/frames (#237 owner asks) |
| NDCG@5 / R@20 vs B0 with GI features | **Gap** — human rubric empty |
| Qwen3-VL verify quality / latency / VRAM | **Gap** — no GPU authorized |
| UniVTG localization on gaming prompts | **Gap** |
| End-to-end 2h Clip Maker with GI on | **Gap** — hooks research-only; product path unchanged |
| Paired significance vs B0 | **Not claimed** — n=0 rated GI rows |

Historical reference only (from #237, not re-run as new significance): Wayin overlap **7/15**; YouNiverse title-marker study **no boost**.

---

## Estimates (not measurements)

| Item | Estimate | Source |
| --- | --- | --- |
| L4 compute at 15 billed min / source hour | **$0.1725** / source hour | list $0.69/h × 0.25 h — `estimate-gpu` |
| Same assumption on CPU C6 | **$0.040** | $0.16/h |
| RTX 4090 same assumption | **$0.2225** | $0.89/h |

These share a **sensitivity assumption** (15 min/source hour). Actual ClutchClips GPU wall time is **not measured**.

---

## Interpretation

1. The GI Python hook is cheap on CPU when enabled with zero weights; it does not reorder candidates.
2. Quality gates cannot be scored until humans fill the GI label sheet / #237 asks.
3. Do not raise weights or rent GPU from this report.

Reproduce:

```bash
cd clip-api
python3 -m pytest -q tests/test_gaming_intelligence.py tests/test_gaming_phase1.py
python3 scripts/gaming_intelligence_cli.py cpu-bench -o /tmp/gi-cpu-bench.json
python3 scripts/gaming_intelligence_cli.py estimate-gpu --sku l4 --minutes 15
```
