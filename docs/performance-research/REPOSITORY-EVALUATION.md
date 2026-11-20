# Repository evaluation

Status: draft scaffold. Filled by research Agents 1–3, 5, 8.

Claim labels follow [RESEARCH.md](RESEARCH.md).

## Method

For each technology: activity (last release / commits), license, dependencies, hardware needs, overlap with ClutchClips today, production suitability. Do not recommend replacing an existing piece without measured evidence it is superior.

## Inventory (seed)

| Technology | Role we care about | In ClutchClips today | Notes |
|---|---|---|---|
| FFmpeg | decode, encode, filters | yes (`pipeline/ff.py`, libx264) | verified |
| faster-whisper | ASR | yes, CPU int8 | verified |
| yt-dlp | link import | yes, pinned, no evasion | verified |
| OpenCV | facecam | yes, Haar | verified |
| fastembed CLIP | visual search | yes | verified |
| NVIDIA Accelerated Video for AI Playbook | NVDEC patterns | no | evaluate |
| PyNvVideoCodec | GPU decode/encode | no | evaluate |
| TorchCodec | torch video I/O | no | evaluate |
| ClipGen | clip generation reference | no | evaluate |
| WhisperX | ASR + align + diarize | no | evaluate |
| PySceneDetect | scene cuts | no (timeline on #218) | evaluate |
| Silero VAD | speech activity | via faster-whisper VAD | evaluate standalone |
| MediaPipe | face / pose | no (OpenCV today) | evaluate |
| Remotion | JS render | no | likely unfit for server pipeline |
| Streamlink | live streams | no | ingest rules constrain use |
| Decord | frame decode | no | evaluate |
| Anthropic API | judge / copy | yes | verified |

## Detailed evaluations

_Sections below filled during fan-out._
