# Agent 4. Gaming highlight detection

**Scope.** Research only. No production code, no dependency change, no edit to `clip-api/eval/`, `docs/PARITY.md`, or `docs/parity-opusclip.md`.  
**Date.** 2026-11-20. Sources below were read that day.  
**Claim labels.** `measured`, `verified`, `inferred`, `hypothesis`, `public-source`, `not measured`. Definitions are in [RESEARCH.md](../RESEARCH.md).  
**Throughput checkpoint.** n/a, read-only investigation.

## Overview

ClutchClips still nominates moments from loudness and, when the caller sets a chat region, from motion in the on-screen chat band. Gunshots, kill-feed lines, eliminations, explosions, laughter, screams, win and loss banners, and a true chat-message rate are not signals yet. Issues [#199](https://github.com/salaarkhan123/gta-clipping-pipeline/issues/199) and [#202](https://github.com/salaarkhan123/gta-clipping-pipeline/issues/202) already reserve those detectors. This note picks models that can feed those tickets, and it leaves every new signal at weight 0 until a labelled game video measures it.

The recommendation is YAMNet for the named sounds, PaddleOCR mobile on measured HUD crops for kill feeds and banners, and no speech-emotion network. PANNs and BEATs stay on the shelf until a YAMNet class is precise and still misses moments. MediaPipe blendshapes are an optional webcam scalar, also at weight 0, and only inside the facecam box the pipeline already finds.

## Key concepts

| Term | Meaning here |
|---|---|
| Signal | One number per source second, scaled like the others, then multiplied by a weight |
| Weight 0 | The detector is not run, and it does not enter the fused score. `release/step2-candidate` `clip-api/app/pipeline/timeline.py` states that rule, and `pipeline/__init__.py` there builds `heard_audio` only for timeline signals whose weight is above 0 (`verified` GitHub read 2026-11-20) |
| AudioSet mAP | Mean average precision of a clip tagger on the AudioSet eval set. It is not precision of a gunshot second inside a GTA VOD |
| Candidate | A window the picker nominates. Issue #199 requires those windows to stay byte-identical at weight 0 |
| Scene count | A count stored beside the window. Issue #199 also requires a per-class count in `scene`. The window can stay identical while `scene` gains a count (`inferred` from the two acceptance lines) |

## How the picker works

On this checkout, which follows `main`, `run_pipeline` probes the file, then builds per-second series, then picks windows (`verified` `clip-api/app/pipeline/__init__.py`).

| Step | What it does | Label |
|---|---|---|
| Loudness | `audio_rms_db` reads RMS dB per second through ffmpeg, then `baseline_z` and `normalise` | `verified` `clip-api/app/pipeline/signals.py` |
| Chat motion | Optional. 2 fps edge-difference inside a top band or a bottom band. `CHAT_LAG` shifts it 4 seconds earlier | `verified` `signals.py` |
| Fuse | `WEIGHTS` on this checkout is `chat_motion` 1.0 and `audio` 0.7. Template weights may override both keys only | `verified` `__init__.py`, `clip-api/app/templates.py` |
| Words | `exclamation_hits` adds a small re-rank bonus from a fixed phrase list. It is not a sound class | `verified` `clip-api/app/pipeline/transcribe.py` |
| Judge | On this checkout the model scores hook, flow, value, and trend. There is no emotion part in `ai.py` | `verified` `clip-api/app/ai.py` `PARTS` |

`release/step2-candidate` is ahead of this checkout. Its `WEIGHTS` are `chat_motion` 1.0, `audio` 0.7, `audio_flux` 0.35, `audio_bursts` 0.35, and `scene` 0.0 (`verified` that file on the branch). `audio_flux` is spectral change. `audio_bursts` is loudness pulsing 3 to 7 times a second, which the module calls the rhythm of laughter (`verified` `timeline.py`). `scene` is built and not computed at weight 0.

PR [#154](https://github.com/salaarkhan123/gta-clipping-pipeline/pull/154) is the write-up of that timeline. The numbers below are the author's report, on an Apple M4, not a run from this VM. Label them `public-source`.

| Detector tried in #154 | Author result on the tuning sheets | What this draft does with it |
|---|---|---|
| `audio_flux` | Kept at 0.35. Zias selection moved from 7 of 15 threes to 9 of 15 at that weight | Leave the weight alone |
| `audio_bursts` | Kept at 0.35. Caught 14 of 15 Zias moments against a chance of 12.3 | Leave it as the laughter-rhythm signal. A classifier has to beat it before it gets a weight |
| Both at 0.35 | Author reports 10 of 15 threes and 9 hits at 20 | The default on that branch |
| `scene` | Weight 0. It hurt the pair and costs a key-frame decode | Leave at 0 |
| Voice brightness, 1 to 3.5 kHz | Dropped. Caught 9 of 15 against a chance of 11.1, and selection got worse | Do not revive this shout feature |
| GTA "wasted" and "busted" by colour | Dropped. Top 8 hits on `gta-online-1`, checked by eye, 0 real | Do not revive a colour HUD detector. OCR is the #202 path |
| Wanted stars by bright pixels | Dropped. Top 8, 0 real | Do not revive |
| Speech rate | Dropped on that video | Out of scope here |

The author also wrote that seven weight sets on one video of 15 moments are small evidence, and that eval set v2 is the real test (`public-source` PR #154). This draft does not retune those weights.

## Where things live

| Thing | Path or ticket | Label |
|---|---|---|
| Eval moments | `clip-api/eval/`. Columns are `id, vod, game, start, end, rating, reason, held_out, source`. Ratings are 1, 2, 3, or empty. No per-class sound column | `verified` `clip-api/eval/README.md`, `labels-v2.csv` header |
| Held-out video | `gta-rp-1`. Tuning must not look at which of its clips hit | `verified` eval README |
| Wayin moments | `clip-api/eval/wayin-zias-iceman.csv`. 15 moments, selection run found 7 of 15 | `verified` eval README |
| Wayin moment types | Funny reactions, clutch wins, epic fails, emotional moments, high-energy scenes | `verified` `docs/PARITY.md` job-form table |
| OpusClip plan | `docs/parity-opusclip.md` on `release/step2-candidate`. Rows 1.3 sounds, 1.6 actions, 1.7 emotions, 1.8 on-screen text. Tickets R1-3 is #199, R1-4 is #202, R2-2 is #201 | `verified` file read 2026-11-20 |
| Timeline ticket | [#101](https://github.com/salaarkhan123/gta-clipping-pipeline/issues/101). Loudness, laughter and shouting, speech rate, scene change, GTA HUD events, chat. Acceptance criteria still unwritten. Blocked by U1 | `public-source` issue body |
| Named sounds | [#199](https://github.com/salaarkhan123/gta-clipping-pipeline/issues/199). Local model, no audio leaves the server, weight 0 until a class has precision 0.9 or better on labelled seconds of six game videos, plus `job_timings.py` | `public-source` issue body |
| HUD text | [#202](https://github.com/salaarkhan123/gta-clipping-pipeline/issues/202). Local OCR inside measured HUD regions only. Unknown game reads nothing and adds no decode. Exact-match 0.9 or better before ranking. Blocked by #201 | `public-source` issue body |
| Dependencies today | `clip-api/requirements.txt` has ffmpeg via the system, numpy, faster-whisper, OpenCV, fastembed. No torch, TensorFlow, Paddle, or onnxruntime | `verified` |

Nothing in `clip-api/eval/` is a labelled gunshot second, kill-feed frame, or emotion second (`verified` column list). #199 and #202 need new sheets. They do not need edits to `labels-v2.csv`.

## Gotchas

AudioSet clip mAP will not clear the 0.9 gate. The gate is precision on labelled seconds of our videos, per class (`public-source` #199). A class under 0.9 stays at weight 0 even if its AudioSet mAP looks strong.

A gunshot is not an elimination. Many shots can sit in a second that has no kill-feed line. Kill-feed text is #202. Gunfire is #199. They stay separate series.

Game music and fireworks collide with gunshots and explosions in the AudioSet ontology. YAMNet has `Video game music` at index 267 and `Fireworks` at index 426 (`verified` class map, read 2026-11-20). Those two scores are logs for the precision sheet. They are not ranking features.

This VM has no NVIDIA GPU. `nvidia-smi` is missing (`measured` 2026-11-20). Wall time of YAMNet, PANNs, BEATs, and both OCR stacks on a 2-hour VOD is `not measured`. RESEARCH.md keeps full 2-hour benches behind owner approval.

A weight of 0 that is implemented as "multiply by zero after you ran it" can still change features and timing. The release-branch rule is stronger. The detector is not computed (`verified` `timeline.py`). New classes should follow that rule so candidates stay byte-identical, which is the #199 test.

## Named sound models

All three tag AudioSet. Their published scores are clip-level mAP on that dataset unless the row says otherwise.

| | YAMNet | PANNs | BEATs |
|---|---|---|---|
| What it is | MobileNet v1, 521 classes, frame scores | Family of CNNs, 527 classes. Clip taggers and a few framewise heads | Transformer pretrained with an acoustic tokenizer, then fine-tuned for AudioSet clip tags |
| Frame time base | 0.96 second window, 50 percent overlap, so a hop of 0.48 second. At least 0.975 second of audio for the first frame. 16 kHz mono | Clip taggers score a whole file. The README's sound-event path is `Cnn14_DecisionLevelMax`, or else the clip tagger run on consecutive 2 second slices | README example classifies a whole tensor. No frame head is shown |
| Published score | Balanced mAP 0.306, d-prime 2.318, lwlrap 0.393, on 20,366 AudioSet eval segments and the 521 classes | CNN14 clip mAP 0.431. Wavegram-Logmel-CNN 0.439. `Cnn14_16k` clip mAP 0.438. `Cnn14_DecisionLevelMax` mAP 0.385. MobileNetV1 mAP 0.389 | `BEATs_iter3+` fine-tuned on AudioSet-2M, single model mAP 48.6 versus a previous 47.4, with 90M parameters versus 304M |
| Weights | `yamnet.h5`, 15,296,092 bytes, from `storage.googleapis.com/audioset/yamnet.h5` | Zenodo [3987831](https://doi.org/10.5281/zenodo.3987831). `Cnn14_mAP=0.431.pth` 327.4 MB. `Cnn14_DecisionLevelMax` 327.4 MB. `Cnn14_16k` 358.7 MB. `MobileNetV1` 23.6 MB | OneDrive links in the README. Size of the checkpoint file was not fetched |
| Code license | Apache-2.0. The YAMNet directory sits under `research/` in tensorflow/models, and that tree's LICENSE covers `research/` | MIT. GitHub license for `qiuqiangkong/audioset_tagging_cnn` and for `panns_inference` | MIT. `microsoft/unilm` root LICENSE. The BEATs README points at that file. Portions derive from fairseq and VQGAN |
| Weight license | The README tells you to download `yamnet.h5` as part of the Apache-2.0 example. No separate license file was next to the URL | CC BY 4.0 on Zenodo record 3987831. Credit Kong, Cao, Iqbal, Wang, Wang, and Plumbley | No separate weight license was stated in the README. Treat the MIT code license as the only statement found, and confirm the file before a bundle |
| Runtime | TensorFlow, plus Keras 2. The README says YAMNet is incompatible with Keras 3, the default from TensorFlow 2.16 | PyTorch. Inference scripts in the repo pass `--cuda` | PyTorch |
| In our image | No | No | No |
| Label | `public-source` [YAMNet README](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/README.md), class map, tensorflow/models LICENSE, HTTP content-length | `public-source` [PANNs README](https://github.com/qiuqiangkong/audioset_tagging_cnn), GitHub license API, [Zenodo 3987831](https://zenodo.org/records/3987831) | `public-source` [BEATs README](https://github.com/microsoft/unilm/blob/master/beats/README.md), [unilm LICENSE](https://github.com/microsoft/unilm/blob/master/LICENSE), [arXiv 2212.09058](https://arxiv.org/abs/2212.09058) |

YAMNet reports 3.7 million weights and 69.2 million multiplies per 960 millisecond frame (`public-source` README). That is an operation count, not a wall time. This VM did not run the model (`not measured`).

The class map used below is `yamnet_class_map.csv` on the tensorflow/models master branch, 521 data rows (`verified` download 2026-11-20). YAMNet drops six AudioSet classes on a fairness review. Gendered speech, gendered singing, Battle cry, and Funny music are the ones named (`public-source` README). Gunshot, explosion, siren, crash, scream, and laughter remain.

### Which model for #199

Use YAMNet as the first local classifier.

The #199 output is one value per second. YAMNet already emits a score every 0.48 second. Max-pool frames whose center falls in a source second, then store that max. That pooling rule is a `hypothesis` until the precision sheet exists.

PANNs publishes two scores that answer different questions. CNN14 clip tagging reaches mAP 0.431. The sound-event checkpoint `Cnn14_DecisionLevelMax` reaches mAP 0.385, and the file is 327.4 MB under CC BY 4.0, on PyTorch (`public-source` Zenodo and README). That is a large new runtime for a small published gap over YAMNet's 0.306. MobileNetV1 from the same record is 23.6 MB at mAP 0.389, still PyTorch, and the README shows it as a clip tagger. Hold PANNs for a second experiment if a YAMNet class is under 0.9 and the misses look like the network is too small for the sound.

BEATs has the highest single-model AudioSet-2M mAP in its paper, 0.486, at about 90 million parameters (`public-source` arXiv 2212.09058). The published fine-tune example is a clip tag. A per-second timeline would mean slicing the VOD and running the transformer many times, on a machine with no GPU (`hypothesis` on cost). Do not put BEATs in the first #199 PR.

Domain shift is untested. AudioSet gunshots are field recordings. A GTA mix is game sound effects, music, voice, and compressed upload audio. Whether YAMNet precision on our seconds clears 0.9 is `not measured`. Issue #199 already names the failure mode. Game music can read as events.

Packaging, if a later PR adopts YAMNet. Convert once to ONNX, ship the file in the image, and run it with onnxruntime on the 16 kHz mono WAV the pipeline can already extract. No download on the worker, which is the #199 network test. The conversion was not done here (`not measured`). Pinning TensorFlow and Keras 2 into the CPU image fights the Keras 3 note in the YAMNet README (`public-source`).

AudioSet itself is YouTube audio plus a label ontology. These licenses cover the code and the weight files the authors published. They are not a license to the YouTube source audio, and this note is not a legal opinion (`inferred`).

### YAMNet groups for the #199 classes

Scores in a group combine by max. Indices are the model outputs (`verified` class map).

| Series | Indices and display names | Left out on purpose |
|---|---|---|
| `sound_gunshot` | 421 Gunshot, gunfire. 422 Machine gun. 423 Fusillade. 424 Artillery fire | 425 Cap gun |
| `sound_explosion` | 420 Explosion | 426 Fireworks. 428 Burst, pop |
| `sound_siren` | 390 Siren. 317 Police car, siren. 318 Ambulance, siren. 319 Fire engine, fire truck, siren | 391 Civil defense siren, until a clip needs it |
| `sound_crash` | 463 Smash, crash | Vehicle classes. A car horn is not a crash |
| `sound_scream` | 11 Screaming. 6 Shout. 9 Yell | 7 Bellow. 8 Whoop. 10 Children shouting |
| `sound_laughter` | 13 Laughter. 15 Giggle. 17 Belly laugh. 18 Chuckle, chortle | 14 Baby laughter |
| `sound_fireworks` | 426 Fireworks | Diagnostic only. Weight stays 0. Never added into `sound_explosion` |
| `sound_game_music` | 267 Video game music | Diagnostic only. Weight stays 0. Report how often it fires in the same second as gunshot or explosion |

The grouping is a proposal (`hypothesis`). The precision sheet can split a group if one index causes the false positives.

`sound_laughter` does not replace `audio_bursts`. On the release branch that rhythm signal already has weight 0.35 (`verified`). A YAMNet laughter series starts at weight 0. It earns a weight only when its precision is at or above 0.9 and a selection run beats `audio_bursts` on the same sheets. One video of 15 moments was not enough for #154, so the comparison uses eval set v2 when the labels exist, and the held-out video is reported as totals only (`verified` eval README).

`sound_scream` is a new detector. The dropped 1 to 3.5 kHz feature in #154 is a different method that failed on one video (`public-source`). That failure is a reason to avoid another hand-built spectral shout feature. It is not a measurement of YAMNet.

## On-screen text

#202 reads text on sparse frames, inside HUD regions measured per game, and writes `text`, `region`, and `t`. An unknown game produces no events and no decode. #201 is the measurement ticket, and the HUD table stays empty until someone measures it (`public-source` #201 and #202, and parity row R2-2). This draft does not invent boxes.

| | PaddleOCR | EasyOCR |
|---|---|---|
| Code license | Apache-2.0. The GitHub repository states that release | Apache-2.0 for the JaidedAI repository |
| Detector weights | PP-OCRv4 mobile det, 4.7 MB in the PaddleX table. Server det is 109 MB | CRAFT. `easyocr/craft.py` carries a NAVER copyright and an MIT header. The upstream CRAFT repository is MIT |
| Recogniser | PP-OCRv4 mobile rec. PaddleX lists 10.6 MB. The Hugging Face card lists about 11 MB and license `apache-2.0` | CRNN, described by the project as ResNet or VGG, LSTM, and CTC. The project acknowledges the deep-text-recognition-benchmark training pipeline |
| Published accuracy | PaddleX table, self-built Chinese set of about 11,000 images. Mobile det Hmean 77.79. Mobile rec average accuracy 78.20. Server rec 79.20. The Hugging Face card for the same mobile rec name lists 83.28, and says a line is wrong if any character is wrong. Those two figures are not one eval | No matching official CPU accuracy table was fetched |
| Published CPU time | PaddleX. Intel Xeon Gold 5117 at 2.00 GHz, 8 threads, FP32. Mobile det 120.177 ms. Mobile rec 46.7868 ms. Server det 2434.01 ms | `not measured` |
| Extra runtime | PaddlePaddle. Absent from `requirements.txt` | PyTorch. Absent from `requirements.txt` |
| Fit for a GTA HUD | The mobile rec card says the model supports Chinese and English and mainly focuses on Chinese (`public-source` [HF card](https://huggingface.co/PaddlePaddle/PP-OCRv4_mobile_rec)). English kill-feed exact-match is `not measured` | Same gap. Stylised game fonts are the #202 risk, and neither toolkit publishes a GTA number |
| Label | `public-source` [PaddleOCR repo](https://github.com/PaddlePaddle/PaddleOCR), [PaddleX OCR table](https://paddlepaddle.github.io/PaddleX/main/en/pipeline_usage/tutorials/ocr_pipelines/OCR.html), HF card | `public-source` [EasyOCR](https://github.com/JaidedAI/EasyOCR), [CRAFT](https://github.com/clovaai/CRAFT-pytorch) |

Use the PaddleOCR mobile English or Latin recogniser the toolkit documents for English, on crops from #201, for the first #202 experiment. Quote the Chinese-set Hmean only as a document-scene number. Do not quote it as kill-feed exact-match.

The CPU arithmetic that follows is a `hypothesis`, not a bench. Add the two PaddleX mobile times, 120.177 ms and 46.7868 ms, to get about 167 ms per crop on that Xeon. One crop every second for 7,200 seconds is about 1,200 seconds of OCR. The assumptions are a matching CPU, one crop, no batch, and both detection and recognition on every crop. Our VM was not that Xeon, and no crop was run (`not measured`). A 1,200 second OCR stage does not fit a 10 minute job next to transcription and render (`inferred` from the SPEC 932.7 second baseline in RESEARCH.md, where render is 578 seconds and transcribe is 257 seconds). So the first OCR PR samples slower than 1 Hz, only inside a measured region, and skips the decode when #201 has no table for that game. That last rule is already an acceptance test on #202.

Closed lexicon for banners, proposed and `not measured`. `wasted`, `busted`, `winner`, `victory`, `defeat`, `eliminated`, `mission passed`, `mission failed`. A hit is an exact token after a case fold, inside the banner region only. Player names in a kill feed are an open vocabulary. For that region, store the line and a change count. Ranking still waits on exact-match of 0.9 or better against labelled frames, which is the #202 gate. A change count that has not met the gate can sit in `scene` and must stay at weight 0.

#154 already showed that a colour test for "wasted" and "busted" fired on garages, a red car, and a bank menu (`public-source`). OCR replaces that test. It does not sit beside it.

## Emotion, laughter, and reactions

| Model or signal | License and limit | Use |
|---|---|---|
| audEERING `wav2vec2-large-robust-12-ft-emotion-msp-dim` | CC BY-NC-SA 4.0. The model card says research only, and that a commercial license is bought from audEERING. Fine-tuned on MSP-Podcast. About 1.32 GB on the Hub tree. Outputs arousal, dominance, and valence | Do not bundle. A paid license is a money decision for the owner |
| SpeechBrain `emotion-recognition-wav2vec2-IEMOCAP` | Model card says `apache-2.0`. Training data is IEMOCAP. The USC SAIL release form says the data is for internal research only, that derivatives are not passed on without permission, and that the data and derivatives are not used for commercial purposes | Do not bundle. The Apache tag on the card does not erase the dataset form. This is a reading of those two public texts, not a counsel opinion (`inferred`) |
| YAMNet scream and laughter classes | Apache-2.0 example, as above | The voice-reaction series, at weight 0 |
| `audio_bursts` on the release branch | Our code | Already weighted at 0.35. Leave it |
| OpenCV Haar facecam | Already in the image. Finds a face that stays put | The box a later face scalar may crop. No new face detector for that job (`verified` `facecam.py`) |
| MediaPipe Face Landmarker blendshapes | Task source in google-ai-edge/mediapipe is Apache-2.0. The task returns 478 landmarks and 52 blendshape scores when blendshapes are enabled (`public-source` [Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) and the Python task file) | Optional, weight 0. Not in `requirements.txt` (`verified`) |
| Judge text | This checkout scores hook, flow, value, and trend. Parity row 1.7 points at a later emotion sub-score from the words on #153 | Leave the judge. Do not add a second text-emotion model in this track |

Parity row 1.7, on `release/step2-candidate`, says a webcam expression signal may be reused for ranking, and that face analysis of a person has to be described in the privacy text, with no identity and no stored face data (`verified` that file). A `face_reaction` series, if built, stores three scalars per second inside the existing facecam box. `jawOpen`, the mean of `mouthSmileLeft` and `mouthSmileRight`, and `browInnerUp`. Landmarks and any embedding are discarded in the same step. No box, no series, no extra decode. Weight 0 until a labelled reaction sheet exists. Showing a tag such as "laughing" to the user waits on the 0.9 scene-field rule in the parity Release 1 quality check (`verified` that plan).

High-intensity play is the loudness z-score already in `audio`, plus `audio_flux` where the release branch has it. A new intensity head would add the same seconds again. No new series.

## Chat spikes

`onscreen_chat_motion` is pixel change, not a message rate (`verified` `signals.py`). A camera move inside the band can raise it (`inferred` from the edgedetect and frame-difference filter). Its weight stays where the template put it. Default on this checkout is 1.0 (`verified`).

`chat_rate` is messages per second from a chat log the user supplies, or from an official chat API when SPEC section 4.5 is built. Weight 0. Shift it with the existing `CHAT_LAG` of 4 seconds only after a sheet shows the lag still fits, which is `not measured` for message logs. No cookies, no unofficial scrape, and no client impersonation. That is the ingest rule in `CLAUDE.md` (`verified`).

## Wins, losses, and eliminations

| Product idea | Series | Weight |
|---|---|---|
| Elimination | `hud_killfeed` change count inside the measured kill-feed region | 0 |
| Win or loss | `hud_banner` lexicon hit. Positive tokens and negative tokens stay distinct so a fail is not stored as a win | 0 |
| Clutch or fail as a clip type | The banner event plus the words the judge already sees. The banner does not by itself become a rank term | 0 |
| High-energy scene | Existing `audio`, and `audio_flux` on the release branch | unchanged |
| Funny reaction | `audio_bursts` where it already has weight, plus `sound_laughter` and `face_reaction` at 0 | mixed, see each row |
| Emotional moment | The judge, when #153 lands. No NC speech model | unchanged |

## Proposed signals

Every new row has weight 0. Existing weights are listed so a later PR does not "normalise" them.

| Series | Weight | Computed when | Ticket |
|---|---|---|---|
| `audio` | 0.7 | Audio track present | today |
| `chat_motion` | 1.0 unless the template overrides | Chat region set | today |
| `audio_flux` | 0.35 on `release/step2-candidate` only | Weight above 0 | #154, already measured by the author |
| `audio_bursts` | 0.35 on `release/step2-candidate` only | Weight above 0 | #154 |
| `scene` | 0 | Not computed | #154 |
| `sound_gunshot` | 0 | Not computed until a #199 PR turns the log on. Still weight 0 for ranking | #199 |
| `sound_explosion` | 0 | Same | #199 |
| `sound_siren` | 0 | Same | #199 |
| `sound_crash` | 0 | Same | #199 |
| `sound_scream` | 0 | Same | #199 |
| `sound_laughter` | 0 | Same. Must beat `audio_bursts` before any nonzero weight | #199 |
| `sound_fireworks` | 0 | Diagnostic log only | #199 |
| `sound_game_music` | 0 | Diagnostic log only | #199 |
| `hud_banner` | 0 | Game has a #201 banner box. Otherwise no decode | #202 |
| `hud_killfeed` | 0 | Game has a #201 kill-feed box. Otherwise no decode | #202 |
| `chat_rate` | 0 | A user-supplied or official log exists. Otherwise absent | SPEC 4.5, not a scraper |
| `face_reaction` | 0 | A facecam box exists, and the owner has accepted the privacy text | parity 1.7 |

No series named intensity, elimination, or emotion. Those words are products of the rows above. Adding a fused key before the parts are measured would hide which part was wrong.

## Tradeoffs

| Choice | What you gain | What you pay | Judgment |
|---|---|---|---|
| YAMNet, weight 0, ONNX later | Per-second scores, 15,296,092 byte file, Apache-2.0 example, classes that match #199 | Keras 2 if you skip the conversion. AudioSet mAP 0.306 is not our precision. Domain shift untested | First #199 model |
| PANNs `Cnn14_DecisionLevelMax` | A published framewise head, mAP 0.385 | 327.4 MB, CC BY 4.0, PyTorch, and the mAP is still an AudioSet clip score | Second, only if YAMNet's errors justify the size |
| BEATs iter3+ | Highest cited AudioSet-2M single-model mAP, 0.486, at 90M parameters | Clip head, PyTorch, no GPU here, weight license not separately stated | Hold |
| PaddleOCR mobile on #201 crops | Apache-2.0, a published CPU table, matches the #202 shape | Chinese-leaning rec card, PaddlePaddle wheel, HUD exact-match unknown, 1 Hz may cost about 1,200 seconds on the published Xeon | First #202 model, sampled sparsely |
| EasyOCR | Apache-2.0 code, MIT CRAFT detector, PyTorch if the image already had torch | It does not. No CPU table fetched. Same HUD gap | Fallback if PaddlePaddle packaging fails |
| audEERING or IEMOCAP emotion nets | Dimensional or categorical speech emotion | Non-commercial dataset terms | Reject for the product image |
| Another colour HUD test | None. #154 already got 0 real hits in the top 8 | False "wasted" screens | Reject |
| Another spectral shout feature | None on the Zias sheet | #154 dropped it | Reject |

## What a later PR measures

The PR is still #199 or #202. It does not open a new understanding track.

1. Weight 0 leaves nominated windows byte-identical to the branch it starts from. A test locks that, the same way #154 locks "a signal with weight 0 costs nothing".
2. Each class reports precision and recall on labelled seconds, or exact-match on labelled frames. A weight above 0 is proposed only at 0.9 or better. Below that, the series may be stored and is not ranked.
3. `scripts/job_timings.py` on the 2-hour benchmark reports the added time. Owner approval still gates that bench (`verified` RESEARCH.md).
4. Eval set v2 precision at 20, precision at 40, and recall of 3s are reported before and after, with the held-out video as totals only. The PR does not edit `labels-v2.csv` to chase a score.
5. New labels live in a new sheet. Sound seconds for #199. HUD frames for #202. They are not columns stuffed into the moment sheet.
6. No network call during inference. A test covers that for #199.
7. A game with no HUD table adds no frame decode. A test covers that for #202.
8. Tags shown to a user are fields that were measured. Parity row 1.10 already says a tag the pipeline did not measure is not shown.

## Recommendation

Ship the research conclusion as follows. The first sound model is YAMNet, local, weight 0, with the class groups in the table above, and with fireworks and video-game music kept as confounder logs. The first text model is PaddleOCR mobile, English or Latin, on #201 crops only, weight 0, banners on a closed lexicon and kill feeds as line events. Laughter from YAMNet does not get a weight while `audio_bursts` is the measured laughter signal. Speech-emotion checkpoints trained under CC BY-NC-SA or the IEMOCAP commercial ban stay out of the image. Face reaction, if built, is three blendshape scalars inside the current facecam box, landmarks discarded, weight 0, and only after the privacy text is accepted.
