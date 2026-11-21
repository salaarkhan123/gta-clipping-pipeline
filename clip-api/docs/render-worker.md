# Dedicated render worker (setup B / S4)

Ops note for an optional second machine that spends most of its CPU on clip encodes. Complements the short
section in `DEPLOY.md`. **Docs and a commented compose stub only** — no API behaviour change, and nothing here
provisions paid infrastructure.

Claim labels: `measured` · `verified` · `hypothesis` · `not measured` · `public-source`.

## Why split

On the production 4 vCPU droplet (2026-11-15, SPEC.md §10 B), a ~2 h VOD finished in 932.7 s with rendering
578.4 s (~62% of wall clock) — `measured`. Analysis (transcribe, signals, judge) and encode share the same
cores today, so a second customer waits or both jobs slow down.

SPEC section 14 **setup B** names:

- current droplet → API, database, analysis
- one 16-vCPU CPU-optimized host → render worker
- hosted transcription behind config (separate decision; Terms/Privacy if audio leaves the box)

The owner provisions and pays. An agent does not create droplets, GPUs, or cloud accounts.

## What exists today vs what S4 still needs

| Piece | Status |
|---|---|
| Shared queue, claim with `FOR UPDATE SKIP LOCKED` | `verified` — any number of worker containers |
| `WORKER_CONCURRENCY` (1–2) | `verified` — jobs per process |
| `RENDER_WORKERS` (1–8) | Wave B1 — parallel encodes inside one job; default 1 keeps serial behaviour |
| `WORKER_STAGES` / render-only role | **S4 / #98** — not shipped. Until then every worker runs the full pipeline |
| Shared object storage (Spaces / R2 / S3) | Required for two hosts; local `DATA_DIR` volume does not cross machines |

Until #98 lands, a "render worker" container is only a second whole-pipeline replica. That can still soak up
queue on a larger host the owner already runs, but it pays Whisper/CLIP memory on the expensive box.

## When to add the second machine

Add it when all of these are true (owner call):

1. `scripts/job_timings.py` on real jobs shows render as the dominant stage.
2. Raising `RENDER_WORKERS` on the small droplet thrashes CPU/RAM or makes analysis slower.
3. You accept the fixed cost of a second host (or you will create it only for a backlog and destroy it after —
   `hypothesis` that per-second billing makes that cheaper than leaving a 16-vCPU box idle; see research cost
   notes, `not measured` for ClutchClips utilization).

Stay on one droplet when queue depth and export SLOs are fine. Do **not** enable paid cloud GPUs from this
doc; GPU encode is S5 (#99) after an owner-approved benchmark.

## Env knobs

Set in `.env` on each host that runs `api` or `worker`. Recreate containers after edits (`docker compose up -d
…`); `restart` does not re-read `.env`.

### `WORKER_CONCURRENCY`

- Maps to `Settings.worker_concurrency` (`verified` `app/config.py`).
- Default `1`. Allowed `1` or `2`. Values outside that fail at start.
- One process, shared Whisper/CLIP load, that many jobs at once.
- On 4 vCPU / 8 GB: `2` shortens queue wait but each job is expected to run slower (`not measured` magnitude;
  written rationale in `DEPLOY.md`).
- Raising the code cap above 2 needs a bigger-host benchmark and a reviewed settings change.

### `RENDER_WORKERS`

- Maps to `Settings.render_workers` when Wave B1 is deployed.
- Default `1` (serial encodes, best-first hand-off unchanged).
- Range 1–8. Ops knob only; the worker overwrites any client-supplied value.
- Raise on a machine with spare cores after a before/after with `scripts/job_timings.py`.
- Independent of `WORKER_CONCURRENCY`: one job can encode several clips while another job is still analyzing.

### Capacity sketch

```
in-flight jobs  ≈  (worker containers) × WORKER_CONCURRENCY
encodes per job ≈  RENDER_WORKERS   # after B1; else 1
```

`max_concurrent_jobs_per_account` still caps one account regardless of free slots (`verified`).

## Hardware sizing (hypotheses, not measured)

List prices below are **public-source** DigitalOcean bundled droplet figures as read for research on
2026-11-20. They are not a quote and exclude tax. ClutchClips wall clock and memory on these shapes are
**not measured** until the owner runs timings on provisioned hardware.

| Shape | Intended role | Approx. list price | Hypothesis (label) |
|---|---|---|---|
| Basic 4 vCPU / 8 GiB | Always-on API + DB + analysis | ~$48 / month (~$0.07 / hour) | Keep as the small droplet. |
| CPU-Optimized 16 vCPU / 32 GiB | Setup B render worker | ~$336 / month (~$0.50 / hour) | Room for higher `RENDER_WORKERS` and/or multiple worker containers. Break-even vs leaving render on the small box needs a much faster wall clock (`hypothesis` / research arithmetic; **not measured**). |
| GPU host | S5 NVENC/NVDEC only | higher $/hour | Out of scope. Do not provision from this guide. |

Memory: each extra worker *container* loads its own models. Four containers on a 16-vCPU box for eight job
slots also multiply RAM for Whisper — layout memory is **not measured**. Prefer raising `RENDER_WORKERS`
inside one process before multiplying containers, then measure with `docker stats` and `job_timings.py`.

## Compose stub (default off)

`docker-compose.yml` ends with a **fully commented** `render-worker` service. Plain `docker compose up` does
not start it. To try a second whole-pipeline worker on a host the owner already has:

1. Configure shared storage (`STORAGE_BACKEND=s3` and the S3/R2/Spaces settings in `DEPLOY.md`) on both hosts.
2. Uncomment the stub (or copy it into an override file the owner maintains outside git).
3. Point `DATABASE_URL` at the same Postgres the API uses (VPN / private network; do not expose Postgres to the
   public internet).
4. Start only that service on the render host: `docker compose up -d render-worker` (after uncomment).
5. Leave `api`, `db`, and `caddy` on the small droplet. `deploy.sh` on the API host still restarts `api` and
   `worker` only; the render host needs its own pull/build (owner runbook).

After S4 (`WORKER_STAGES`) ships, set the render host to render stages only and keep analysis on the small
droplet. Until then, treat the stub as a scaled worker, not a role-split worker.

## Measuring

```bash
curl -s $API/v1/jobs/<job_id> -H "authorization: Bearer $KEY" > job.json
python scripts/job_timings.py job.json
python scripts/job_timings.py job.json --baseline before.json --md
```

Compare the same VOD and clip count with `RENDER_WORKERS=1` vs `2..N` on the candidate host. Do not claim a
speed-up in a PR without those numbers.

## Explicit non-goals

- Agents provisioning droplets, Spaces, GPUs, or hosted ASR accounts.
- Changing credit prices, plan limits, or public API contracts in this docs PR.
- Turning GPU encode on without an S5 benchmark and owner OK.
- Assuming the 16-vCPU box is faster until `job_timings.py` says so.
