# QA v1 · issue #3 · head e791810

| AC | Result | Proof |
|---|---|---|
| Plain pytest skips, reason names RUN_WHISPER_E2E | pass | `pytest -q -rs`: 53 passed, 4 skipped; both new tests skipped with "opt-in: set RUN_WHISPER_E2E=1 ..." |
| Enabled, no synthesizer: skip names tool | pass | `RUN_WHISPER_E2E=1` with `say` off PATH: 2 skipped, "no speech synthesizer on PATH: install macOS `say` or Linux `espeak-ng`" |
| 40 s clip, phrase at ~5 s and ~25 s | pass (code read + run) | `SPEECH_AT = (5, 25)`, `adelay` per offset, `-t 40`, testsrc2 640x360@15 like the `video` fixture |
| Transcript has "clutch" and "clips" | pass | `RUN_WHISPER_E2E=1 pytest tests/test_whisper_e2e.py`: 2 passed in 12.8 s, real tiny.en |
| run_pipeline renders a clip ffprobe reads | pass | `test_run_pipeline_with_real_whisper` passed; options match `test_run_pipeline_end_to_end` |
| No media committed | pass | PR diff is one file, `clip-api/tests/test_whisper_e2e.py`; media lives in tmp dirs |

Not run: espeak-ng path (not installed on this Mac).
