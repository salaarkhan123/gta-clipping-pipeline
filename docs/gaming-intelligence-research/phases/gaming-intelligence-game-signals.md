<!-- Mirrors store docs/gaming-intelligence-game-signals.md -->

# Gaming-specific feature research (CPU-first)

**Rule.** Do not assume one title’s signals generalize. Experimental weights stay **0** until labelled precision gates pass. Reuses #237 taxonomy / detectors docs.

---

## Shared Tier-0 (already on main)

| Signal | Use | Limit |
| --- | --- | --- |
| Audio RMS / flux / bursts | Loud action, impacts, laughter rhythm | Misses quiet RP punchlines; combat false positives |
| Faster-Whisper + judge sub-scores | Narrative / reaction language | Costly; opinion ≠ views |
| CLIP every 2 s | Visual search / similarity | Sparse; not kill detection |
| chat_motion | Chat scroll proxy | Needs region; not IRC text |
| scene (weight 0) | Cut / standby | Decode cost; keep off until shared decode |

---

## Per-title lightweight opportunities

| Title | High-value events | CPU-first features to pilot (weight 0) | Do **not** assume |
| --- | --- | --- | --- |
| **GTA V / RP** | Chase payoff, crash, funny dialogue reverse, mission banner, wasted/busted | Named sounds (siren/crash/gunshot); HUD banner lexicon OCR; transcript setup→payoff windows | Shooter killfeed logic |
| **CoD / Warzone** | Elimination, multi-kill, gulag, buy-station chaos, squad wipe | Killfeed OCR on measured ROI; gunshot/explosion YAMNet; short reaction lag after kill | GTA chase audio priors |
| **Fortnite** | Elimination, third-party, zone close, emote fail | Banner/elim text OCR; storm/zone visual change sparingly; crowd/cheer audio weak | CS utility nades |
| **Valorant** | Ace, clutch, spike plant/defuse, eco win | Spike/plant audio+HUD; killfeed; agent ultimate audio classes carefully | Open-world RP dialogue |
| **CS2** | Ace, clutch, eco, bomb plant/defuse, nade lineup fail | Bomb timer/HUD; plant/defuse audio; killfeed; freeze-time reject | Fortnite build fights |

---

## Event families (cross-check, not one model)

1. **Eliminations / multikills** — HUD text + optional sound; suppress spectator POV when detectable.
2. **Clutch / high-stakes** — context from scoreboard/round state + transcript (“1vX”); abstain if HUD unknown.
3. **Surprise / fail** — audio burst + facecam motion; high FP risk → verify shortlist only.
4. **Reaction / banter** — transcript + laughter classes; critical for GTA RP.
5. **Entertaining interaction** — judge sub-scores + dialogue; not a detector class alone.

---

## Validation order

1. Label GTA sheet (this PR’s workflow).
2. Offline YAMNet / PaddleOCR at weight 0 vs labelled seconds/frames.
3. Promote **one** title profile at a time after NDCG/P@k gates.
4. Port only features that survive transfer tests on a second title.

No production activation from this document.
