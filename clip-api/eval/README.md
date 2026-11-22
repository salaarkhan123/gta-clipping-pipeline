# Quality eval set

Labelled moments of real streams, so a change to clip picking is measured instead of judged by eye. Every
selection PR (understanding track U1 to U5) reports precision@20, precision@40 and recall from here.

| File | What |
|---|---|
| `labels-v2.csv` | **eval set v2**: about 100 rated moments over 3 videos, one held out |
| `gi-gta-label-sheet.csv` | GI / AS-1 gaming highlight sheet (human columns empty until owner rates) |
| `gaming-rating.md` | AS-1 gaming AI quality components + ablation CLI |
| `labeller.html` | the local page for rating moments (open it in Chrome) |
| `runs/` | saved runs (moments, best first) that the sheet was filled from, and baselines to compare with |
| `benchmark-2h-labels.csv`, `wayin-zias-iceman.csv` | eval set v1 (below); still scored the same |

**AS-1 honesty.** `gi-gta-label-sheet.csv` ships with **0** complete human ratings. Do not invent NDCG or a
virality %. Census: `python scripts/gaming_rating_eval.py sheet-stats eval/gi-gta-label-sheet.csv`.

## The three videos

| Id | Game | Video | Held out |
|---|---|---|---|
| `gta-online-1` | `gta-online` | the 2-hour benchmark, `GTA_Benchmark_2Hours.mkv` (deathmatches, flying, street chaos) | no |
| `gta-rp-1` | `gta-rp` | **owner to supply** | **yes** |
| `<game>-1`, e.g. `valorant-1` | e.g. `valorant` | **owner to supply** | no |

**The held-out video.** Nobody tunes thresholds, prompts, weights or anything else against `gta-rp-1`. PRs report
its numbers, but the people and agents changing the picker do not look at which of its clips hit or missed:
`eval_clips.py` prints only its totals unless `--show-held-out` is given, and that flag is for the final check of a
change, not for tuning. A comparison against another tool on it (below) is reported too, and is not used to tune
either. It is the GTA RP video because no tuning has seen it yet and RP is the core audience. The benchmark video
cannot be held out: earlier work was measured on it.

## Owner: what to do (about 1.5 hours, most of it watching)

The sheet gets moments from two places: our picker's best 30 per video (you rate them), and the moments you find
yourself by skimming the rest of the video (step 5). Step 5 is the only check on what our picker misses, so do not
skip it.

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

Never put videos in the repo. An agent can do steps 3 and 6 for you once the files are there.

### 3. Fill the sheet with moments to rate (2 minutes, can be done by an agent)

Run in `clip-api/`. `select` runs our moment picker on the file (no AI, no rendering, nothing uploaded, seconds)
and `add` puts its 30 best moments in the sheet as rows to rate:

```bash
python scripts/label_moments.py select ~/ClutchClips-eval/gta-rp-1.mp4 eval/runs/gta-rp-1.staging.json
python scripts/label_moments.py add eval/labels-v2.csv --vod gta-rp-1 --game gta-rp --held-out yes \
    --job eval/runs/gta-rp-1.staging.json
python scripts/label_moments.py select ~/ClutchClips-eval/valorant-1.mp4 eval/runs/valorant-1.staging.json
python scripts/label_moments.py add eval/labels-v2.csv --vod valorant-1 --game valorant --held-out no \
    --job eval/runs/valorant-1.staging.json
```

`gta-online-1` is already in the sheet (30 rows).

### 4. Rate the moments (about 20 minutes per video)

1. Open `clip-api/eval/labeller.html` in Chrome.
2. **Open sheet**: `clip-api/eval/labels-v2.csv`. **Open video**: the matching file from `~/ClutchClips-eval/`
   (named after its id, it selects its rows by itself).
3. Rows are listed in time order. The page does not say where a row came from: judge the moment, not the source.
   Each row plays from its start and pauses at its end. Rate it with a key, and it moves to the next row:

   | Key | Rating | Means |
   |---|---|---|
   | `3` | great | you would post it as it is. Type a few words on why ("cop chase ends in the river"), then Enter |
   | `2` | good | worth posting after a trim |
   | `1` | weak | not a clip: weak, junk, menus, dead air |

   Watch at 1.5x (`.` and `,` change speed). If the moment starts or ends in the wrong place, stop there and press
   `[` or `]` to move the row's start or end to the playhead. A row you are unsure about: rate it 2.

### 5. Hunt for the moments our picker missed (10 minutes per video, do not skip)

This is what measures recall: a great moment nobody offered you is invisible to every score unless you add it here.

1. Look at the bar under the video. The coloured blocks are the rows you just rated; **the gaps are the parts our
   picker passed over.**
2. Click into a gap and skip through it with `Shift` + `→` (30 s at a time). Listen for shouting, laughter, a
   crash, a fight, a sudden silence.
3. For a moment worth posting: `I` at its start, `O` at its end, `N` to add it. Rate it like the others (a 3 needs
   a reason). `Delete` removes a moment you added by mistake.
4. Aim for at least 3 added moments per video, more if the stream is busy. Finding none in 10 minutes is a result
   too: carry on to the next video.

### 6. Save, check and hand back (2 minutes)

**Save** (`Cmd+S`) writes straight back to the sheet. If Chrome asks, allow it to edit the file. If it downloads a
copy instead, move that over `clip-api/eval/labels-v2.csv`. Unsaved ratings survive a closed tab in the same
browser. If a video does not play, remux it (fast, no quality loss): `ffmpeg -i in.mkv -c copy out.mp4`.

```bash
python scripts/eval_clips.py eval/labels-v2.csv
```

It lists each video's progress and any row it cannot accept, with its line number. Aim for at least 30 rated rows and
5 or more 3s per video. Commit the sheet in a PR (or hand it to an agent).

### Time

| Step | Per video | All three |
|---|---|---|
| Rate our 30 moments of about 45 s at 1.5x, with reasons for the 3s | 15 to 20 min | 55 min |
| Hunt the gaps for missed moments | 10 min | 30 min |
| Pick the videos, run the commands, check | | 10 min |
| **Total** | | **about 1.5 hours** |

## Scoring a run (PRs)

Make a run per video (`label_moments.py select`, or a real job's JSON), then:

```bash
python scripts/eval_clips.py eval/labels-v2.csv gta-online-1=run-online.json gta-rp-1=run-rp.json valorant-1=run-val.json
```

It prints one table: a line per `@k` for the tuning videos, the held-out video, all of them, then each video; after
it, each tuning video's clips (hit, miss, repeat or unrated) and the 3s nobody found. Put the `tuning` and
`held_out` lines from before and after the change in the PR. `--json` gives everything.

Among a run's k best clips (k = 20, 40), each clip is one of:

| Clip | Meaning |
|---|---|
| hit | on a moment rated 2 or 3 that no better-ranked clip of the run is on |
| miss | on a moment rated 1 |
| repeat | on a rated moment a better-ranked clip of the run is already on |
| unrated | on no rated moment. **Not a miss**: nobody has judged it yet |

| Number | Meaning |
|---|---|
| precision of rated | hits / (clips that landed on a rated moment) |
| range | hits / clips (unrated counted as misses) to (hits + unrated) / clips (unrated counted as hits) |
| unrated | how wide the range is: rate them before trusting a small difference (below) |
| fewer than k clips | when a run returned n < k clips: flagged, and the strict range over k (hits / k to (hits + unrated) / k) is printed next to the range over the n it returned |
| recall of 3s | share of the 3-rated moments some clip of the run is on (all of its clips) |

Precision is never printed as one number that counts unrated clips as bad. Pooled lines add up the counts over
videos, so each video weighs the same.

**Matching rule.** A clip is on the rated moment of its own video that it overlaps most, if the overlap is at least
10 s (a third of the clip, for clips under 30 s). On equal overlap the higher rating wins. A clip is on one moment at
most; unrated rows take no part. Ranking: the clips' `rank`, else `score`, else the order listed.

**When unrated is high.** A new picker finds moments nobody rated yet. Add them and rate them (blind, in the
labeller), then score both runs again: `label_moments.py add ... --job new-run.json` adds only moments the sheet does
not cover. Rating a moment is about the video, not about the run, so this is fine on the held-out video too.

**Sheet rules** (`eval_clips.py` refuses a sheet that breaks them): columns `id, vod, game, start, end, rating,
reason, held_out, source`; `vod` and `game` short ids (a-z, 0-9, dashes); times `h:mm:ss`; 5 to 300 s long;
`rating` 1, 2, 3 or empty (not rated yet); `reason` under 80 characters and required for a 3; `held_out` yes or no;
one `game` and one `held_out` per video; unique ids; two rated rows of one video may not overlap by more than half
(the same moment rated twice). `source` records which runs offered a row (`clutchclips:<run>#<rank>`, joined with
`+` when several did, `owner` for one you added); it stays in the CSV and the labeller never shows it.

## Later: head-to-head against Wayin (optional, not part of the steps above)

Once the engine is tuned, the same sheet can score Wayin's clips next to ours. This needs paid Wayin exports, so it
waits for the owner's go-ahead.

1. Run each of the three videos through Wayin's game clipping with its default settings. Download every clip into
   `~/ClutchClips-eval/wayin/<vod-id>/`, numbered in Wayin's order (`01_...mp4`, `02_...mp4`). If the names cannot
   carry the order, write a CSV with a header `filename,rank` (or `filename,score`) instead.
2. Place the clips in their source video by audio:

   ```bash
   python scripts/label_moments.py wayin ~/ClutchClips-eval/gta-rp-1.mp4 ~/ClutchClips-eval/wayin/gta-rp-1 \
       eval/runs/gta-rp-1.wayin.json            # add --ranks ranks.csv when the files are not numbered
   ```

   The start and the end of each clip are found separately (Wayin trims dead air, so one clip can be several
   pieces of the source); it prints each clip's source span and how confident each end is. Matches under 0.85
   confidence, ambiguous ones, or ends that do not make one moment are refused and listed, never guessed. Checked on
   real recordings: pieces cut from a 78-minute stream and re-encoded (one with 15 s cut out of the middle, one 6 dB
   louder) came back at their exact spans with confidence 0.97 to 1.00; a piece of another video was refused.
3. Add Wayin's moments the sheet does not cover yet, and rate them blind in the labeller like the rest (all of
   Wayin's clips are added, not just 30; ones that cover an existing row only add `wayin:...` to its `source`):

   ```bash
   python scripts/label_moments.py add eval/labels-v2.csv --vod gta-rp-1 --game gta-rp --held-out yes \
       --job eval/runs/gta-rp-1.wayin.json
   ```

4. Score both systems on the same sheet; the table puts ClutchClips and Wayin side by side per video and pooled:

   ```bash
   python scripts/eval_clips.py eval/labels-v2.csv gta-online-1=ours-online.json gta-online-1=eval/runs/gta-online-1.wayin.json ...
   ```

   The comparison on the held-out video is reported, and is not used to tune.

## Eval set v1

One video per sheet, labels 0 to 3, scored against one run:

```bash
python scripts/eval_clips.py eval/benchmark-2h-labels.csv run.json
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
| @20, @40 | hits, misses, repeats, unrated and the precision range, as in v2 |

v1 labels: **3** would post as-is · **2** good (a trim away) · **1** weak · **0** nothing / junk. Rows you leave
unlabelled are ignored. `python scripts/make_label_sheet.py <video> <out.csv>` writes a new v1 sheet.
