<!-- Mirrors store docs/gaming-intelligence-ci-verification.md -->

# PR #262 CI verification report

**PR.** [#262](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/262) · head `213f65b` (plus follow-up commits on this eval pass) · base `main` @ `b74a3e7`  
**Date.** 2026-11-21

---

## Hosted checks (at verification start)

| Check | Status | Notes |
| --- | --- | --- |
| `docker-build` | **success** | Completed ~3 min |
| `test` | **in_progress** (Pytest step; >15 min wall as of eval push) | Will update when terminal; local GI 20 passed |

Local GI suites do not wait on hosted full pytest completion to ship research docs; hosted result is recorded when terminal.

---

## Local verification (this agent)

| Check | Result |
| --- | --- |
| `pytest -q tests/test_gaming_intelligence.py tests/test_gaming_phase1.py` | **20 passed** (was 18; +2 compare tests) |
| `GI_ENABLED` default | **False** |
| `DEFAULT_FAMILY_WEIGHTS` | all **0.0** |
| Production `WEIGHTS` | unchanged (`chat_motion` 1.0, audio 0.7, flux/bursts 0.35, scene 0.0) |
| `HUD_REGIONS` | `{}` |
| Product API / billing / deploy | **untouched** |
| Relation to #261 | Separate branch from `main`; **no rebase/merge** with `cursor/perf-staging-onto-main-8db9` |

---

## Compatibility with #261

#261 is the staging→main perf integration (source_audio, RENDER_WORKERS default 1, weight-0 scaffolds). This research PR:

- Does not modify those perf paths.
- Keeps GI behind `GI_ENABLED` / zero family weights.
- Can coexist: #261 may land weight-0 YAMNet/HUD modules; GI compare consumes their scores only when explicitly enabled later.

---

## Safety checklist

- [x] No merge of #262
- [x] No production deploy
- [x] No GI activation for users
- [x] No private media in git
- [x] No fabricated human labels
- [x] Metrics blocked until owner rates sheet
