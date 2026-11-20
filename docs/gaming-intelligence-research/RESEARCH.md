# ClutchClips gaming intelligence research

**Decision requested, November 20, 2026.** Approve Phase 1: collect permissioned labels, freeze a release baseline and test the named-sound and HUD readers that Cursor has already scaffolded. Keep ranking weights at zero. Defer a GPU rental or purchase until a measured quality gain and bottleneck justify one.

The best near-term hypothesis is that **identifying what changed in the game and preserving what made it interesting are two different tasks**. A score increment can identify a Rocket League goal and suppress its replay. Whether the goal won in overtime, or provoked a reaction worth keeping, determines its rank and boundaries. In GTA RP, a quiet reversal in dialogue can carry the entire clip. Use shared transcript, sound and timing features plus measured per-game state profiles. A large video model is a later candidate for uncertain moments.

## What the evidence supports

| Evidence | Finding | Consequence |
|---|---|---|
| Verified repository | #218 merged into main at `8e0d9bad`. It already has multimodal nomination/judging, transcript reuse, standby rejection, deduplication and five editorial sub-scores. It lacks populated HUD regions. Cursor's #231 and #232 add weight-zero audio/OCR interfaces outside this baseline; #234 integrates the performance waves for staging. | Start from those interfaces and preserve existing outputs. Do not build a second performance pipeline. [Audit](CURRENT-ARCHITECTURE.md) |
| Replayed historical scorer | 7 of 15 Wayin selections recovered by one saved ClutchClips run on one reaction recording. At K=20 there are 6 hits and 14 unrated. A separate historical U2 comparison recovered 10 of the same 15 after tuning. The checked-in gaming sheets and 55 private multigame candidate rows lack editorial ratings. | Track overlap as a historical reference. It cannot settle gaming quality or competitive parity. [Audit and prior U2 evidence](CURRENT-ARCHITECTURE.md) |
| New local experiment | On three 120 s excerpts, audio+motion changed at least one top-three start against audio alone every time. Reading one reduced visual frame/s took 8.900–15.567 s per excerpt. The pinned RC selection-only mode returned 2–3 candidates. | Selection changed; benefit remains unmeasured. Test sparse shared decode, event precision and human preference together. [Methods, timings and runnable probes](EVALUATION-FRAMEWORK.md) |
| New historical metadata analysis | 116 matched higher/lower-reach pairs across nine game families from the licensed YouNiverse archive. Action/highlight terms appeared in 40 higher-reach titles versus 49 controls. The archive predates Shorts; one creator supplies 44 pairs. | No basis for a title-marker boost. Collect creator-authorized footage and fixed-age analytics to test effects of hooks, editing and payoff. [Cohort reconstruction](VIRALITY-RESEARCH.md) |
| Published model evidence | 21 candidate tools/models. Specific artifacts include Apache-licensed YAMNet and PaddleOCR mobile, PANNs MIT code with CC BY 4.0 weights, and noncommercial VideoMAE/TimeSformer checkpoints. General-purpose benchmarks establish reference performance on other tasks. | Prefer cheap, testable signals and verify exact artifact rights. Measure accuracy and operating cost per supported title before packaging. [Repository evaluation](REPOSITORY-EVALUATION.md) |
| Competitor and hardware evidence | Wayin, OpusClip and Eklipse document gaming workflows; Outplayed provides a live game-event comparator on supported titles. No paired independent gaming quality or turnaround result exists here. Device capacities and hourly rental prices are documented; ClutchClips GPU throughput remains unknown. | Require a blinded, same-source comparison before a superiority claim. Require a bounded, separately authorized hardware test before any purchase. [Competitors](COMPETITIVE-ANALYSIS.md) · [Hardware and economics](GPU-REQUIREMENTS.md) |

## Recommendation matrix

Rank is **experiment priority**, conditional on rights and adequate labels. Quality and competitive advantage are hypotheses. Processing cost is incremental to the current selector, including decode. Scalability describes what drives cost as titles and hours grow. The label/replay work is a prerequisite for every ranking experiment and has no direct product ranking effect.

| Rank | Capability and expected quality effect | Processing cost | Development complexity | Scalability | Commercial licensing or rights | Competitive advantage to test |
|---:|---|---|---|---|---|---|
| 1 | Versioned labels, blind review, replay and attribution. Indirect, essential to distinguish improvement from merely different clips. | Low machine cost, high human review cost | Medium | Reusable per title and release; creator recruitment limits coverage | Original schema; explicit footage/analytics grants | High: defendable evidence by title and an honest confidence measure |
| 2 | Sparse HUD/score-state transitions and replay suppression. High for structured outcomes. | Low–medium if crops reuse frames; separate decoding can dominate | Medium, per-profile maintenance | Good on validated layouts; abstain after patch drift | Tesseract and selected Paddle artifacts permissive; separately clear training/template media | High: fewer false goals, spectator kills and duplicates |
| 3 | Named sounds on reused PCM. Medium for action without commentary; bursty game audio can be routine. | Low–medium CPU, measure continuous versus gated | Low–medium via #231 | One extractor across games; thresholds vary by mix | Google YAMNet Apache-2.0; PANNs backup needs attribution | Medium: discover off-camera/quietly narrated events |
| 4 | Transcript setup/payoff and cuts for GTA RP / IRL. High in narrative streams. | Low with cached transcript; additional ASR/AI time variable | Medium | Shared across titles; language/ASR coverage limits transfer | Existing access conditions and creator permission for text processing | High: publishable quiet stories and complete punchlines |
| 5 | Fusion, temporal deduplication and probability calibration. High if independent families add signal. | Low for tabular ranking; cost of constituent signals separate | Medium | Shared ranker with small measured title corrections | Owned fitting code/data subject to corpus rights | High: plausible events ranked by stakes and viewer context |
| 6 | Gap-aware chat response, facecam reaction and scene cues. Medium when present. | Low for aggregate chat; medium for sampled facecam | Medium | Optional across games; outages and overlays reduce coverage | Permission for chat/face evidence; verify model bundle licenses | Medium: retain aftermath, reject alerts and screen changes |
| 7 | Game/mode recognition with unknown fallback. Medium indirect benefit on mixed/incorrectly tagged VODs. | Low for anchors; higher for sparse embeddings | Medium | Extend profiles per title; unknown titles use universal path | Permissive selected DINOv2 artifact or existing embeddings; no external media grant implied | Medium: fewer confidently wrong profiles |
| 8 | Specialized detection/tracking where OCR fails. Potentially high for one icon or event; low outside that profile. | Medium–high for dense bursts and training | High | Label and patch costs grow per game | RF-DETR Nano Apache; distinguish commercial terms of larger sizes and YOLO alternatives | Selective advantage when a recurring measured error justifies it |
| 9 | Candidate-only visual-language verification and temporal models. Unknown marginal gain. | High GPU or API plus latency | High | Strictly cap clips, frames and tokens per VOD | Exact Qwen2.5-VL 7B artifact permissive; several alternatives gated/NC | Unproven: resolve ambiguous events if gains survive blinded comparison |
| 10 | Learned engagement score from published outcomes. Unknown for raw-VOD ranking. | Low inference; costly longitudinal data | High statistical/data complexity | Platform drift, cold creators and missing exposure | Creator analytics permissions and platform terms by use | Unproven: prioritize only after across-creator replication |

## Approval and evidence map

Approve **1A–1D** in the [implementation roadmap](IMPLEMENTATION-ROADMAP.md) as research on owned or permissioned data. Phase 2 pairs a falsifiable score transition (Rocket League) with a quiet narrative case (GTA RP), followed by a shooter with difficult attribution (Valorant). No class gains weight for simply passing an OCR or audio benchmark. A future enablement request must show a paired quality gain, high-precision detections on unseen creators, acceptable boundary errors and a measured latency/cost envelope.

| Owner decision or technical question | Document |
|---|---|
| What exists in main, on other branches, and in the evaluation sets? | [Current architecture](CURRENT-ARCHITECTURE.md) |
| Which tools, checkpoints and licenses merit a test? | [Repository evaluation](REPOSITORY-EVALUATION.md) |
| What counts as a distinct event or worthwhile moment in each game? | [Game event taxonomy](GAME-EVENT-TAXONOMY.md) |
| How do we recognize those events when the HUD, POV or title changes? | [Game-specific detectors](GAME-SPECIFIC-DETECTORS.md) |
| How should the pipeline represent evidence, combine it and handle uncertainty? | [Multimodal architecture](MULTIMODAL-ARCHITECTURE.md) |
| Which signals predict engagement given the evidence so far? | [Virality study](VIRALITY-RESEARCH.md) |
| How do we collect permissioned positives, unsuccessful clips and ordinary gameplay? | [Dataset plan](DATASET-PLAN.md) |
| How can another researcher reproduce the runs and test future candidates? | [Evaluation framework](EVALUATION-FRAMEWORK.md) |
| When could renting or buying compute be justified? | [Hardware and cost](GPU-REQUIREMENTS.md) |
| What do competitors document and how would we test them fairly? | [Competitive analysis](COMPETITIVE-ANALYSIS.md) |
| What would each PR prove, and when would we stop? | [Phased implementation roadmap](IMPLEMENTATION-ROADMAP.md) |

The independent workstreams examined vision, audio, HUD/OCR, temporal models, datasets, engagement, competitors, infrastructure and licensing. The coordinator checked repository claims against pinned code, replayed the existing scorer, ran the local selection probe and reconciled source-specific licenses and historical measurements. The empirical limits are material: three short ungraded gameplay excerpts, observational reach proxies, no blind vendor comparison and no measured GPU workload.
