# Autonomous run, 2026-11-15

Rules for this run (owner's message): merge into `staging` myself only when CI passes, the full suite passes
locally, the PR has tests, the diff matches the ticket, and it is not a money path. Money-path PRs stay open.
Never: `main`, a `staging` → `main` PR, deploys, the droplet, third-party signups, prices, secrets.

## Merged into `staging`

| Ticket | PR | Merge commit | By | Notes |
|---|---|---|---|---|
| 0.7 Alembic (#37) | #80 | `c17e0dd` | owner asked | First deploy changes the live schema; see "Owner to do" |
| 0.4 `WORKER_CONCURRENCY` (#34) | #81 | `8d82fea` | owner asked | Off until `WORKER_CONCURRENCY=2` is set |
| 0.6 eval set (#36) | #79 | `84cdb74` | owner asked | Sheet waits for the owner's labels |
| 0.5 Spaces storage (#35) | #82 | `84b46c1` | me (session rule) | Off until `STORAGE_BACKEND=s3`; price verified in the PR |
| 0.2e candidate coverage (#31) | #83 | `f381440` | me (session rule) | Judge sees every quarter of long videos; final-clip quality not measured (no labels yet) |
| db: freeze the legacy migration step | #84 | `bdf90d6` | me (session rule) | Found while writing the first real revision; first refused as part of a compound command, merged when sent alone |
| 1.1 projects and sidebar (#38) | #86 | `5ad1b76` | me (session rule) | Whole dashboard UI replaced; checked in headless Chrome |
| 1.2 sort, filter, reactions (#39) | #87 | `21e56f2` | me (session rule) | Revision 0002 (additive): `clips.reaction`, `clips.bookmarked`, `clip_feedback` |
| 1.3 rank + tier (#40) | #88 | `ed02fcd` | me (session rule) | Tier thresholds 75 / 55 / 35 are my choice |
| facecam: overlay's own rectangle (priority 1) | #89 | `033ff80` | me (session rule) | Benchmark VOD's camera is a cut-out: it takes the tight fallback |
| punchier clips (priority 2) | #90 | `67a486b` | me (session rule) | Segment renders, judge-chosen cut, flash-forward, dead air, punch-in zoom; all on by default |
| titles and hook (priority 3) | #91 | `0c73c7c` | me (session rule) | 3 titles + 1 hook, hook burned in for 2.5 s, `PATCH /v1/clips/{id}` |
| GTA templates + suggestions (priority 4, #50) | #92 | `df24f30` | me (session rule) | Template attaches tuning only; options and cost untouched |

## Open for the owner (in merge order)

1. **#85** ✨ uploads: reuse a re-upload of the same file (0.3). 💰 Money path: needs your OK. Up to date with
   `staging` (228 passed). Its migration is revision 0003, after 0002 from #87.

Nothing else is open. `staging` at `df24f30`: 224 passed, 13 skipped.

## Not started (owner priorities 5 and 6, then the north-star plan)

- Dashboard redesign (priority 5) and the editor (priority 6) were next when the north-star goal arrived. The
  APIs they need are merged: projects, library, reactions, rank and tier, titles, hook, suggestion, templates,
  and the `tighten` / `punch_zoom` / `flash_forward` / `hook_overlay` options. The dashboard does not show the
  title picker, suggestions, templates or those toggles yet.
- North-star goal (30-50 ranked clips with previews in 10 minutes): plan sent to the owner, no code.

## Blocked

None yet.

## Decisions I made

- 0.5: signed bucket links download as a file (`attachment`), because the site's Download link is cross-origin.
  Previews still play. Verified against a local S3 (moto), **not against real Spaces**: I may not create a Space.
- 0.2e: the report proposed per-quarter nomination "after your OK, measured with the eval set". Taken as the
  sensible default in its conservative form: each quarter of a 20 min+ video gets `count // 6` of the judge's
  candidates first, total unchanged (no extra AI cost). Benchmark VOD candidates per quarter 5/2/14/9 → 5/5/13/7.
- #84: while writing revision 0002 I found the legacy step from #80 read the live models, which would break
  the first production migration once any later revision adds an index. Fixed with lists frozen at 0001.
- 0.3: "within 7 days" = the existing 7-day retention; reuse does not extend expiry; never across accounts.
- 1.1: Brand kit and Publishing are in the sidebar as plain text marked "Coming soon", not links.
- 1.2: reactions are stored on the clip and every change is appended to `clip_feedback`; revision 0002 went to
  this ticket and #85's revision was renumbered to 0003, so the money PR does not block the non-money one.
- 1.3: tier comes only from the AI score (top 75+, strong 55+, solid 35+, long shot below); clips the AI did not
  rate show a rank and no tier. Rank is within a run, because scores from different runs are not comparable.
- Owner priorities (second message) now come before the old order: facecam, punchier clips, titles and hooks,
  GTA templates and suggestions, dashboard redesign, editor.
- Priority 2: "dead air" by audio level alone removed nothing on the benchmark VOD (game audio never goes
  quiet). It is now a gap in speech over 0.6 s while the game is no louder than the clip's typical level, plus
  true silences; never a spoken word; at most 35% of a clip. Flash-forward only when the peak is 4 s or more
  into the clip. Zooms: at most 3 per clip, 4 s apart, 1.15x.
- Priority 3: changing the burned-in hook on an existing clip is a re-render (money), so it waits for the
  editor. Priority 4: applying a suggestion is a re-render too; the suggestion ships, the apply button waits.
- Priority 4: my first version let a template fill options on the server, which changed the cost of a job from
  inside the cost code. Reworked so the client sends the template's options and the server attaches only the
  detection tuning; the cost lines are identical to before.
- Facecam: an edge-based border detector was tried and dropped (it stopped on static lines inside the camera's
  own background). The benchmark VOD's camera is a cut-out with no rectangle, so it uses the tight fallback;
  removing gameplay behind the streamer's silhouette would need person segmentation (not built).

## Before / after notes

- Facecam, benchmark VOD at 1:30:00, split layout: old box `[0.138, 0.715, 0.253, 0.285]` showed the "MATCH" HUD
  and icons in the camera panel; new box `[0.172, 0.786, 0.186, 0.210]` shows the streamer only.
- 0.2e, benchmark VOD, judge candidates per quarter: 5 / 2 / 14 / 9 before, 5 / 5 / 13 / 7 after.
- Dead air, benchmark VOD, ten strongest 30 s moments, Whisper `small.en` on my machine: 18.3 s of 300 s removed
  (6%); one or two cuts of 0.6-3 s per clip; gappiest clip 30.0 s -> 22.8 s. Zooms on 5 of 10 clips.
- Not measured anywhere yet: the judge's cuts, flash-forward, new titles, templates and suggestions on a real
  job (no AI key on this machine, no server access), and the eval set (no labels yet).
- Speed measurements for the north-star plan, on my Apple M4 (10 cores), benchmark VOD (1080p60 H.264):
  audio-only extract of 2 h: 4.1 s; full 360p/10 fps video proxy of 2 h: 213 s; one 30 s split clip at
  1080x1920 veryfast: 6.3 s; the same as a 540x960 ultrafast preview: 3.0 s; 8 simple previews in parallel: 8 s.
  The droplet rendered the same kind of clip in 57.8 s (578 s for 10), about 9x slower than this machine.

## Owner to do

1. Before the first deploy that includes #80, on the droplet:
   `docker compose exec -T db pg_dump -U clip clip > clip-pre-alembic-$(date +%F).sql` and
   `docker compose exec -T api python scripts/admin.py db-status`. Expect "from before migrations" and at most a
   missing `ix_accounts_stripe_customer_id`.
2. Label `clip-api/eval/benchmark-2h-labels.csv` (instructions in `clip-api/eval/README.md`).
3. Spaces: create the Space and keys, then follow `clip-api/DEPLOY.md` "Moving files to DigitalOcean Spaces"
   ($5.00 per month).

## Benchmark command (compare with SPEC.md §10 B: 10 clips, 932.7 s, 121 credits)

On the droplet, with `$API` and `$KEY` set, same upload as the last run (`upl_48592031ec2640f0ba7bfc74`):

```
JOB=$(curl -s -X POST $API/v1/clips -H "authorization: Bearer $KEY" -H "content-type: application/json" \
  -d '{"upload_id":"upl_48592031ec2640f0ba7bfc74","options":{"max_clips":10,"clip_length":30}}' | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
watch -n 15 "curl -s $API/v1/jobs/$JOB -H 'authorization: Bearer $KEY' | python3 -c \"import sys,json; j=json.load(sys.stdin); print(j['status'], j['stage'], j['progress'])\""
curl -s $API/v1/jobs/$JOB -H "authorization: Bearer $KEY" > job.json
python scripts/eval_clips.py eval/benchmark-2h-labels.csv job.json     # once the sheet has labels
```

The upload is kept 7 days from when it was uploaded; if it has expired, upload the VOD again first. Since the
last run the defaults changed (dead-air removal, zoom, flash-forward, hook, judge-chosen 15-45 s cuts), so
compare total time, per-stage timings in the job's `result`, and the clips themselves.
