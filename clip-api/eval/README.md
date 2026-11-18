# Quality eval set

Labelled moments of real streams, so a change to clip picking is measured instead of judged by eye. Every
selection PR (understanding track U1 to U5) reports precision@20, precision@40 and recall from here.

| File | What |
|---|---|
| `labels-v2.csv` | **eval set v2**: about 100 rated moments over 3 videos, one held out |
| `labeller.html` | the local page for rating moments (open it in Chrome) |
| `runs/` | saved runs (moments, best first) that the sheet was filled from, and baselines to compare with |
| `benchmark-2h-labels.csv`, `wayin-zias-iceman.csv` | eval set v1 (below); still scored the same |

## The three videos

| Id | Game | Video | Held out |
|---|---|---|---|
| `gta-online-1` | `gta-online` | the 2-hour benchmark, `GTA_Benchmark_2Hours.mkv` (deathmatches, flying, street chaos) | no |
| `gta-rp-1` | `gta-rp` | **owner to supply** | **yes** |
| `<game>-1`, e.g. `valorant-1` | e.g. `valorant` | **owner to supply** | no |

The held-out video is never tuned against: PRs report its numbers, but the people and agents changing the picker
do not look at which of its clips hit or missed (`eval_clips.py` hides them unless `--show-held-out`). It is the
GTA RP video because no tuning has seen it yet and RP is the core audience. The benchmark video cannot be held out:
earlier work was measured on it.

## Owner: what to do (about 1.5 hours, most of it watching)

### 1. Pick two videos (10 minutes)

Use streams you own or have permission to clip. Public, non-DRM only.

| | GTA RP video | Other-game video |
|---|---|---|
| Game | GTA V roleplay on an RP server | one popular non-GTA game with voice: Valorant, CS2, Fortnite or Apex |
| Length | 1.5 to 3 hours (2 is ideal: the north-star target) | 1.5 to 2.5 hours |
| Must have | a facecam, the streamer talking, a few chases, fights or funny scenes | a facecam, voice comms, some clutches or wipes |
| Avoid | a stream we already ran (the benchmark, the Zias video) | another GTA mode; a mostly menu or lobby stream |
| File | MP4 or MKV, H.264, 720p or 1080p | same |

### 2. Put the files in one folder outside the repo

```
~/ClutchClips-eval/
  gta-online-1.mkv   (copy or link of GTA_Benchmark_2Hours.mkv)
  gta-rp-1.mp4
  valorant-1.mp4     (name it after its game)
```

Never put videos in the repo. An agent can do steps 3 and 5 for you once the files are there.

### 3. Fill the sheet with moments to rate (2 minutes, can be done by an agent)

Run in `clip-api/` for each new video. `select` runs our moment picker on the file (no AI, no rendering, nothing
uploaded, under a minute) and `add` puts its 30 best moments in the sheet as rows to rate:

```bash
python scripts/label_moments.py select ~/ClutchClips-eval/gta-rp-1.mp4 eval/runs/gta-rp-1.staging.json
python scripts/label_moments.py add eval/labels-v2.csv --vod gta-rp-1 --game gta-rp --held-out yes \
    --job eval/runs/gta-rp-1.staging.json
python scripts/label_moments.py select ~/ClutchClips-eval/valorant-1.mp4 eval/runs/valorant-1.staging.json
python scripts/label_moments.py add eval/labels-v2.csv --vod valorant-1 --game valorant --held-out no \
    --job eval/runs/valorant-1.staging.json
```

`gta-online-1` is already in the sheet (30 rows). Optional: if you also run a video as a normal ClutchClips job
(with the AI judge), save its result (`curl -s $API/v1/jobs/<job_id> -H "authorization: Bearer $KEY" > job.json`)
and `add --job job.json` it too. Only moments the sheet does not have yet are added.

### 4. Rate in the labeller (about 25 minutes per video)

1. Open `clip-api/eval/labeller.html` in Chrome.
2. **Open sheet**: `clip-api/eval/labels-v2.csv`. **Open video**: the matching file from `~/ClutchClips-eval/`
   (named after its id, it selects its rows by itself).
3. Each row plays from its start and pauses at its end. Rate it with a key, and it moves to the next row:

   | Key | Rating | Means |
   |---|---|---|
   | `3` | great | you would post it as it is. Type a few words on why ("cop chase ends in the river"), then Enter |
   | `2` | good | worth posting after a trim |
   | `1` | weak | not a clip: weak, junk, menus, dead air |

   Watch at 1.5x (`.` and `,` change speed). If the moment starts or ends in the wrong place, stop there and press
   `[` or `]` to move the row's start or end to the playhead. A row you are unsure about: rate it 2.
4. **Then hunt for missed moments, 10 minutes.** The bar under the video shows the rows; the gaps are what our picker
   did not offer. Skip through the gaps with `Shift` + `→` (30 s). For a moment worth posting: `I` at its start,
   `O` at its end, `N` to add it, then rate it. These rows count most: they are what the picker should have found.
5. **Save** (`Cmd+S`) writes straight back to the sheet. If Chrome asks, allow it to edit the file. If it downloads a
   copy instead, move that over `clip-api/eval/labels-v2.csv`. Unsaved ratings survive a closed tab in the same
   browser.

If a video does not play, remux it (fast, no quality loss): `ffmpeg -i in.mkv -c copy out.mp4`.

### 5. Check and hand back (2 minutes)

```bash
python scripts/eval_clips.py eval/labels-v2.csv
```

It lists each video's progress and any row it cannot accept, with its line number. Aim for at least 30 rated rows and
5 or more 3s per video. Commit the sheet in a PR (or hand it to an agent).

### Time

| Step | Per video | All three |
|---|---|---|
| Rate 30 moments of about 45 s at 1.5x, with reasons for the 3s | 15 to 20 min | 50 min |
| Hunt the gaps for missed moments | 10 min | 30 min |
| Pick the videos, run the commands, check | | 15 min |
| **Total** | | **about 1.5 hours** |

## Scoring a run (PRs)

Make a run per video (`label_moments.py select`, or a real job's JSON), then:

```bash
python scripts/eval_clips.py eval/labels-v2.csv gta-online-1=run-online.json gta-rp-1=run-rp.json valorant-1=run-val.json
```

The first lines look like this (example numbers), followed by one line per video and its clips:

```
tuning (2 vods): precision@20 45% · precision@40 30% · recall 70% (7 of 10 3s) · unrated@20 3 · unrated@40 9
held_out (1 vod): precision@20 40% · precision@40 28% · recall 60% (3 of 5 3s) · unrated@20 2 · unrated@40 6
```

Put the `tuning` and `held_out` lines from before and after the change in the PR. `--json` gives everything.

| Metric | Meaning |
|---|---|
| precision@k | hits among the run's k best clips, divided by k (so a run with fewer than k clips cannot score 100%) |
| hit | a clip on a moment rated 2 or 3, when no better-ranked clip of the run is on the same moment |
| recall | share of the 3-rated moments some clip of the run is on |
| unrated@k | clips among the k best on no rated moment: rate them before trusting the numbers (below) |
| pooled lines | hits and moments added up over the videos; each video weighs the same in precision@k |

**Matching rule.** A clip is on the rated moment of its own video that it overlaps most, if the overlap is at least
10 s (a third of the clip, for clips under 30 s). On equal overlap the higher rating wins. A clip is on one moment at
most; unrated rows take no part. Ranking: the clips' `rank`, else `score`, else the order listed.

**When unrated@k is high.** A new picker finds moments nobody rated yet. Add them and rate them, then score both runs
again: `label_moments.py add ... --job new-run.json` (only uncovered moments are added). Rating a moment is about the
video, not about the run, so this is fine on the held-out video too.

**Sheet rules** (`eval_clips.py` refuses a sheet that breaks them): columns `id, vod, game, start, end, rating,
reason, held_out, source`; `vod` and `game` short ids (a-z, 0-9, dashes); times `h:mm:ss`; 5 to 300 s long;
`rating` 1, 2, 3 or empty (not rated yet); `reason` under 80 characters and required for a 3; `held_out` yes or no;
one `game` and one `held_out` per video; unique ids; two rated rows of one video may not overlap by more than half
(the same moment rated twice).

## Eval set v1

One video per sheet, labels 0 to 3, scored against one job:

```bash
python scripts/eval_clips.py eval/benchmark-2h-labels.csv job.json
```

- `benchmark-2h-labels.csv`: 46 candidate moments of the benchmark video from the audio signal
  (`scripts/make_label_sheet.py`), never labelled. Its rows can seed v2 with `label_moments.py add --sheet`.
- `wayin-zias-iceman.csv`: the 15 moments a competitor picked on the Zias video, all counted as 3. Selection-only run
  on staging 347ca2f (`runs/zias-iceman.staging-347ca2f.json`): 7 of 15 found, the same 7 as the 2026-11-16 benchmark.

| Metric | Meaning |
|---|---|
| good rate | share of clips on a moment labelled 2 or 3 |
| mean label | average label of the clips that matched a row |
| great moments found | 3-rated moments that some clip landed on |
| unlabelled | clips on no labelled row (the sheet missed them: label them and re-run) |
| duplicate pairs | two clips on the same moment or less than 60 s apart |
| per quarter | clips in each quarter of the video |
| precision@20, @40 | as in v2 |

v1 labels: **3** would post as-is · **2** good (a trim away) · **1** weak · **0** nothing / junk. Rows you leave
unlabelled are ignored. `python scripts/make_label_sheet.py <video> <out.csv>` writes a new v1 sheet.
