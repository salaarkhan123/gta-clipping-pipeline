# Transcript reuse (U1) — ops playbook

Confirm that repeat Clip Maker / Video Finder jobs reuse stored Heard pieces instead of transcribing again.
No 2-hour VOD measurement is included here (**not measured** on this change).

## What is stored

| File | Written by | Read by |
|---|---|---|
| `transcripts/<upload>.json` | Video Finder, Transcript/Summary tools, or Clip Maker with `TRANSCRIBE_WHOLE=true` | Later jobs in the same language |
| `transcripts/<upload>.parts.json` | Clip Maker candidate windows | Later Clip Maker / Finder jobs (pieces only; does not claim a whole transcript for pricing) |

Reuse works for Clip Maker parts **without** `TRANSCRIBE_WHOLE`. The LLM pass and whole-recording skip need a whole transcript (`TRANSCRIBE_WHOLE=true`, or an earlier Finder/transcript job).

## Confirm reuse on a repeat job

1. Run Clip Maker (or find) on an upload; note `job_id` A.
2. Run the same tool again on the **same** `upload_id` (same language); note `job_id` B.
3. Fetch both job payloads and compare with `job_timings.py`:

```bash
curl -s $API/v1/jobs/<A> -H "authorization: Bearer $KEY" > first.json
curl -s $API/v1/jobs/<B> -H "authorization: Bearer $KEY" > repeat.json
python scripts/job_timings.py first.json
python scripts/job_timings.py repeat.json --baseline first.json
```

### Clip Maker — healthy repeat

On job B look at `result.counts` / the rates line from `job_timings.py`:

- `transcript_reuse_rate` near **1.0** (all candidate windows read from Heard).
- `transcript_reused` ≥ 1; `transcript_transcribed` = 0 when every window was already covered.
- `transcribe_rough` / `transcribe_final` stages **absent** (or ~0 s) when nothing new was transcribed.
- `heard_pieces` ≥ 1 when earlier Clip Maker parts were loaded.
- With `TRANSCRIBE_WHOLE=true` and an existing whole transcript: `transcript_whole_reused` = 1 and no `transcribe_whole` stage.

### Video Finder / transcript tool — healthy repeat

- `result.transcript_cached` is **true** on the second job.
- `job_timings.py` prints `transcript cached True`.

### Unhealthy / partial reuse

- `transcript_reuse_rate` well below 1, or `transcribe_rough` still dominates run time on a re-run of the same upload and language.
- Language mismatch: a second job in another language does **not** reuse (`transcript_cached` false / new transcription).
- Missing or unreadable `*.parts.json` / `*.json` (worker logs a warning and transcribes again).

## What this change measured vs not

| Claim | Label |
|---|---|
| Existing Heard / `load_heard` / `save_parts` path on RC | verified in code and unit/API tests |
| `transcript_reused` + `transcript_transcribed` → `transcript_reuse_rate` in `job_timings.py` | measured via tests on fixture job JSON |
| Repeat Clip Maker skips Whisper when parts cover candidates | measured in existing API tests (`test_upload_transcript`, `test_stt`) |
| 2-hour VOD end-to-end reuse wall time | **not measured** |
