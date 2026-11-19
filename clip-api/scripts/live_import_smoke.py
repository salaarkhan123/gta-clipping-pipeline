#!/usr/bin/env python3
"""One link, end to end, through the PUBLIC API of a running stack: preview, import, clips, export, download.

It makes exactly the calls the website makes, as one test account, and stops at the first step that fails with
that step's name, the error code and the message. Nothing here reads the database, the server's files or its
settings, so it runs the same against a laptop and against production.

    export CLIP_API_TOKEN=...            # a session token or an API key of the test account; never printed
    python scripts/live_import_smoke.py --base-url https://api.example.com \\
        --url https://www.youtube.com/watch?v=VIDEO_ID --start 30 --end 90 --i-have-the-rights

Steps, each printed as it happens:
  1. preview   POST /v1/imports/preview         what the link is, and the price of the chosen part
  2. start     POST /v1/clips/from-url          with start_sec / end_sec and an Idempotency-Key
  3. import    GET  /v1/jobs/{id} (polled)      every import stage, with the bytes downloaded
     footage   the same job's `import.fetched`  what was charged for next to what was actually downloaded
  4. clips     GET  /v1/jobs/{id} (polled)      every clip-job stage; then the clips
  5. quote     POST /v1/clips/export/quote      what the export of the first clip would reserve
  6. export    POST /v1/clips/export (polled)   the full-quality render
  7. download  the export's file                saved under --out
  8. verify    ffprobe on the saved file        a picture and sound, and every frame decodes to the full length
  9. credits   GET  /v1/credits                 balance before and after, the ledger rows of the jobs, the net

The link must be one the account holder owns or may clip: `--i-have-the-rights` is the consent the API asks for,
given by the person running this. Without it nothing is sent.

It spends real credits on the account when it succeeds (the clip job, then the export). A failed or refused import
must cost nothing: step 9 runs on failure too and prints the net, and the exit code says which it was.

A job that outlasts --timeout is cancelled (a cancel refunds it in full) unless --leave-running is given.

Exit codes: 0 all steps passed; 1 a step failed (the line starting `FAILED` says where); 2 bad arguments or no
token; 3 a failed run did not come back to its starting balance (credits were lost: tell the owner).

Printed text is cleaned first: bearer tokens, API keys, signed query strings and download tokens are replaced
with `<redacted>`, so the output can be pasted into a ticket.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

FINAL = ("SUCCEEDED", "FAILED", "CANCELED")
SAFE_IN = ["-protocol_whitelist", "file,pipe"]      # ffprobe reads the saved file only (CLAUDE.md)
SECRET_PATTERNS = (
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1<redacted>"),
    (re.compile(r"\b(?:ck|sk|pk|rk|whsec)_[A-Za-z0-9_-]{8,}"), "<redacted>"),                 # API and provider keys
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),   # JWTs
    (re.compile(r"(/v1/files/)[A-Za-z0-9._~-]+"), r"\1<redacted>"),                           # signed download paths
    # the whole query of a signed address (a bucket link); a plain video link keeps its `?v=...`
    (re.compile(r"(?i)(https?://[^\s\"'<>?]+)\?(?=[^\s\"'<>]*(?:x-amz-|signature=|expires=|awsaccesskeyid=|token=|sig=))"
                r"[^\s\"'<>]+"), r"\1?<redacted>"),
    (re.compile(r"(?i)\b(token|signature|sig|key|secret|password|x-amz-[a-z-]+)=[^\s&\"']+"), r"\1=<redacted>"),
)


def clean(text) -> str:
    """`text` with anything that could be a credential or a signed address taken out."""
    text = text if isinstance(text, str) else json.dumps(text, default=str)
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def say(step: str, text: str = "") -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {step:9s} {clean(text)}", flush=True)


class Failed(Exception):
    """A step that did not pass: where, the API's error code and its message."""

    def __init__(self, stage: str, code: str, message: str):
        super().__init__(f"{stage}: {code}: {message}")
        self.stage, self.code, self.message = stage, code, message


class Api:
    """The public API as one account. The token is sent in the Authorization header and nowhere else."""

    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout,
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": "clip-api-smoke/1"})

    def call(self, stage: str, method: str, path: str, body: dict | None = None, headers: dict | None = None,
             ok: tuple = (200, 201, 202)) -> dict:
        try:
            r = self.http.request(method, path, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise Failed(stage, "network_error", f"{type(e).__name__}: {e}") from None
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code not in ok:
            error = data.get("error") if isinstance(data, dict) and isinstance(data.get("error"), dict) else {}
            raise Failed(stage, str(error.get("code") or f"http_{r.status_code}"),
                         str(error.get("message") or r.text[:300] or r.reason_phrase))
        return data if isinstance(data, dict) else {"value": data}

    def credits(self, stage: str = "credits") -> dict:
        return self.call(stage, "GET", "/v1/credits")


def job_error(job: dict) -> tuple[str, str]:
    error = job.get("error") or (job.get("import") or {}).get("error") or {}
    return str(error.get("code") or job.get("status") or "unknown"), str(error.get("message") or "No message.")


def mb(n) -> str:
    return "unknown size" if not isinstance(n, (int, float)) else f"{n / 1e6:.1f} MB"


def footage(job: dict, estimate: dict, trail: dict) -> None:
    """Charged for, next to downloaded. The price follows the range that was asked for; `import.fetched` follows
    the network: how the worker got the video, how many bytes and seconds came over, and the whole video's size
    in the same streams for comparison."""
    imp = job.get("import") or {}
    fetched, span = imp.get("fetched"), imp.get("range") or {}
    say("footage", f"import stages seen: {' > '.join(trail.get('stages') or []) or 'none'}; "
                   f"most bytes reported while downloading: {trail.get('bytes', 0)}")
    charged = (f"charged for: {estimate.get('duration_sec')} s"
               f"{' (' + str(span.get('start_sec')) + ' to ' + str(span.get('end_sec')) + ' s)' if span else ' (the whole video)'}"
               f", {job.get('credits_reserved')} credit(s) reserved")
    if not isinstance(fetched, dict):
        why = ("the import did not finish, so there is no final count" if imp.get("status") != "SUCCEEDED"
               else "this API does not report it (no import.fetched)")
        say("footage", f"{charged} | downloaded: {why}; see the stages and bytes above")
        return
    how = {"segments": "only the segments that hold the range", "whole_file": "the whole file, then cut",
           "stored_copy": "nothing: cut from a copy the account already had",
           "none": "nothing: the stored upload was handed back"}.get(fetched.get("mode"), str(fetched.get("mode")))
    say("footage", f"{charged} | downloaded: {fetched.get('seconds')} s, {mb(fetched.get('bytes'))} "
                   f"({fetched.get('bytes')} bytes), mode={fetched.get('mode')} ({how})")
    full_bytes, full_sec = fetched.get("full_bytes"), fetched.get("full_seconds")
    share = (f", so {100 * fetched['bytes'] / full_bytes:.1f}% of it was downloaded"
             if isinstance(full_bytes, (int, float)) and full_bytes > 0 and isinstance(fetched.get("bytes"), (int, float)) else "")
    say("footage", f"whole video in the same streams: {full_sec} s, {mb(full_bytes)}"
                   f"{' (the site does not size these streams)' if full_bytes is None else ''}{share}")


def follow(api: Api, job_id: str, step: str, timeout: float, every: float, trail: dict | None = None) -> dict:
    """Poll a job to its final state, printing each change of stage (and of the import's stage and bytes).
    `trail` collects the import's stages in order and the most bytes it reported."""
    seen, started, most_bytes = None, time.monotonic(), 0
    trail = trail if trail is not None else {}
    while True:
        job = api.call(step, "GET", f"/v1/jobs/{job_id}")
        imp = job.get("import") or {}
        importing = job.get("status") == "WAITING"
        most_bytes = max(most_bytes, imp.get("bytes_done") or 0)
        trail["bytes"] = most_bytes
        stages = trail.setdefault("stages", [])
        if imp.get("stage") and (not stages or stages[-1] != imp["stage"]):
            stages.append(imp["stage"])
        now = (job.get("status"), job.get("stage"), imp.get("status"), imp.get("stage")) if importing else \
              (job.get("status"), job.get("stage"))
        if now != seen:
            seen = now
            if importing:
                total = imp.get("bytes_total")
                size = f" bytes {imp.get('bytes_done') or 0}" + (f" of {total}" if total else "")
                say("import", f"{imp.get('status')} stage={imp.get('stage')} progress={imp.get('progress')}{size}")
            else:
                say(step, f"{job.get('status')} stage={job.get('stage')} progress={job.get('progress')}")
        if job.get("status") in FINAL:
            if most_bytes:
                say("import", f"most bytes seen while downloading: {most_bytes}")
            return job
        if time.monotonic() - started > timeout:
            where = f"import:{imp.get('stage')}" if importing else f"{step}:{job.get('stage')}"
            raise Failed(where, "smoke_timeout", f"The job was still {job.get('status')} after {int(timeout)} seconds.")
        time.sleep(every)


def probe(path: Path) -> dict:
    """What ffprobe says about the saved file after decoding every frame of the picture."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", *SAFE_IN, "-count_frames", "-show_entries",
         "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames,duration",
         "-of", "json", str(path)], capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise Failed("verify", "not_playable", (out.stderr or "ffprobe failed").strip().splitlines()[-1][:300])
    return {**json.loads(out.stdout or "{}"), "decode_errors": [line for line in out.stderr.splitlines() if line.strip()]}


def verify(path: Path, expected_sec: float | None) -> str:
    """The file has a picture and sound, and its picture decodes for the file's whole length."""
    info = probe(path)
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise Failed("verify", "no_video_stream", "The exported file has no picture.")
    if audio is None:
        raise Failed("verify", "no_audio_stream", "The exported file has no sound.")
    length = float((info.get("format") or {}).get("duration") or 0)
    num, _, den = str(video.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    frames = int(video.get("nb_read_frames") or 0)
    decoded = frames / fps if fps else 0.0
    if length <= 0 or frames <= 0:
        raise Failed("verify", "not_playable", "The exported file has no length or no frame that decodes.")
    if info["decode_errors"]:
        raise Failed("verify", "decode_errors", info["decode_errors"][0][:300])
    if abs(decoded - length) > max(1.0, 0.05 * length):
        raise Failed("verify", "plays_short", f"The file says {length:.2f} s but its picture decodes for {decoded:.2f} s.")
    if expected_sec and abs(length - expected_sec) > max(2.0, 0.15 * expected_sec):
        raise Failed("verify", "wrong_length", f"The export was quoted at {expected_sec:.2f} s and the file is {length:.2f} s.")
    return (f"{video.get('codec_name')} {video.get('width')}x{video.get('height')} at {fps:.2f} fps, "
            f"{audio.get('codec_name')} sound, {length:.2f} s, {frames} frames decoded ({decoded:.2f} s), "
            f"{path.stat().st_size} bytes")


def download(api: Api, url: str, dest: Path) -> None:
    """Save the export's file. A signed address needs no login; the API's own /v1/files address is fetched as is."""
    try:
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r:
            if r.status_code != 200:
                raise Failed("download", f"http_{r.status_code}", f"The file's address answered {r.status_code}.")
            with open(dest, "wb") as fh:
                for chunk in r.iter_bytes(1024 * 1024):
                    fh.write(chunk)
    except httpx.HTTPError as e:
        raise Failed("download", "network_error", f"{type(e).__name__}: {e}") from None
    if dest.stat().st_size == 0:
        raise Failed("download", "empty_file", "The export's file is empty.")


def run(api: Api, args, jobs: list[str]) -> None:
    span = {k: v for k, v in (("start_sec", args.start), ("end_sec", args.end)) if v is not None}
    options = json.loads(args.options)

    seen = api.call("preview", "POST", "/v1/imports/preview", {"url": args.url, "options": options, **span})
    estimate = seen.get("estimate") or {}
    say("preview", json.dumps({k: seen.get(k) for k in (
        "platform", "video_type", "live_status", "title", "channel", "category", "duration_sec", "range",
        "supported", "lookup_ms")} | {"options": seen.get("options"), "estimate": {
            k: estimate.get(k) for k in ("credits", "basis", "duration_sec", "balance", "enough")} or None}))
    if not seen.get("supported"):
        refusal = seen.get("refusal") or {}
        raise Failed("preview", str(refusal.get("code") or "refused"), str(refusal.get("message") or "Refused."))
    if seen.get("estimate") is None:
        raise Failed("preview", "no_estimate", "The preview gave no price for this link.")
    if estimate.get("enough") is False:
        raise Failed("preview", "insufficient_credits",
                     f"The job costs {estimate.get('credits')} credits and the account has {estimate.get('balance')}.")

    key = f"smoke-{uuid.uuid4()}"
    job = api.call("start", "POST", "/v1/clips/from-url", {"url": args.url, "consent": True, "options": options, **span},
                   headers={"Idempotency-Key": key})
    jobs.append(job["job_id"])
    imp = job.get("import") or {}
    say("start", f"job {job['job_id']} status={job.get('status')} reserved={job.get('credits_reserved')} "
                 f"import={imp.get('import_id')} reused={imp.get('reused')} range={imp.get('range')}")
    if job.get("credits_reserved") != estimate.get("credits"):
        raise Failed("start", "price_mismatch", f"The preview quoted {estimate.get('credits')} credits and the job "
                                                f"reserved {job.get('credits_reserved')}.")
    again = api.call("start", "POST", "/v1/clips/from-url", {"url": args.url, "consent": True, "options": options, **span},
                     headers={"Idempotency-Key": key})
    if again.get("job_id") != job["job_id"]:
        raise Failed("start", "not_idempotent", "The same Idempotency-Key started a second job.")
    say("start", "the same request again returned the same job (one reservation)")

    trail: dict = {}
    try:
        done = follow(api, job["job_id"], "clips", args.timeout, args.every, trail)
    finally:
        try:                                # also after a failure or a timeout: how far the download got
            footage(api.call("footage", "GET", f"/v1/jobs/{job['job_id']}"), estimate, trail)
        except Failed:
            pass
    imp = done.get("import") or {}
    if done.get("status") != "SUCCEEDED":
        failed_in_import = imp.get("status") not in (None, "SUCCEEDED")
        stage = f"import:{imp.get('stage') or imp.get('status')}" if failed_in_import else f"clips:{done.get('status')}"
        raise Failed(stage, *job_error(done))
    try:                                    # what the import stored: the proof of which streams were picked
        uploads = api.call("upload", "GET", "/v1/uploads").get("uploads") or []
        stored = next((u for u in uploads if (u.get("upload_id") or u.get("id")) == done.get("upload_id")), None)
        if stored:
            say("upload", f"{done.get('upload_id')} {stored.get('width')}x{stored.get('height')} "
                          f"{stored.get('duration_sec')} s {stored.get('size_bytes')} bytes sound={stored.get('has_audio')} "
                          f"file={stored.get('filename')!r}")
    except Failed as e:
        say("upload", f"could not list uploads: {e.code}")
    clips = done.get("clips") or []
    say("clips", f"{len(clips)} clip(s), charged {done.get('credits_charged')} of {done.get('credits_reserved')} reserved")
    for c in clips:
        say("clips", f"  {c.get('id')} {c.get('start_sec'):.1f}-{c.get('end_sec'):.1f} s rendered={c.get('rendered')} "
                     f"score={c.get('display_score')} title={c.get('title')!r}")
    if not clips:
        raise Failed("clips", "no_clips", "The job succeeded and found no clip in this part of the video. "
                                          "Try a longer or livelier range.")
    if args.no_export:
        return

    first = clips[0]
    body = {"job_id": job["job_id"], "clips": [first["id"]], "options": {"resolution": args.resolution}}
    quote = api.call("quote", "POST", "/v1/clips/export/quote", body)
    say("quote", f"credits={quote.get('credits_reserved')} seconds={quote.get('seconds')} "
                 f"resolution={quote.get('resolution')} already_rendered={bool(quote.get('existing'))}")
    export = api.call("export", "POST", "/v1/clips/export", body, headers={"Idempotency-Key": f"smoke-{uuid.uuid4()}"})
    url = None
    if export.get("job_id"):
        jobs.append(export["job_id"])
        say("export", f"job {export['job_id']} reserved={export.get('credits_reserved')}")
        rendered = follow(api, export["job_id"], "export", args.timeout, args.every)
        if rendered.get("status") != "SUCCEEDED":
            raise Failed(f"export:{rendered.get('status')}", *job_error(rendered))
        say("export", f"charged {rendered.get('credits_charged')} of {rendered.get('credits_reserved')} reserved")
        source = api.call("export", "GET", f"/v1/jobs/{job['job_id']}")
        url = next((c.get("export_url") for c in source.get("clips") or [] if c.get("id") == first["id"]), None)
    else:                                   # this render exists already: handed back free
        url = next((e.get("video_url") for e in export.get("existing") or [] if e.get("clip_id") == first["id"]), None)
        say("export", "this render already exists: handed back free")
    if not url:
        raise Failed("export", "no_export_url", "The export finished and the clip has no export_url.")
    if url.startswith("/"):
        url = str(api.http.base_url).rstrip("/") + url

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"{first['id']}.mp4"
    download(api, url, dest)
    say("download", f"saved {dest} from {url}")
    seconds = quote.get("seconds") or sum(c.get("seconds") or 0 for c in quote.get("existing") or []) or None
    say("verify", verify(dest, seconds))


def money(api: Api, before: int | None, jobs: list[str]) -> int | None:
    """Print the balance now, the ledger rows of this run's jobs, and the net. Returns the net (None: unknown)."""
    try:
        now = api.credits()
    except Failed as e:
        say("credits", f"could not read the balance: {e.code}: {e.message}")
        return None
    rows = [r for r in now.get("history") or [] if r.get("job_id") in jobs]
    for r in reversed(rows):
        say("credits", f"  {r.get('kind'):8s} {r.get('delta'):+d}  job={r.get('job_id')} at {r.get('created_at')}")
    for job_id in jobs:
        try:
            job = api.call("credits", "GET", f"/v1/jobs/{job_id}")
            say("credits", f"  job {job_id}: {job.get('status')}, reserved {job.get('credits_reserved')}, "
                           f"charged {job.get('credits_charged')}")
        except Failed:
            pass
    net = None if before is None else now.get("balance") - before
    say("credits", f"balance before={before} after={now.get('balance')} net={net:+d}" if net is not None
        else f"balance after={now.get('balance')}")
    return net


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", required=True, help="the API's address, for example https://api.example.com")
    ap.add_argument("--url", required=True, help="the public video link to import")
    ap.add_argument("--start", type=float, default=None, help="start of the part to import, seconds")
    ap.add_argument("--end", type=float, default=None, help="end of the part to import, seconds")
    ap.add_argument("--options", default='{"max_clips": 1, "clip_length": 15, "render": "preview"}',
                    help="the clip options, JSON (default: one 15-second clip, preview render, so the export is a real render)")
    ap.add_argument("--resolution", default="1080", help="the export's resolution (default 1080)")
    ap.add_argument("--token-env", default="CLIP_API_TOKEN", help="the environment variable that holds the token")
    ap.add_argument("--out", default="smoke-out", help="folder for the downloaded export")
    ap.add_argument("--timeout", type=float, default=1800, help="seconds to wait for each job (default 1800)")
    ap.add_argument("--every", type=float, default=2.0, help="seconds between polls (default 2)")
    ap.add_argument("--no-export", action="store_true", help="stop after the clips: no export, download or verify")
    ap.add_argument("--leave-running", action="store_true",
                    help="when a job outlasts --timeout, leave it running (default: cancel it, which refunds it)")
    ap.add_argument("--i-have-the-rights", action="store_true",
                    help="you own this video or have permission to clip it (the consent the API requires)")
    args = ap.parse_args()

    token = os.environ.get(args.token_env, "").strip()
    if not token:
        print(f"Set {args.token_env} to a session token or API key of the test account.", file=sys.stderr)
        return 2
    if not args.i_have_the_rights:
        print("Nothing was sent. Pass --i-have-the-rights to confirm you own this video or may clip it.", file=sys.stderr)
        return 2
    try:
        json.loads(args.options)
    except ValueError:
        print("--options must be JSON.", file=sys.stderr)
        return 2

    api, jobs, before, failure = Api(args.base_url, token), [], None, None
    say("target", f"{args.base_url} link={args.url} range={args.start}-{args.end}")
    try:
        before = api.credits("credits-before").get("balance")
        say("credits", f"balance before={before}")
        run(api, args, jobs)
    except Failed as e:
        failure = e
        print(f"FAILED stage={clean(e.stage)} code={clean(e.code)} message={clean(e.message)}", flush=True)
    in_flight = []
    if failure is not None and failure.code == "smoke_timeout":
        # A job that outlasted the wait still holds its credits. Cancel it (a cancel refunds in full) unless asked
        # not to, so the test account is left as it was found.
        for job_id in jobs:
            try:
                job = api.call("cancel", "GET", f"/v1/jobs/{job_id}")
                if job.get("status") in FINAL:
                    continue
                if args.leave_running:
                    in_flight.append(job_id)
                    say("cancel", f"job {job_id} is still {job.get('status')}: left running, its credits stay reserved")
                    continue
                api.call("cancel", "POST", f"/v1/jobs/{job_id}/cancel")
                for _ in range(30):
                    job = api.call("cancel", "GET", f"/v1/jobs/{job_id}")
                    if job.get("status") in FINAL:
                        break
                    time.sleep(2)
                say("cancel", f"job {job_id} cancelled: now {job.get('status')}")
                if job.get("status") not in FINAL:
                    in_flight.append(job_id)
            except Failed as e:
                in_flight.append(job_id)
                say("cancel", f"could not cancel job {job_id}: {e.code}: {e.message}")
    net = money(api, before, jobs)
    if failure is None:
        print("PASSED every step", flush=True)
        return 0
    spent_on_a_failed_import = (failure.stage.startswith(("preview", "start", "import")) and net not in (0, None)
                                and not in_flight)
    if spent_on_a_failed_import:
        print(f"CREDITS LOST: a run that failed at {clean(failure.stage)} ended {net:+d} credits from where it started.",
              flush=True)
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
