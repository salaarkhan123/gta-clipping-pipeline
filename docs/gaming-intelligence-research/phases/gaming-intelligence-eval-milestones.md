<!-- Mirrors store docs/gaming-intelligence-eval-milestones.md -->

# Recommended next development milestones

Independent of #261. No merge/deploy/activation without owner OK.

| # | Milestone | Owner input? | Exit criterion |
| ---: | --- | --- | --- |
| M0 | Rate `gi-gta-label-sheet.csv` (≥20, prefer 30) via `gi-labeller.html` | **Yes — blocking** | `compare` status ≠ blocked |
| M1 | Gap-hunt ≥3 misses on same VOD | Yes | Recall not only among proposals |
| M2 | Run A/B/C compare; publish exploratory or claim-ready report | No (once labelled) | Metrics with honest sample note |
| M3 | Weight-0 YAMNet/HUD offline precision on labelled seconds/frames | Labels for sounds/HUD | ≥0.90 propose-class or reject |
| M4 | Second title sheet (Valorant/CS2/…) | Yes — media | Transfer hypothesis testable |
| M5 | Optional L4 scale-to-zero bench | **Yes — spend cap** | Measured $/hour vs CPU |
| M6 | Architecture A fusion promote one class | Yes — weight raise | NDCG@5 gate vs B0 |

**Stop conditions already hit this turn:** human labels absent; GPU purchase not approved. Frameworks and labeller are ready for M0.
