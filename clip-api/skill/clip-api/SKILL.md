---
name: clip-api
description: Turn a long gameplay or stream recording into short captioned vertical clips with the Clip API. Use when the user wants highlights, shorts, TikToks or Reels cut from a local video file.
---

# Clip API

Finds the best moments in a long video and renders captioned clips. Costs 1 credit per minute of source video; failed jobs are refunded automatically.

## Setup

- `CLIPAPI_KEY`: the user's API key (starts with `gck_`). Ask for it if it is not set. Never print it.
- `CLIPAPI_URL`: API base URL. Ask the user if it is not set.

## Steps

1. Confirm the source is a local video file the user has the rights to clip. This API takes uploads only, not links.
2. Run the bundled client:

   ```bash
   python scripts/clip.py VIDEO_PATH --clips 3 --length 30 --out ./clips
   ```

   Options: `--clips 1-10`, `--length 10-60` (seconds), `--horizontal` (keep the source aspect instead of 9:16), `--chat-region top-right|top-center|top-left|bottom-right|bottom-left` (when the stream chat is visible in the video; it is used as a signal and shown above the gameplay), `--no-captions`, `--facecam top-left|top-right|bottom-left|bottom-right` (where the streamer's camera is; gives the split layout with the cam on top and gameplay below), `--layout auto|split|fill|classic`.
3. The script uploads, starts the job, polls until it finishes, downloads the clips and prints each clip's time range, score and which signals picked it.
4. Report the saved file paths and the credits charged.

## Other tools (same auth, same job polling)

- Reframe to 9:16 without detection: `POST /v1/reframe {upload_id, segments?: [{start, end}], options: {facecam_region, layout}}`
- Burn captions into a video: `POST /v1/captions {upload_id, segments?, options: {caption_style: pop|bold|neon|boxed|clean, vertical}}`
- Find moments by what was said: `POST /v1/find {upload_id, query, max_results, make_clips, clip_length}`; matches are in `job.result.matches`. After the first search of an upload, `GET /v1/uploads/{upload_id}/search?q=...` is instant and free.

- Options shared by every tool: `aspect` (`9:16`, `4:5`, `1:1`, `16:9`), `facecam_region` (`auto` detects the streamer's camera), `caption_style`.
- Each clip in a finished job has `title`, `description`, `hashtags` and `virality` (when the server has AI enabled), and `GET /v1/clips/{clip_id}/subtitles?format=srt|vtt|txt` returns its subtitles.
- Video Finder searches what was said and what is on screen: `mode` is `auto`, `speech` or `visual`.

## Errors

- `402 insufficient_credits`: tell the user how many credits the video needs and that they can buy more on the website.
- `413 file_too_large` / `video_too_long`: the file exceeds the service limits; suggest trimming it.
- `429 too_many_jobs` / `rate_limited`: wait for running jobs to finish, then retry.
- `FAILED` job: report `error.message`. Credits were refunded; do not retry more than once.

## Direct API use

`POST /v1/uploads?filename=NAME` (raw file body) -> `upload_id`; `POST /v1/clips {upload_id, options}` -> `job_id`; `GET /v1/jobs/{job_id}` until `status` is `SUCCEEDED`, `FAILED` or `CANCELED`. All requests need `Authorization: Bearer $CLIPAPI_KEY`. Full reference: `$CLIPAPI_URL/docs`.
