<!-- Mirrors store docs/gaming-intelligence-eval-milestones.md -->

# Recommended next development milestones

Independent of #261. No merge/deploy/activation without owner OK.

| # | Milestone | Owner input? | Exit criterion |
| ---: | --- | --- | --- |
| M0 | Rate `gi-gta-label-sheet.csv` (≥20, prefer 30) via `gi-labeller.html` (v2 dimensions) | **Yes — blocking** | `compare` status ≠ blocked |
| M0b | Dual-rater ≥10 overlaps + adjudication | **Yes — blocking** | `agreement` reliability gate |
| M1 | Gap-hunt ≥3 misses + ordinary/weak draws on same VOD | Yes | Recall not only among proposals |
| M2 | Run A/B/C compare; publish exploratory or claim-ready report | No (once labelled) | Metrics with n_sources + limitations |
| M2b | ≥5 independent source recordings (streamer-separated held-out) | Yes — media | Source-level CI eligible |
| M3 | Weight-0 YAMNet/HUD offline precision on labelled seconds/frames | Labels for sounds/HUD | ≥0.90 propose-class or reject |
| M4 | Dataset B pilot 30/game across five titles | Yes — media | Multi-title transfer testable |
| M5 | Optional L4 scale-to-zero bench | **Yes — spend cap** | Measured $/hour vs CPU |
| M6 | Architecture A fusion promote one class | Yes — weight raise | Decision gates 1–6 + ΔP@5 practical |

**Stop conditions:** human labels absent; all six statistical decision gates fail; GPU purchase not approved. See [statistical-constraints/08-NEXT-EXPERIMENTS.md](../statistical-constraints/08-NEXT-EXPERIMENTS.md).
