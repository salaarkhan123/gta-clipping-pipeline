# Phase 1 harness

Offline tools that freeze the production selector, census evaluation assets and measure existing signals **without** changing ranking weights.

## Commands (from `clip-api/`)

```bash
python scripts/gaming_phase1_cli.py pin
python scripts/gaming_phase1_cli.py inventory
python scripts/gaming_phase1_cli.py metrics-demo
python scripts/gaming_phase1_cli.py baseline /path/to/video.mp4 --repeat --out /tmp/b0.json
python scripts/gaming_phase1_cli.py signals /path/to/video.mp4 --start 0 --length 40
pytest -q tests/test_gaming_phase1.py
```

## Artifacts

| Path | Role |
|---|---|
| [baseline-pin.json](baseline-pin.json) | Frozen SHA, production weights, experimental zero-weight list |
| [schemas/](schemas/) | Public schemas for source manifests and per-second event labels |
| [fixtures/](fixtures/) | Synthetic examples + evaluation denylist IDs |
| [PHASE1-FINDINGS.md](../PHASE1-FINDINGS.md) | Findings and owner asks |

Private media, consent records and human ratings stay outside Git.
