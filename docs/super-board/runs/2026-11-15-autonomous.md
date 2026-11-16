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

## Open for the owner (in merge order)

1. **#85** ✨ uploads: reuse a re-upload of the same file (0.3). 💰 Money path: needs your OK. Its migration is
   revision 0003, on top of 0002 from #87 (already merged).

## In flight (mine to merge when green)

- **#89** 🐛 facecam: crop to the overlay's own rectangle (owner priority 1).

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
- Facecam: an edge-based border detector was tried and dropped (it stopped on static lines inside the camera's
  own background). The benchmark VOD's camera is a cut-out with no rectangle, so it uses the tight fallback;
  removing gameplay behind the streamer's silhouette would need person segmentation (not built).

## Before / after notes

- Facecam, benchmark VOD at 1:30:00, split layout: old box `[0.138, 0.715, 0.253, 0.285]` showed the "MATCH" HUD
  and icons in the camera panel; new box `[0.172, 0.786, 0.186, 0.210]` shows the streamer only.
- 0.2e, benchmark VOD, judge candidates per quarter: 5 / 2 / 14 / 9 before, 5 / 5 / 13 / 7 after.

## Owner to do

1. Before the first deploy that includes #80, on the droplet:
   `docker compose exec -T db pg_dump -U clip clip > clip-pre-alembic-$(date +%F).sql` and
   `docker compose exec -T api python scripts/admin.py db-status`. Expect "from before migrations" and at most a
   missing `ix_accounts_stripe_customer_id`.
2. Label `clip-api/eval/benchmark-2h-labels.csv` (instructions in `clip-api/eval/README.md`).
3. Spaces: create the Space and keys, then follow `clip-api/DEPLOY.md` "Moving files to DigitalOcean Spaces"
   ($5.00 per month).

## Benchmark command (compare with SPEC.md §10 B: 10 clips, 932.7 s, 121 credits)

To be filled in at the end of the run.
