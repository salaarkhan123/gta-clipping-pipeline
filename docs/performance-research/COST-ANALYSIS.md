# Cost analysis

Coordinator note: promoted from Agent 6 draft (2026-11-20). Research only; no prices changed.


**Scope.** Research only. No droplet, Space, bucket, GPU pod, or hosted-transcription account was created. No price in `clip-api/app/plans.py` or `CREDIT_PACKS` was changed.
**Date.** 2026-11-20.
**Claim labels.** `measured` | `verified` | `inferred` | `hypothesis` | `public-source` | `not measured`. Definitions are in [RESEARCH.md](../RESEARCH.md).
**Price read.** Public pages fetched on 2026-11-20. List prices exclude tax. A second cloud's hourly rate is not a measured ClutchClips speed.

## Executive summary

One `s-4vcpu-8gb` droplet, billed at its public monthly cap, is the cheap part of a clip. The 2026-11-15 production run finished a 2 hour 18 second VOD in 932.7 seconds on that size. Applying the public hourly rate of that same size as if the box did nothing else puts compute at about USD 0.009 per source-video-hour. That figure is arithmetic on a historical timing, not a new benchmark.

SPEC setup B adds hosted transcription and a 16-vCPU CPU-optimized render worker. The worker's public monthly cap is USD 336, seven times the current droplet. Hosted transcription at the OpenAI Whisper list price is USD 0.36 per source-hour, about 39 times the dedicated-compute figure above. A GPU list price in the USD 0.80 to USD 1.01 per hour band is 11 to 14 times the current droplet's hourly rate. Render was 62.0 percent of that historical wall clock. Removing render time entirely, and leaving every other stage unchanged, would make the job 2.63 times faster. That is short of the speedup those GPU rates need in order to match today's compute dollars. GPU speed on this pipeline is `not measured`.

Placeholder subscription prices still collect about USD 0.47 to USD 1.08 per source-hour. Local transcription on the current droplet fits inside that. OpenAI Whisper list price plus an always-on 16-vCPU box does not fit the cheapest placeholder tier unless volume stays high. This file proposes that shape. It does not change a price.

## Where the knobs live

| Knob | What it limits | Label |
| --- | --- | --- |
| `Settings.worker_concurrency` | Jobs inside one worker process. Default 1. Values 0 and 3 fail validation. | `verified` `clip-api/app/config.py`, `clip-api/tests/test_worker_concurrency.py` |
| `serve` in `app/worker.py` | One thread per slot. Each slot claims with `FOR UPDATE SKIP LOCKED` and a conditional update, so a job has one owner. | `verified` |
| `WORKER_CONCURRENCY` times containers | DEPLOY.md states total in-flight jobs. A second container loads its own models. `deploy.sh` returns to one container. | `verified` `clip-api/DEPLOY.md` |
| `max_concurrent_jobs_per_account` | Default 2. One account cannot occupy more slots than this even if the worker allows them. | `verified` `clip-api/app/config.py` |
| `transcribe_parallel` | Chunks of one whole-recording transcription. Default 1, maximum 8. Independent of job slots. | `verified` `clip-api/app/config.py` |
| `daily_minutes_cap` | 6000 source minutes per UTC day, which is 100 source-hours. | `verified` `clip-api/app/config.py` |
| `retention_days` | 7. Uploads and clips past that date are deleted by the worker sweep. | `verified` `clip-api/app/config.py`, `sweep_expired` in `app/worker.py` |

`run_pipeline` renders best-first and calls `on_clip` when each clip file exists. The worker's `save_clip` stores that file and inserts the clip row while the job is still `RUNNING`. `preview` on the render options defaults to false, and `run_pipeline` does not pass it, so the clip stored today is the full encode, preset `veryfast`, CRF 20, short side capped by the plan's `max_side`. The 540-pixel preview encode exists in `render.py` and is not what that path stores. `verified`.

## Worker concurrency on the current box

SPEC phase 0.4 sets the default at 1 and the maximum at 2 on `s-4vcpu-8gb`. `verified` SPEC.md section 13. The settings field uses the same cap for every machine. A 16-vCPU host does not get a higher cap without a code change. `verified` `config.py` comment and `le=2`.

DEPLOY.md states why the cap is 2 on the 4-vCPU, 8 GB droplet. ffmpeg and Whisper already use every core, so two jobs each run slower, and the gain is that the second customer does not wait for the first job to finish. The two slots share one copy of the Whisper and CLIP models. The amount of slowdown is `not measured` in this research. The written claim is `verified` in `clip-api/DEPLOY.md`.

Claiming is safe at two slots. The test starts eight claimers against two queued jobs and expects each job once. `verified` `tests/test_worker_concurrency.py`. Credits still settle once per job, including a refund when the job does not succeed. `verified` `process_job`.

## SPEC setup B

SPEC section 14 names setup B as the current droplet for the API, the database, and analysis, plus hosted transcription behind config, plus one 16-vCPU CPU-optimized render worker. The owner provisions and pays. An agent does not sign up or deploy. Hosted transcription sends audio to a third party, so the Terms and Privacy pages have to say so. `verified` SPEC.md.

The code does not match that split yet. `transcription_provider` defaults to `local`. `verified` `clip-api/app/config.py`. One worker process runs download, transcription, render, and storage. `verified` `process_job`. Ticket S4 is the render-machine role split, and S5 is the GPU benchmark. Neither was run here. `verified` SPEC.md section 14 ticket list. Speed on a 16-vCPU worker is `not measured`.

## Public storage prices, read 2026-11-20

### DigitalOcean Spaces

Source. [Spaces pricing](https://docs.digitalocean.com/products/spaces/details/pricing/), fetched 2026-11-20. `public-source`.

| Item | Price |
| --- | --- |
| Standard subscription | USD 5.00 per month, from the first bucket until every bucket is destroyed. Prorated hourly if the subscription ends. |
| Storage included | 250 GiB across buckets |
| Extra standard storage | USD 0.02 per GiB-month |
| Outbound included | 1,024 GiB, shared, covering CDN and origin |
| Extra outbound | USD 0.01 per GiB |
| Inbound | Does not count against the allowance |
| CDN | No separate fee. Origin-to-edge transfer counts toward the same 1,024 GiB. |
| Cold storage | USD 0.007 per GiB-month, retrieval USD 0.01 per GiB, 30-day minimum with an early-delete charge |
| Requests | No per-request price on this page |

Same-region droplet traffic is free for the region groups listed on that page, including TOR1 to a TOR1 Space. The production benchmark droplet is in Toronto. `verified` SPEC.md section 10 B. Private VPC DNS routing, where configured, also stays off the Spaces outbound allowance. Traffic from a droplet to Spaces still counts against the droplet's own outbound allowance.

DEPLOY.md recorded the same USD 5, 250 GiB, USD 0.02, and USD 0.01 figures on 2026-11-15. `verified` `clip-api/DEPLOY.md`. This read matches that note and adds cold storage, which the DEPLOY note does not price.

### Amazon S3 and Cloudflare R2

The fetch of [aws.amazon.com/s3/pricing](https://aws.amazon.com/s3/pricing/) on 2026-11-20 confirms that the first 100 GB per month of internet data transfer out is free across AWS services, that bytes in from the internet are free, and that AWS uses a binary gigabyte, 2^30 bytes. The regional Standard storage table was not in the extracted page text.

The Standard rates below are from a secondary page that quotes the AWS Price List API for US East, N. Virginia, publication timestamp 2026-11-18T16:18:49Z. [DevZero, AWS S3 pricing](https://www.devzero.io/blog/aws-s3-pricing), read 2026-11-20. `public-source`. Treat them as that API snapshot, not as a number copied from the AWS marketing table in this session.

| Item | us-east-1 figure on that read |
| --- | --- |
| S3 Standard storage | USD 0.023 per GB-month for the first 50 TB |
| PUT, COPY, POST, LIST | USD 0.005 per 1,000 |
| GET and other | USD 0.0004 per 1,000, written there as USD 0.004 per 10,000 |
| Internet data transfer out after 100 GB | USD 0.09 per GB for the next 10 TB, from [Upstash's 2026 S3 writeup](https://upstash.com/blog/aws-s3-pricing-explained-2026), also read 2026-11-20. `public-source`. |

R2, from [Cloudflare's R2 pricing](https://developers.cloudflare.com/r2/pricing/), fetched 2026-11-20. `public-source`.

| Item | Price |
| --- | --- |
| Standard storage | USD 0.015 per GB-month |
| Egress to the internet | USD 0 |
| Class A, including PutObject | USD 4.50 per million |
| Class B, including GetObject | USD 0.36 per million |
| Free tier, Standard only | 10 GB-month, 1 million Class A, 10 million Class B |
| Rounding | Usage rounds up to the next billing unit. 1.1 GB-month bills as 2 GB-month. |
| Infrequent Access | USD 0.01 per GB-month, 30-day minimum, no free tier |

`app/storage.py` already speaks S3 for Spaces or R2. `verified`. Choosing R2 is an owner decision. This research does not switch the backend.

### What a kept source file costs

The benchmark file is 2,848 MB, which is 2.781 GiB. `measured` SPEC.md, file size only. Retention is 7 days, so a byte held for the full window is 7/30 of a GB-month. `inferred` from `retention_days`.

2.781 GiB times 7/30 is 0.649 GiB-month. `inferred`.

| Store | Storage for that one object, if it sits past any included pool | Label |
| --- | --- | --- |
| Spaces extra GiB | 0.649 times USD 0.02 = USD 0.013. Inside the 250 GiB pool the marginal storage is USD 0 and the USD 5 subscription still applies. | `inferred` |
| S3 Standard at USD 0.023 | USD 0.015 | `inferred` |
| R2 at USD 0.015, before rounding | USD 0.010. Past the free 10 GB-month, rounding up can bill a full extra GB-month. | `inferred` |

Clip output sizes for that run are `not measured`. The source object dominates any guess that uses only this file size.

Spaces cold storage and R2 Infrequent Access both want 30 days. Clip retention is 7 days, and a failed job deletes objects immediately. Those classes bill the leftover minimum. Keep clips on standard storage. `inferred` from the public minimums and `retention_days`.

## Dollars per source-video-hour

### The only pipeline timing used

SPEC section 10 B, server run on 2026-11-15, DigitalOcean `s-4vcpu-8gb`, Toronto, production image, Whisper `small.en` and `base.en`. Input `GTA_Benchmark_2Hours.mkv`, duration 2:00:18, 10 clips, wall 932.7 s, realtime factor 7.7 times, transcribing 257.0 s, rendering 578.4 s, 121 credits. `measured` on that date, cited from SPEC.md. This research did not rerun it.

Check on those inputs. 2:00:18 is 7,218 seconds, which is 2.005 source-hours. 7,218 / 60 is 120.3 minutes, and the credit rule rounds up to 121. 7,218 / 932.7 is 7.74, which SPEC rounds to 7.7. Rendering is 578.4 / 932.7 = 62.0 percent. Transcribing is 257.0 / 932.7 = 27.6 percent. `inferred` arithmetic on `measured` inputs. Run A's stage list adds up to its wall clock, so these stage seconds are sequential, not overlapped. `verified` SPEC.md run A note, applied to the same table.

Apple Silicon timings in the same section do not transfer to this droplet. `verified` SPEC.md. They are not used below.

### Compute list prices, read 2026-11-20

DigitalOcean bundled droplets, [pricing page](https://www.digitalocean.com/pricing/droplets), fetched 2026-11-20. Per-second billing, 60-second minimum, monthly cap at the bundled price. `public-source`.

| Plan | Role in this note | USD per hour | USD per month cap | Disk and transfer |
| --- | --- | --- | --- | --- |
| Basic, 8 GiB, 4 vCPU | The size named `s-4vcpu-8gb` in SPEC. The page lists the row, not the slug. | 0.07143 | 48 | 160 GiB SSD, 5,000 GiB |
| CPU-Optimized, 32 GiB, 16 vCPU | The setup B render worker shape. Slug `c-16` is the usual name for this row. The pricing page lists the specs, not the slug. | 0.50000 | 336 | 200 GiB SSD, 7,000 GiB |

672 hours times USD 0.07143 is USD 48.00. 672 hours times USD 0.50 is USD 336. The caps match the hourly rates. `inferred`.

AWS on-demand, us-east-1, Linux, two aggregators read on 2026-11-20 that agree. [Vantage c7i.4xlarge](https://instances.vantage.sh/aws/ec2/c7i.4xlarge), [Vantage g6.xlarge](https://instances.vantage.sh/aws/ec2/g6.xlarge), [Vantage g5.xlarge](https://instances.vantage.sh/aws/ec2/g5.xlarge), and the DoiT pages for the same three names. These are not the AWS console. `public-source`.

| Instance | vCPU and memory | GPU | USD per hour on demand |
| --- | --- | --- | --- |
| c7i.4xlarge | 16 vCPU, 32 GiB | none | 0.714 |
| g6.xlarge | 4 vCPU, 16 GiB | 1 NVIDIA L4 | 0.8048 on DoiT. Vantage rounds the same listing to 0.805. |
| g5.xlarge | 4 vCPU, 16 GiB | 1 NVIDIA A10G | 1.006 |

Runpod, [pricing page](https://www.runpod.io/pricing), fetched 2026-11-20, page says updated 12 November 2026. The RTX 4090 card shown is 24 GB VRAM, 41 GB RAM, 6 vCPUs, USD 0.89 per hour. The same page's summary line says RTX 4090 from USD 0.34 per hour. The worked rows use USD 0.89, the named card. USD 0.34 is a floor, not that card. `public-source`.

No ClutchClips job was run on c7i, g5, g6, or Runpod. Throughput there is `not measured`.

### Dedicated-machine cost of the historical job

Formula. Machine hours times the public hourly rate, divided by source hours. This charges the whole instance to one job for 932.7 seconds. On an always-on droplet the job's marginal compute is near zero until the box is full. Both readings are below.

| Reading | USD | How | Label |
| --- | --- | --- | --- |
| Run B machine time at USD 0.07143 per hour | 0.0185 for the job | 932.7 / 3600 times 0.07143 | `inferred` |
| Per source-hour, same assumption | 0.0092 | 0.0185 / 2.005 | `inferred` |
| Per credit, 121 credits | 0.00015 | 0.0185 / 121 | `inferred` |
| Always-on droplet, full month, one job at a time at this speed | 0.0086 per source-hour | USD 48 divided by the source-hours that fit in 672 hours at 7.74 times realtime. 672 times 7.74 / 1 is about 5,200 source-hours. 48 / 5200 is 0.009, same band. | `inferred` |

The limiter on the USD 0.009 figure is the 2026-11-15 wall clock, not a new profile. It includes transcribe, render, and the smaller stages. It excludes Spaces, a second machine, hosted transcription, Stripe fees, and idle time. A queue that leaves the droplet idle makes the per-job figure lower and the per-month figure stay at the cap. Why the number is not half. Render is 62 percent of the wall and is already inside the 932.7 seconds. Cutting a stage that is outside this sum cannot halve it.

### Break-even against that same job

Hourly multiple is the other machine's hourly price divided by USD 0.07143. Break-even wall clock is 932.7 seconds divided by that multiple. Faster than that wall clock, the other machine costs fewer compute dollars for this job. Slower, it costs more. Speed is `not measured` except on the original droplet.

| Machine | USD per hour | Multiple of the droplet | Wall clock that matches USD 0.0185 | Realtime factor at that wall clock |
| --- | --- | --- | --- | --- |
| DO CPU-Optimized 16 vCPU | 0.50 | 7.00 | 133 s | 54 times |
| Runpod RTX 4090 card at 0.89 | 0.89 | 12.5 | 75 s | 96 times |
| AWS g6.xlarge | 0.8048 | 11.3 | 83 s | 87 times |
| AWS g5.xlarge | 1.006 | 14.1 | 66 s | 109 times |
| AWS c7i.4xlarge | 0.714 | 10.0 | 93 s | 77 times |

`inferred` from `public-source` rates and the `measured` 932.7 s. The realtime column is 7,218 divided by the break-even wall clock.

If the render stage moved to the 16-vCPU box and still took 578.4 seconds, render compute would be USD 0.080. The other 354.3 seconds left on the droplet would be USD 0.007. The job would be USD 0.087, about 4.7 times the USD 0.0185 all-on-the-droplet figure, with no latency win. `inferred`. The 16-vCPU box earns its rate only by finishing much faster, or by draining a queue the small box cannot. That speed is `not measured`.

### GPU versus the stage split

If render time fell to zero and transcribe plus the other stages stayed at 354.3 seconds, the job would be 2.63 times faster, realtime about 20 times, still 5.9 minutes for this 2-hour file. `inferred` from the measured split. North-star for a 2-hour VOD is 10 minutes, stretch 5. `verified` SPEC.md section 14. A GPU that only accelerates encode does not, on this arithmetic, pay for an 11 times higher hourly rate, and it also does not by itself reach a 5-minute job while 354 seconds of non-render work remain.

That zero-render case is a bound, not a prediction. NVENC and NVDEC speed are `not measured`. S5 is the measurement that can move this row. Vantage prints an ffmpeg frames-per-second field on each instance page. That field is not a ClutchClips encode and is not used here.

### Hosted transcription prices, read 2026-11-20

Setup B names hosted transcription and does not name the vendor. `verified` SPEC.md. These are list prices a later choice would pay. They are not a selected provider.

| Vendor and model | USD per audio minute | USD per source-hour | USD for the 120.3 minute benchmark file | Source |
| --- | --- | --- | --- | --- |
| OpenAI Whisper | 0.006 | 0.36 | 0.72 | [OpenAI pricing](https://developers.openai.com/api/docs/pricing), fetched 2026-11-20. `public-source` |
| OpenAI gpt-4o-mini-transcribe | 0.003, marked on the page as an estimated cost | 0.18 | 0.36 | Same page. `public-source` |
| Deepgram Nova-3 monolingual, pre-recorded, pay as you go | 0.0043 | 0.258 | 0.52 | [Deepgram pricing](https://deepgram.com/pricing), fetched 2026-11-20. `public-source` |

Local Whisper on the droplet is inside the USD 0.0185 job figure. Replacing it with OpenAI Whisper at list price multiplies transcription from a share of USD 0.0185 to USD 0.72 for the same file. `inferred`. The Terms and Privacy requirement in SPEC still applies if that switch is made.

## Concurrency and cost

One worker at the measured 7.74 times realtime can finish the global cap of 100 source-hours in about 12.9 wall-clock hours. `inferred` from `daily_minutes_cap` and run B. The cap, not the hourly price, is what stops a single droplet from taking an unbounded day. Two accounts at the per-account cap of 2 can fill the two worker slots. Further accounts wait. `verified` for the caps, `inferred` for the queue.

`WORKER_CONCURRENCY=2` on this droplet does not buy a second machine's throughput. DEPLOY.md says each job already uses every core. The second slot spends the same USD 48 monthly cap to shorten queue time for the second job. Wall clock per job is expected to rise. The new wall clock is `not measured`.

A second container on a larger host is the path DEPLOY.md allows. Each container has its own models and its own memory. Total slots are still 2 times the container count until the `le=2` field changes. Putting four containers on the 16-vCPU box to get eight slots would also multiply RAM for Whisper. Memory of that layout is `not measured`. The setup B design, analysis on the small droplet and render on the 16-vCPU box, needs the S4 role split. Until then, a second container runs the whole pipeline, including transcription, on the expensive box.

`TRANSCRIBE_PARALLEL` above 1 is for a machine with 8 or more cores, compared with `scripts/job_timings.py`. `verified` DEPLOY.md. It is the wrong dial for the 4-vCPU droplet.

## Progressive delivery cost

SPEC asks for clips to show up as they finish, and for 540 by 960 previews before a 1080p export. `verified` SPEC.md section 14. The first half is what the worker does. The second half is not the default render.

`save_clip` writes up to three objects per clip, the mp4, a jpg, and a captions JSON, then commits the row. The first successful store records `first_clip_sec`. `verified` `app/worker.py`. On any status other than `SUCCEEDED`, the worker deletes those keys, marks the clip rows deleted, and settles the ledger with success false, which refunds the reservation. `verified`.

Cost of publishing early, when the job then succeeds.

| Effect | Cost | Label |
| --- | --- | --- |
| Same objects as an upload at the end | No extra bytes from the early publish itself | `inferred` |
| Spaces request fees | None on the pricing page | `public-source` |
| S3 PUT fees for 50 clips, 3 objects each, 150 PUTs | 150 / 1000 times USD 0.005 = USD 0.00075 | `inferred` |
| R2 Class A for those 150 PUTs | Inside the 1 million monthly free tier. Past it, 150 / 1,000,000 times USD 4.50 is USD 0.0007 | `inferred` |
| A viewer who watches each file once | Same egress as watching after the job, only sooner. Spaces outbound is USD 0.01 per GiB after 1,024 GiB. R2 egress is USD 0. | `public-source` rates, byte counts `not measured` |

Cost of publishing early, when the job then fails or is canceled. The encode already happened. The refund returns the credit. The delete avoids a storage bill on Spaces standard and on S3 Standard, because those pages do not price standard deletes. The machine time is spent with no revenue. How large that share is depends on cancel rate, which is `not measured`.

A second file, the 540-pixel preview plus a later 1080p export, is the SPEC design and not the current `run_pipeline` call. `verified` that preview defaults to false. Doing both would add a second encode and a second object for every clip the user exports. Byte ratio and the extra render seconds are `not measured`. Preview encode settings are preset `ultrafast`, CRF 30, audio 96k, short side 540. Full encode is preset `veryfast`, CRF 20, audio 160k. `verified` `clip-api/app/pipeline/render.py`. Free plan `max_side` is 720. Paid plans in the placeholder table use 1080. `verified` `clip-api/app/plans.py`.

## Tier sustainability, proposal only

Placeholder prices, `verified` in code, and SPEC.md says to replace them after measuring cost per source minute. This section does not replace them.

One credit is one source minute, rounded up. `verified` SPEC.md. A source-hour is 60 credits. Revenue per source-hour below is price divided by credits, times 60. Yearly rows assume one `invoice.paid` grants 12 times the monthly credit count, which is what SPEC section 4 describes. `verified` SPEC.md for the grant rule, `inferred` for the division.

| Offer | Price | Credits granted for that price | USD per credit | USD per source-hour |
| --- | --- | --- | --- | --- |
| Starter month | USD 9 | 500 | 0.018 | 1.08 |
| Pro month | USD 19 | 1,200 | 0.0158 | 0.95 |
| Scale month | USD 79 | 8,000 | 0.0099 | 0.59 |
| Starter year | USD 84 | 6,000 | 0.014 | 0.84 |
| Pro year | USD 180 | 14,400 | 0.0125 | 0.75 |
| Scale year | USD 756 | 96,000 | 0.0079 | 0.47 |
| Pack 300 | USD 4.99 | 300 | 0.0166 | 1.00 |
| Pack 1,000 | USD 12.99 | 1,000 | 0.0130 | 0.78 |
| Pack 5,000 | USD 49.99 | 5,000 | 0.0100 | 0.60 |
| Signup grant | USD 0 | 30 once | 0 | 0 |

`verified` amounts in `clip-api/app/plans.py` and `DEFAULT_PACKS` in `clip-api/app/config.py`. The per-credit and per-source-hour columns are `inferred`.

Three operating shapes, compared with those collections. Stripe fees are not in this table. They were not fetched.

| Shape | Variable cost per source-hour | Fixed list cost per month | Fits the cheapest paid collection, USD 0.47 per source-hour on yearly Scale |
| --- | --- | --- | --- |
| Today. Local Whisper, one always-on `s-4vcpu-8gb`, disk on the droplet. | About USD 0.009 if the box stays busy. Near USD 0 marginal if it has idle time. The USD 48 cap is fixed. | 48 | Yes, on compute. Storage stays inside the 160 GiB disk until the sweeper and the disk fill. `hypothesis` on the exact full-disk day, because clip sizes are `not measured`. |
| Setup B with the 16-vCPU worker turned on only while it renders, transcription still local. | Render seconds times USD 0.50 per hour, plus analysis seconds times USD 0.07143. Equal to today's wall clock, that sum was USD 0.087 for the benchmark job, USD 0.043 per source-hour. | 48, plus the render box only while it exists | Yes against USD 0.47, before fees, if the render box is not left on. A faster render box lowers this further. That speed is `not measured`. |
| Setup B with OpenAI Whisper at USD 0.36 per source-hour, and the 16-vCPU box left on all month. | 0.36 for audio, plus render compute | 48 + 336 = 384, plus Spaces USD 5 if a bucket exists, USD 389 | No at low volume. Yearly Scale collects USD 0.4725 per source-hour, so USD 0.1125 remains after Whisper. USD 336 / 0.1125 is 2,987 source-hours in a month, about 100 a day, before the droplet, Spaces, fees, refunds, and the signup grant. `inferred`. Monthly Scale collects USD 0.5925, leaves USD 0.2325, and covers USD 336 at 1,445 source-hours in a month, about 48 a day. `inferred`. |

Proposal, for the owner to accept or replace.

1. Leave transcription on `local` until a vendor price is chosen. At the OpenAI Whisper list price, transcription alone is most of the cheapest placeholder credit.
2. When the render worker exists, create it for a backlog and destroy it after. Per-second billing with the USD 336 cap is the public rule as of this read. An idle 16-vCPU box for a month costs more than the small droplet's compute for a year of busy time at the historical rate. 336 / 48 is 7 months of the small droplet. `inferred`.
3. Keep `WORKER_CONCURRENCY` at 1 until a paired benchmark shows the second slot's wall clock. Turn it to 2 when two accounts are waiting and the slower per-job time is acceptable. Do not raise the code cap of 2 on the 4-vCPU box.
4. Put objects on Spaces standard, or on R2 standard, in the droplet's region group. Do not use a 30-day cold class for 7-day clips.
5. Treat USD 0.009 per source-hour as the compute reference for local processing on this droplet, and treat hosted audio as a separate line that has to stay under the credit price. Measure clip byte sizes and cancel rate before changing packs. SPEC already requires that measurement, and a price change needs the owner's OK.

## What would change a decision

A new `scripts/job_timings.py` run on the 16-vCPU worker, or on one GPU instance, with the same 2-hour file and the same 10-clip settings. If that wall clock is under the break-even seconds in the table, the faster machine costs less compute per video-hour than the droplet. If it is over, it costs more, and the only remaining reason to buy it is queue time and the 10-minute target. One run is not enough if two repeats differ by more than the gap to that line. This research did not take that run, and it did not provision the machine.