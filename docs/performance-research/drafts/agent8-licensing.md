# Agent 8. Licensing and verification

**Scope:** Research only. No production code, image, or dependency changes.  
**LICENSE reads:** 2026-11-20, raw-file batch from 02:24:27Z through 02:28:57Z UTC.  
**Claim labels:** `measured` | `verified` | `inferred` | `hypothesis` | `public-source` | `not measured`.

This note records license texts and what this checkout actually ships. It is not a legal opinion. A rank below is an adoption order for engineering, not a measured probability (`inferred`).

## What the product ships today

| Fact | Record | Label |
|---|---|---|
| Image base | `python:3.12-slim`, then `apt-get install ffmpeg` | `verified` `clip-api/Dockerfile` |
| Python deps | `yt-dlp==2026.10.26`, `faster-whisper>=1.0`, `opencv-python-headless>=4.9,<5` | `verified` `clip-api/requirements.txt` |
| Encode | `ffmpeg` subprocess, `-c:v libx264`, AAC audio | `verified` `clip-api/app/pipeline/render.py` |
| ASR | `WhisperModel(..., device="cpu", compute_type="int8")`, `vad_filter: True` | `verified` `clip-api/Dockerfile`, `clip-api/app/pipeline/transcribe.py` |
| CUDA packages | none in the Dockerfile | `verified` |
| ffmpeg on this VM | `6.1.1-3ubuntu5`. Configure has `--enable-gpl`, `--enable-libx264`, `--enable-libx265`, `--enable-libass`. It has no `--enable-nonfree` and no `--enable-libfdk-aac`. | `measured` `ffmpeg -version` |
| Linked libs on this VM | `libx264.so.164`, `libx265.so.199`, `libass.so.9`, `libavcodec.so.60` | `measured` `ldd /usr/bin/ffmpeg` |
| Debian slim image configure line | not built in this run | `not measured` |

The production Dockerfile installs Debian's `ffmpeg` package. The binary measured above is Ubuntu's package on this VM. Both facts stand. They are not the same build (`verified` Dockerfile, `measured` this VM).

Ubuntu's copyright file, which quotes the Debian packaging comment, says the default binaries are GPL-2.0-or-later because GPL parts are enabled, and that an extra `libavcodec` build linked to Apache-2.0 libraries is effectively GPL-3.0-or-later (`verified` `/usr/share/doc/ffmpeg/copyright`). This run did not prove which of those two Debian flavors the CLI links, beyond `--enable-gpl` plus `libx264` on the Ubuntu binary (`measured`).

## License matrix

Each row is one artifact. A wrapper license does not relicense the library it calls.

| Component | Artifact read | License on that artifact | Commercial SaaS, from the text | Label |
|---|---|---|---|---|
| FFmpeg core | `FFmpeg/FFmpeg` `LICENSE.md` | LGPL-2.1-or-later unless `--enable-gpl` | GPL build required once a GPL library is combined. `libx264` and `libx265` are listed under GPL version 2. `--enable-nonfree` makes the binary unredistributable. | `public-source` |
| FFmpeg binary we measured | `ffmpeg -version` and `ldd` | GPL build. `--enable-gpl` and `libx264` are on. `--enable-nonfree` is off, so this build is the redistributable GPL kind, not the nonfree kind. | Shipping the binary, including in a published image, is distribution of a GPL program. | `measured` plus `public-source` `LICENSE.md` |
| libass | upstream `COPYING` | ISC | Permissive for libass itself. The ffmpeg binary that links it is still the GPL build above. | `public-source` `COPYING`. Link `measured` |
| x264 | upstream `COPYING` is the GPL version 2 text. FFmpeg lists `libx264` under "GPL version 2". | GPL-2.0 | Combined ffmpeg must be built `--enable-gpl`. | `public-source` |
| faster-whisper | `SYSTRAN/faster-whisper` `LICENSE`. PyPI 1.2.1 classifier MIT. | MIT. Copyright 2023 SYSTRAN. | Commercial use with the notice kept. | `public-source` |
| CTranslate2 | `OpenNMT/CTranslate2` `LICENSE`. PyPI 4.9.0 license field MIT. | MIT. Copyright 2018 SYSTRAN and 2019 OpenNMT. | Same notice duty. A CUDA build also pulls the CUDA EULA. Current image is CPU. | `public-source`. CPU path `verified` |
| Whisper weights | `openai/whisper` README line "code and model weights are released under the MIT License." `Systran/faster-whisper-small.en` card `license: mit`. | MIT for that code and those weights. | The `small.en` weights baked by the Dockerfile match that card. | `public-source`. Bake `verified` |
| yt-dlp code | repo `LICENSE` (Unlicense text). README licensing section. | Unlicense for the git tree, the PyPI sdist, and the PyPI wheel. | Commercial use of that code. The Unlicense is not a license to the video. | `public-source`. Pin `verified` `yt-dlp==2026.10.26` |
| yt-dlp release binaries | same README section | PyInstaller executables include GPLv3-or-later code, so the combined executable is GPLv3-or-later. The zipimport binary also carries ISC `meriyah` and MIT `astring`. | Do not ship those executables. The wheel we pin is the Unlicense artifact. | `public-source` |
| OpenCV library | `opencv/opencv` `LICENSE` | Apache-2.0 | Commercial use with the Apache notices. | `public-source` |
| opencv-python packaging | `opencv/opencv-python` `LICENSE.txt` and `4.x` README | Scripts are MIT. README says every wheel ships FFmpeg under LGPLv2.1. PyPI `opencv-python-headless` 5.1.0.95 license field says Apache 2.0. Our pin is `>=4.9,<5`, so 5.x is outside the image. | The 4.x wheel is a second ffmpeg distribution, LGPL, inside the image. This run did not unpack a wheel. | `public-source` README. Pin `verified`. Wheel contents `not measured` |
| TorchCodec | `pytorch/torchcodec` `LICENSE` and README. PyPI 0.17.0. GitHub SPDX BSD-3-Clause on `pytorch/torchcodec` and `meta-pytorch/torchcodec`. | BSD-3-Clause. Copyright 2024 Meta. | README says a CUDA build or the CUDA wheel also needs the NVIDIA CUDA EULA. TorchCodec loads the FFmpeg shared libraries already on the machine. It does not ship FFmpeg. | `public-source` |
| PyNvVideoCodec | PyPI `PyNvVideoCodec` 2.2.4 license field MIT, OSI MIT classifier. NVIDIA developer page says the library is MIT and uses Video Codec SDK APIs. | MIT for the Python package metadata. | The Video Codec SDK agreement is a separate contract. This run did not unzip the wheel, so bundled SDK object code is `not measured`. | `public-source`. Wheel contents `not measured` |
| WhisperX code | `m-bain/whisperX` `LICENSE`. PyPI 3.8.6 license field BSD-2-Clause. | BSD-2-Clause. Copyright 2024 Max Bain. | Commercial use with the notice. | `public-source` |
| WhisperX English aligner | HF `facebook/wav2vec2-base-960h` card | `license: apache-2.0` | Commercial use under Apache-2.0. | `public-source` |
| WhisperX FR, DE, ES, IT aligners | HF cards `facebook/wav2vec2-base-10k-voxpopuli-ft-fr`, `-de`, `-es`, `-it` | `license: cc-by-nc-4.0` on all four | Non-commercial. A paid clipping product cannot ship these weights on this text. | `public-source` |
| pyannote.audio | `pyannote/pyannote-audio` `LICENSE` | MIT. Copyright 2020 CNRS. | Code only. Model cards are separate. | `public-source` |
| pyannote `speaker-diarization-3.1` | HTML model page contained the sentence that the pipeline uses the MIT license. Raw README later returned HTTP 401. | MIT on that HTML sentence. | Gated download still needs a Hugging Face token and accepted user conditions. The clickwrap body was not saved. | `public-source` HTML. Clickwrap `not measured` |
| pyannote `speaker-diarization-community-1` | raw README | HTTP 401. No license field read. | Do not treat a draft that names CC BY 4.0 as confirmed. | `not measured` |
| Decord | `dmlc/decord` `LICENSE`. GitHub SPDX Apache-2.0. | Apache-2.0 | Commercial use of the code. Last push 2024-07-17. Latest release v0.6.0 on 2021-06-14. Not archived. | `public-source` |
| PySceneDetect | `Breakthrough/PySceneDetect` `LICENSE`. GitHub SPDX BSD-3-Clause. PyPI `scenedetect` 0.7.3. | BSD-3-Clause. Copyright 2014 Brandon Castellano. | Commercial use with the notice. No endorsement under the name. | `public-source` |
| Silero VAD code and stated weights | `snakers4/silero-vad` `LICENSE`. PyPI `silero-vad` 6.2.3 MIT classifier. | MIT. Copyright 2020-present Silero Team. | Maintainer reply on discussion 817, 2026-10-25, is the single word "MIT" for the v6.2.3 ONNX weights. | `public-source` |
| Silero README badge | raw README first line | Alt text says "License: CC BY-NC 4.0". The badge image URL says `License-MIT`. The link target is the MIT `LICENSE`. | The grant to rely on is the `LICENSE` file plus the maintainer reply. The alt text is a contradicting string on the same page. | `public-source` |
| MediaPipe | `google-ai-edge/mediapipe` `LICENSE`. PyPI 1.2.3 license field Apache 2.0. | Apache-2.0 | Code. Task-model files were not opened. | `public-source`. Models `not measured` |
| Remotion | `remotion-dev/remotion` `LICENSE.md`. GitHub SPDX `NOASSERTION`. FAQ at remotion.dev/docs/license/faq. | Remotion License. Source-available. The FAQ says it is not an OSI open-source license. | Free License if the entity is an individual, a for-profit organization with up to 3 employees, or a qualifying non-profit, including a commercial SaaS and an automation. Otherwise Company License. Automators price on the FAQ is $0.01 per render, $100 per month minimum. Creators price is $25 per month per seat. | `public-source` |
| Streamlink | `streamlink/streamlink` `LICENSE`. GitHub SPDX BSD-2-Clause. PyPI 8.6.3. | BSD-2-Clause. Copyright through 2026 Streamlink Team. | Commercial use with the notice. No grant of rights in streamed content. | `public-source` |
| NVIDIA playbook | `NVIDIA-AI-Technology-Center/accelerated-video-for-ai-playbook` file `LICENCE` (that spelling). GitHub SPDX MIT. | MIT. Copyright 2025 NVIDIA CORPORATION & AFFILIATES. | Code in that repo, with the notice. It does not license the Video Codec SDK or an NGC container. NGC container terms were not read. | `public-source`. NGC `not measured` |
| NVIDIA `video-sdk-samples` | GitHub API license `None`. README has no license line. Root listing has no LICENSE file. Last push 2022-08-13. | No repo-level grant detected. One sample header, `nvEncDXGIOutputDuplicationSample/main.cpp`, is a 3-clause BSD-style notice. | That header covers that file. It does not license the SDK libraries. Do not paste the tree into the product. | `public-source` |
| Video Codec SDK agreement | developer.nvidia.com license agreement page | NVIDIA proprietary agreement. Extract on this read includes object-code-only distribution inside the licensee's product, NVIDIA GPU only, a grant-back of modifications, a one-year term that renews, and a ban on using the materials to capture third-party content. | Separate from the MIT line on PyNvVideoCodec. | `public-source` |
| CUDA Toolkit EULA | docs.nvidia.com/cuda/eula. Page says last updated 26 January 2026. | NVIDIA SDK EULA. Section 1.2 item 5 forbids use that would make the SDK subject to an open-source license requiring source disclosure, derivative-work licensing, or no-charge redistribution. | A GPL ffmpeg library and a CUDA redistributable do not belong in one binary. | `public-source` |
| ClipGen, long-form clipper | `azmifauzan/clipgen`. GitHub license `None`. `LICENSE` URL returned 404. | No grant in the repo. | Default copyright. Do not copy source. | `public-source` |
| ClipGen, PyPI `clipgen` 0.2.0 | PyPI license field MIT. `JerryX2026/clipgen` GitHub license `None`. | MIT on the PyPI metadata. No LICENSE file detected on the GitHub repo. | Short-video templates with TTS, not a VOD clipper. Do not vendor until the repo contains the MIT text. | `public-source` |
| CLIPGen, chiplet tool | `realise-lab/CLIPGen` `LICENSE` | BSD-3-Clause. Copyright 2026 Zhengping Zhu. GitHub description is a 2.5D chiplet-link framework. | Wrong product. | `public-source` |
| clip-gen, text-to-image | `HFAiLab/clip-gen` `LICENSE` | MIT. Copyright 2022 HFAiLab. | Wrong product. | `public-source` |

`ClipsAI/clipsai` is a different name. Its LICENSE is MIT (`public-source`). It is not one of the ClipGen repos above.

## Commercial SaaS risk

Four different duties show up in these texts. Mixing them is how a draft marks a row "OK" and still ships a problem.

**Copyright of the code.** MIT, BSD, Apache-2.0, ISC, and the Unlicense allow a commercial service if the notice duty is met. GPL on the ffmpeg binary we measured requires GPL compliance for that binary when the binary is distributed. Remotion's license is a company contract with a headcount test. CC-BY-NC 4.0 on the four WhisperX aligners rejects commercial use.

**Distribution versus running a server.** The current worker execs `ffmpeg` as a separate process (`verified` `render.py`). `ffmpeg.org/legal.html`, as fetched, says a GPL-enabled FFmpeg is under the GPL, points at the GPL FAQ, and says FFmpeg is not offered under a proprietary license. The page's LGPL checklist says the program must not use GPL libraries, and it names libx264. Our measured binary does use libx264. The page does not contain a sentence that exec of the `ffmpeg` binary leaves the caller under a different license. Treat "the Python service stays under our own license" as an inference from the separate process, and have counsel confirm it before a public image or a customer-hosted image (`inferred`). Publishing `clip-api/Dockerfile`'s image distributes both Debian's ffmpeg and, per the opencv-python 4.x README, an LGPL FFmpeg inside the wheel (`public-source` plus `verified` Dockerfile).

**Patents, separate from copyright.** `ffmpeg.org/legal.html` still tells commercial users that patent holders collect for MPEG-related codecs and names MPEG LA (`public-source`). Via LA's AVC/H.264 program page is live, and its active patent attachment is dated 1 November 2026 (`public-source`). This pass did not place ClutchClips in a Via product category and did not compute a fee (`not measured`). The native AAC encoder is in the measured build. `libfdk-aac` is not. fdk-aac is the codec FFmpeg's `LICENSE.md` puts behind `--enable-nonfree`.

**Rights in the footage.** The Unlicense and the BSD-2-Clause cover yt-dlp and Streamlink as programs. They say nothing about Twitch, Kick, or YouTube videos. Platform terms stay a product rule (`inferred` from the license texts, `verified` ingest rules in `CLAUDE.md`).

Remotion, if someone proposes it as a render farm, has a price only after the headcount test fails. The FAQ says a for-profit organization with up to 3 people may run an automation and a SaaS on the Free License, with no account. At 4 or more people, "Remotion for Automators" is the fit for `renderMedia()`, `renderMediaOnLambda()`, and `npx remotion render`. The FAQ price is $0.01 per successful render and $100 per month minimum. Client-side rendering has telemetry that cannot be turned off. Server-side telemetry is voluntary for Free License users. The FAQ says Remotion 5.0 will require telemetry for Automators customers. Headcount of this company was not read (`not measured`). An unacceptable use on the FAQ is a service that renders Remotion projects the customer uploads. Rendering the company's own templates is the allowed example.

## Docker and CUDA integration risk

| Choice | What the texts require | Label |
|---|---|---|
| Keep today's CPU image | No CUDA redistributable is installed. faster-whisper stays `device="cpu"`. The GPL and LGPL ffmpeg copies are the compliance work. | `verified` Dockerfile |
| Add a CUDA wheel to that same image | CUDA EULA 1.2.5 forbids causing the SDK to become subject to a license that demands source disclosure. GPL ffmpeg libraries and CUDA redistributables stay in separate binaries. | `public-source` EULA. Layout `inferred` |
| faster-whisper on GPU | README says current CTranslate2 wants CUDA 12 and cuDNN 9. Older pins exist for CUDA 11. | `public-source` |
| TorchCodec CUDA wheel | README points CUDA builds at the CUDA EULA. CPU TorchCodec still needs system FFmpeg shared libraries, which on this VM are the GPL build. | `public-source`. System ffmpeg `measured` |
| PyNvVideoCodec in the image | PyPI says MIT. NVIDIA says the library calls the Video Codec SDK. Redistribution follows the SDK agreement, not the MIT line alone. | `public-source` |
| NGC PyTorch base image | The playbook README suggests `nvcr.io/nvidia/pytorch:26.03-py3`. That container's contract was not read. | `not measured` |
| Hugging Face gated weights in the image | `speaker-diarization-3.1` and `community-1` raw cards returned 401 without a token. Baking them needs an accepted gate and a secret. The Dockerfile already bakes Whisper weights with no token. | `public-source` 401. Whisper bake `verified` |
| yt-dlp extras | README lists `mutagen` as GPLv2-or-later and `curl_cffi` as MIT. `requirements.txt` says no extras. Leave it that way. | `public-source` and `verified` |

## Falsifiability checks

A license claim is falsified by the file named here, read on 2026-11-20, disagreeing with the draft. A speed claim is not falsified by this note. Falsify a speed claim with the same VOD, the same machine, and `scripts/job_timings.py` before and after (`not measured` here).

| Draft claim | Check | Result |
|---|---|---|
| Agent 1. yt-dlp wheel is Unlicense. | Repo `LICENSE` plus README sentence that the wheel contains only Unlicense code. | Stands. |
| Agent 1. Standalone binaries can be GPLv3-or-later. | README licensing section. | Stands. The PyInstaller build is the one named. |
| Agent 1. Streamlink is BSD-2-Clause. PyPI 8.6.3. | `LICENSE` file and GitHub SPDX. | Stands. |
| Agent 1. "Tool BSD/Unlicense" as one label. | Compare the two LICENSE files. | The sentence mixes two licenses. yt-dlp is Unlicense. Streamlink is BSD-2-Clause. |
| Agent 1. N_m3u8DL-RE and Lux are MIT. gallery-dl is GPLv2. | GitHub SPDX MIT, MIT, and GPL-2.0. gallery-dl `LICENSE` is the GPL version 2 text. | Stands. |
| Agent 2. PyNvVideoCodec is MIT over the Video Codec SDK. | PyPI MIT classifier and the NVIDIA product page. | Stands. The SDK agreement remains in force for SDK materials. |
| Agent 2. TorchCodec is BSD-3 and a CUDA build needs an NVIDIA review. | `LICENSE` and the README CUDA paragraph. | Stands. |
| Agent 2. Decord is Apache-2.0 and quieter than TorchCodec. | `LICENSE` and last push 2024-07-17 versus TorchCodec pushed 2026-11-19. | Stands. Quiet is maintenance, not a license. |
| Agent 3. faster-whisper and the OpenAI weights are MIT. | `LICENSE` files, OpenAI README sentence, Systran `small.en` card `license: mit`. | Stands. |
| Agent 3. WhisperX code is BSD-2-Clause. | `LICENSE` and PyPI 3.8.6. | Stands. |
| Agent 3. Default FR, DE, ES, IT align models are CC-BY-NC 4.0. | Four HF cards, each `license: cc-by-nc-4.0`. Issue 962 names the same four torchaudio ids. | Stands for those four cards. |
| Agent 3, via issue 962. The English align model is MIT. | HF `facebook/wav2vec2-base-960h` card says `license: apache-2.0`. | The MIT word is wrong for that card. Apache-2.0 still allows commercial use. |
| Agent 3. `speaker-diarization-community-1` is CC BY 4.0. | Raw README returned HTTP 401. | Not confirmed on this pass. |
| Agent 3. Silero weights and code are MIT. | `LICENSE` is MIT. Maintainer reply on 2026-10-25 is "MIT". README alt text still says CC BY-NC 4.0. | The grant text and the maintainer reply support MIT. The badge alt text is still a contradicting string. |
| Agent 4. PANNs and YAMNet are Apache-2.0. | `qiuqiangkong/audioset_tagging_cnn` GitHub SPDX is MIT. `research/audioset/yamnet/yamnet.py` header is Apache-2.0. | The single Apache label is wrong for the PANNs code repo. YAMNet's file header is Apache-2.0. Checkpoint files were not opened. |
| Agent 5. Remotion Lambda is paid, labeled `verified` from CLAUDE.md. | Remotion FAQ. Free License includes automation and a SaaS at headcount up to 3. Above that, Automators is $0.01 per render and $100 per month minimum. | The blanket "paid" claim is incomplete. CLAUDE.md does not state that price. AWS charges are a separate bill. |
| Agent 5. Remotion is a poor server replacement for `render.py`. | License texts do not describe the filter graph. | Not a license result. The architecture conclusion is untouched. |
| Coordinator stub in this file. OpenCV, Decord, and Silero marked OK. NVIDIA samples marked as sample terms. | Rows in the matrix above. | OpenCV wheels ship LGPL FFmpeg. Decord's license is fine and the project last moved in 2024. Silero's badge alt text disagrees with its LICENSE. The playbook is MIT. `video-sdk-samples` has no repo license. |

## Production risk ranking

Order is the adoption decision each row changes. It is not a score. Nothing here was timed.

1. **Block a Remotion server renderer until headcount is known.** If the company has 4 or more people, an automation needs the Company License before the first production render (`public-source` FAQ). Headcount is `not measured`. The technical mismatch with `render.py` is Agent 5's claim and is separate.
2. **Block WhisperX for commercial non-English captions.** The four default align weights are CC-BY-NC 4.0 (`public-source`). An English-only trial can use the Apache-2.0 aligner card. Do not enable diarization until `speaker-diarization-community-1` is read. The raw card was 401.
3. **Block code copies from unlicensed trees.** `azmifauzan/clipgen` returned 404 for `LICENSE`. `NVIDIA/video-sdk-samples` has no repo license. `JerryX2026/clipgen` is MIT on PyPI and has no GitHub-detected LICENSE file.
4. **Keep CUDA off the CPU image.** A GPU worker is a second image. GPL ffmpeg stays a separate process from CUDA and from the Video Codec SDK (`public-source` EULA and SDK agreement, `inferred` for the process split). PyNvVideoCodec's MIT line does not replace that agreement.
5. **Write down the ffmpeg we already ship before any public image.** The measured binary is a GPL build with libx264 and libx265, and it is not a `--enable-nonfree` build. The OpenCV 4.x wheels add LGPL FFmpeg. A published image needs corresponding source for those binaries. H.264 patent exposure is still an open Via LA program as of 1 November 2026, with no fee computed here.
6. **Silero stays as the faster-whisper bundle.** The `LICENSE` file is MIT. Fix nothing in production because of the badge. Do not describe the badge alt text as the grant.
7. **Decord stays out unless a maintainer appears.** Apache-2.0 is fine. Last push 2024-07-17 (`public-source`).
8. **Clear on the license text, with notices.** faster-whisper, CTranslate2, the `small.en` weights named above, the yt-dlp wheel, Streamlink, PySceneDetect, MediaPipe's code, and the playbook `LICENCE`. Streamlink and yt-dlp still do not license the footage.

## Read log

Re-check by opening the same URL and comparing the license name.

| Artifact | URL | Result |
|---|---|---|
| FFmpeg `LICENSE.md` | https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md | 200, LGPL-2.1-or-later, GPL on `--enable-gpl`, libx264 under GPL version 2 |
| FFmpeg legal page | https://ffmpeg.org/legal.html | 200, GPL once GPL parts are used, patent Q&A names MPEG LA |
| faster-whisper, CTranslate2, OpenAI Whisper | GitHub `LICENSE` on each repo | 200, MIT |
| OpenAI weights sentence | https://github.com/openai/whisper/blob/main/README.md | "code and model weights" under MIT |
| Systran small.en | https://huggingface.co/Systran/faster-whisper-small.en | card `license: mit` |
| yt-dlp | https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE and README licensing | Unlicense wheel. GPLv3-or-later PyInstaller binary |
| OpenCV and opencv-python | opencv `LICENSE`, opencv-python `LICENSE.txt`, `4.x/README.md` | Apache-2.0, MIT scripts, wheels ship LGPLv2.1 FFmpeg |
| TorchCodec | https://github.com/pytorch/torchcodec/blob/main/LICENSE and README | BSD-3-Clause. CUDA paragraph points at the CUDA EULA |
| PyNvVideoCodec | https://pypi.org/project/PyNvVideoCodec/ and https://developer.nvidia.com/pynvvideocodec | PyPI 2.2.4 MIT. Page says Video Codec SDK inside |
| Video Codec SDK agreement | https://developer.nvidia.com/nvidia-video-codec-sdk-license-agreement | object-code distribution, grant-back, one-year renewing term |
| CUDA EULA | https://docs.nvidia.com/cuda/eula/ | updated 26 January 2026. Section 1.2 item 5 |
| WhisperX | https://github.com/m-bain/whisperX/blob/main/LICENSE | BSD-2-Clause |
| Align model cards | HF `facebook/wav2vec2-base-960h` and the four `wav2vec2-base-10k-voxpopuli-ft-*` cards | apache-2.0, then cc-by-nc-4.0 four times |
| Issue 962 | https://github.com/m-bain/whisperX/issues/962 | open, claims EN is MIT and the other four are CC-BY-NC |
| pyannote.audio | https://github.com/pyannote/pyannote-audio/blob/develop/LICENSE | MIT |
| pyannote model cards | HF `speaker-diarization-3.1` and `speaker-diarization-community-1` raw README | 401 on the later raw fetch |
| Decord | https://github.com/dmlc/decord/blob/master/LICENSE | Apache-2.0. Pushed 2024-07-17 |
| PySceneDetect | https://github.com/Breakthrough/PySceneDetect/blob/main/LICENSE | BSD-3-Clause |
| Silero | https://github.com/snakers4/silero-vad/blob/master/LICENSE and README, discussion 817 | MIT file. Badge alt text CC BY-NC 4.0. Maintainer "MIT" on 2026-10-25 |
| MediaPipe | https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE | Apache-2.0 |
| Remotion | https://github.com/remotion-dev/remotion/blob/main/LICENSE.md and https://www.remotion.dev/docs/license/faq | Free License through 3 people. Automators price above that |
| Streamlink | https://github.com/streamlink/streamlink/blob/master/LICENSE | BSD-2-Clause |
| Playbook | https://github.com/NVIDIA-AI-Technology-Center/accelerated-video-for-ai-playbook/blob/main/LICENCE | MIT. Filename is `LICENCE` |
| video-sdk-samples | https://github.com/NVIDIA/video-sdk-samples | no GitHub license, README silent |
| ClipGen repos | `azmifauzan/clipgen`, `JerryX2026/clipgen`, `realise-lab/CLIPGen`, `HFAiLab/clip-gen` | no license, PyPI MIT with no GitHub license, BSD-3 chiplet tool, MIT text-to-image |
| gallery-dl, N_m3u8DL-RE, Lux, PANNs | GitHub license API | GPL-2.0, MIT, MIT, MIT |
| This VM | `ffmpeg -version`, `ldd /usr/bin/ffmpeg` | GPL configure flags and libx264, libx265, libass |

throughput checkpoint: n/a, read-only investigation.
