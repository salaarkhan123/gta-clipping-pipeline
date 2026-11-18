# Transcription benchmark on the server (owner runs it)

The provider keys are on the production server in `/root/clip-api/.env.benchmark`, so the benchmark runs
there. It runs in a separate, throw-away container built from this branch. The production containers, their
`.env` and their data volume are not touched. Nobody but you connects to the server.

**Cost:** about $2.40 for every command on this page. The breakdown is in [Cost per run](#cost-per-run).

## Where the audio may go

Audio goes only to services that do not train on it. Each service's policy was read from its own pages on
2026-11-18:

| Service | Trains on our audio? | What the benchmark and the app do |
|---|---|---|
| Groq | No. Services Agreement section 4.2: "Groq is not permitted to use Inputs or Outputs for training". Inputs are not kept, except temporary logs (up to 30 days) for errors and abuse. | Nothing to set. Optional: turn on Zero Data Retention in the Groq console under Data Controls. |
| Deepgram | Yes, by default, through its Model Improvement Program. | Every request sends `mip_opt_out=true`, so Deepgram keeps the audio only while it processes the request. |
| AssemblyAI | Some files, "as permitted by the applicable contract". Files sent to its EU servers are excluded. A paid account can opt out under Data Controls. A free account cannot. | The benchmark uses the EU servers by default (`--assemblyai-region eu`). It refuses the US servers unless you opted out and pass `--assemblyai-opted-out`. The transcript is deleted from AssemblyAI after it is read. The uploaded audio is deleted within 24 to 48 hours. |

Sources:

- https://console.groq.com/docs/legal/services-agreement
- https://console.groq.com/docs/your-data
- https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program
- https://www.assemblyai.com/docs/data-retention-and-model-training
- https://www.assemblyai.com/docs/faq/how-to-opt-out-of-data-sharing-for-our-model-improvement-program

If AssemblyAI's EU server refuses the key (HTTP 401), choose one:

- Use a key from an EU project.
- Upgrade the account, opt out under Data Controls, and run with `--assemblyai-region us --assemblyai-opted-out`.

## 1. On the Mac: make the audio

The footage is in `~/ClutchClips-eval/`. Make the audio once:

```bash
cd "<repo>/clip-api"
~/ClutchClips-eval/heavy.sh bench-audio scripts/prep_bench_audio.sh
```

The script writes `~/ClutchClips-eval/bench-audio/`, 0.85 GB. Game audio barely compresses: FLAC is about the size of the WAV. Every file is 16 kHz mono FLAC, the format
Groq recommends. Deepgram and AssemblyAI take it as is.

| File | What |
|---|---|
| `masters/<video>.flac` | the whole first audio track of each video: forza, gta6, valorant, fortnite, gta5, gta-online |
| `bench-30-valorant.flac` | valorant, 0:00 to 30:00 |
| `bench-60-gta5.flac` | gta5, 0:00 to 60:00 |
| `bench-120-mixed.flac` | gta5 (0 to 4232 s), then gta-online (4232 to 6327 s), then forza (6327 to 7200 s), cut at 120:00. No single video is 2 hours long. |
| `bench-120-mixed.txt` | where each video starts and ends in the 120-minute file, in seconds |
| `SHA256SUMS` | checksums of all of the above |

None of it goes into git.

## 2. Copy it to the server

From the Mac, with your server's address in place of `<droplet>`:

```bash
ssh root@<droplet> 'mkdir -p /root/bench/audio /root/bench/video /root/bench/results && df -h /'
rsync -avP ~/ClutchClips-eval/bench-audio/ root@<droplet>:/root/bench/audio/
ssh root@<droplet> 'cd /root/bench/audio && sha256sum -c SHA256SUMS'
```

Every line must end in `OK`.

The clip comparison (`--select`, step 4) also needs the video. Copy only the videos you run it on, for
example:

```bash
rsync -avP ~/ClutchClips-eval/valorant.mp4 ~/ClutchClips-eval/gta-online.mp4 root@<droplet>:/root/bench/video/
ssh root@<droplet> 'cd /root/bench/video && sha256sum valorant.mp4 gta-online.mp4'
```

Compare those two lines with `shasum -a 256 ~/ClutchClips-eval/valorant.mp4 ~/ClutchClips-eval/gta-online.mp4`
on the Mac.

**Disk needed on the server:**

| What | Size |
|---|---|
| Audio | 0.85 GB |
| Image | about 4 GB |
| Two videos for `--select` | 1.3 GB |
| Temporary WAV during a run, deleted after | 0.25 GB for 120 minutes |
| **Total** | **about 6.5 GB** |

Check the free space with `df -h /` before you start.

## 3. Build the image

```bash
chmod 600 /root/clip-api/.env.benchmark
git clone --branch feat/transcription-providers git@github.com:salaarkhan123/gta-clipping-pipeline.git /root/bench-code
cd /root/bench-code/clip-api
docker build -t clutchclips-bench .
```

The image is built from the same Dockerfile as production and bakes in `small.en` and `base.en`.

## 4. Run it

Run it while no customer job is running. The local model uses the same 4 vCPUs as the worker. Check with
`docker stats --no-stream`: the worker's CPU should be near 0 %.

Set up the shared part of the command once per shell:

```bash
B="docker run --rm --cpus 2 --memory 3g -e OMP_NUM_THREADS=2 --user 0:0 --cap-drop ALL --security-opt no-new-privileges \
  -v /root/clip-api/.env.benchmark:/run/secrets/bench.env:ro -v /root/bench:/bench \
  clutchclips-bench python scripts/transcribe_bench.py --keys-file /run/secrets/bench.env"
P=local:base.en,groq:whisper-large-v3-turbo,deepgram,assemblyai
```

Then run the three inputs, one at a time. The local model is the slow part: on 2 vCPUs expect roughly 20 to
40 minutes for the 120-minute input with `base.en`. `small.en` is about 3 times slower, so it runs on the
30-minute input only:

```bash
$B --audio /bench/audio/bench-30-valorant.flac --providers local:small.en,$P --out /bench/results/30
$B --audio /bench/audio/bench-60-gta5.flac     --providers $P --out /bench/results/60
$B --audio /bench/audio/bench-120-mixed.flac   --providers $P --out /bench/results/120
```

The clip comparison needs a whole video, because it reads the picture too:

```bash
$B --audio /bench/video/valorant.mp4 --providers $P --select --out /bench/results/select-valorant
```

Each run prints which providers have a key, never the key itself. At the end it prints a table.

What each flag is for:

| Flag | Why |
|---|---|
| `--cpus 2 --memory 3g -e OMP_NUM_THREADS=2` | Leaves production 2 vCPUs and its memory. The local model uses 2 threads to match. |
| `--user 0:0 --cap-drop ALL --security-opt no-new-privileges` | The image runs as `app`, which cannot read a root-owned `chmod 600` file. Root without capabilities can read only files that root owns. |
| `.env.benchmark:...:ro` | The keys file, read-only. The script reads it into its own process and does not change the environment. It refuses the file if other users can read it. |

**Local numbers at production speed.** The 2-CPU cap makes the local model slower than on production's 4
vCPUs. While no job runs, add one more run:

```bash
docker run --rm --cpus 4 --memory 3g -e OMP_NUM_THREADS=4 --user 0:0 --cap-drop ALL -v /root/bench:/bench \
  clutchclips-bench python scripts/transcribe_bench.py --audio /bench/audio/bench-120-mixed.flac \
  --providers local:base.en --out /bench/results/120-local-4cpu
```

**Groq rate limit.** The developer plan's base limit is 7,200 audio seconds per hour, which is 2 hours of audio
per hour. The 120-minute run uses all of it, so run Groq's `whisper-large-v3` on its own an hour later:

```bash
$B --audio /bench/audio/bench-120-mixed.flac --providers groq:whisper-large-v3 --out /bench/results/120-groq-v3
```

A 429 error shows up under "Retries / errors" in the table.

**Judge.** The judge runs when the keys file has `ANTHROPIC_API_KEY` and `--select` is given. It costs Claude
tokens, roughly 3,000 input tokens per candidate, for every provider's run. To leave it out, add `--judge off`.

## 5. Paste back

For each folder in `/root/bench/results/`, paste `summary.md` and `results.json` into the PR. They contain no
keys and no transcript, only numbers and at most 5 example words from the hallucination check.

`transcripts/` and `moments/` stay on the server.

## 6. Clean up

```bash
docker image rm clutchclips-bench
rm -rf /root/bench-code /root/bench/audio /root/bench/video
```

Keep `/root/bench/results` until the numbers are in `provider-comparison.md`.

## Cost per run

Pay-as-you-go prices from the providers' pages, read 2026-11-18. Sources are in `provider-comparison.md`.

| Provider | $ per audio hour | 3 inputs (3.5 h) | One `--select` run (33 min) |
|---|---|---|---|
| Groq whisper-large-v3-turbo | 0.04 | $0.14 | $0.02 |
| Deepgram Nova-3, diarization included | 0.258 | $0.90 | $0.14 |
| AssemblyAI assemblyai-stt-3-7 + diarization | 0.23 | $0.81 | $0.13 |
| Local | 0 extra | $0 | $0 |
| **Total** | | **$1.85** | **$0.29** |

The extra Groq `whisper-large-v3` run on the 120-minute input costs $0.22 ($0.111 per hour). All commands on
this page together: about $2.40, plus the judge's tokens.

Groq bills at least 10 s per request. The script sends 10-minute chunks, so that minimum never applies.

New accounts get trial credit that covers several runs: Deepgram $200 and AssemblyAI $50. Groq has a free tier.

## What the numbers decide

Target: a 2-hour video gives previews in under 5 minutes, and the final render takes under 2 more. The summary
shows how much of the 300 s each provider's transcription takes. Choose by:

1. Time on the 120-minute input, measured.
2. WER and term recall against a reference, and words heard in non-speech.
3. Overlap with the local baseline's clips, plus the eval numbers once the sheet has ratings.
4. Cost per 2-hour VOD, compared with the cheapest credit price of $0.576 per source hour.

To make a model reference for an input:

```bash
$B --audio /bench/audio/bench-30-valorant.flac --make-reference large-v3 --out /bench/ref-30
```

This is slow on 2 vCPUs: several times the length of the audio. Make the reference on a faster machine if
you can. Then add `--reference /bench/ref-30/reference.json` to the runs on that input.
