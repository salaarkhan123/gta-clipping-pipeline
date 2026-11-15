# QA v1 for #7 (PR #16)

Head under test: `1834786`. Env: macOS, ffmpeg-full (libass), repo `.venv` Python 3.12.

- `pytest -q tests/test_bench_pipeline.py`: 4 passed
- `pytest -q` (full clip-api suite): 62 passed, 13 skipped
- CLI on a generated 20 s 1280x720 clip, `--chat-region top-right --transcriber none`:
  `{"source_minutes": 0.33, "wall_seconds": 1.32, "realtime_factor": 15.13, "peak_rss_mb": 491.9, "clips": 1, "credits": 1, "chat_region": "top-right"}` (exit 0)
- Spy on `run_pipeline`: `PipelineOptions.chat_region == "top-right"` and the JSON echoes it.
- `--chat-region bogus` is rejected by argparse.

Env note: stock Homebrew `ffmpeg` has no `ass` filter, so 11 existing pipeline tests and 2 bench tests fail there. This is the same on `staging`; it is not caused by this PR. CI uses the Docker image.

Test gaps (not written, Medium): no test asserts `PipelineOptions.chat_region` reaches `run_pipeline` (tests check only the echo); no test for exit code 1 on `PipelineError`.
