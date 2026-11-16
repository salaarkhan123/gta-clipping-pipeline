# Quality eval set

Labelled moments of the 2-hour benchmark VOD (`GTA_Benchmark_2Hours.mkv`, upload `upl_48592031ec2640f0ba7bfc74`),
so a change to clip picking can be measured instead of judged by eye.

## Labelling (owner)

Open `benchmark-2h-labels.csv` in Numbers, Excel or Google Sheets. Each row is a candidate moment (start and end as
h:mm:ss). Jump to `start` in the VOD, watch to `end`, and fill in:

| Column | What to write |
|---|---|
| `label` | **3** would post as-is · **2** good (a trim away) · **1** weak · **0** nothing / junk (menu, loading, dead air) |
| `what_happens` | a few words ("plane into the bay", "police chase") |
| `notes` | optional: better start or end time, why it works |

Leave `source` alone (where the row came from: `top` = strongest overall, `q1`–`q4` = strongest in that quarter).

**Add rows** at the bottom for good moments the sheet missed: any `id`, your own start and end, a label, and
`source` = `owner`. These matter most: they are what the pipeline should have found.

Rows you leave unlabelled are ignored, so you can stop part-way and the score still works on what is done.

## Scoring a run

```bash
curl -s $API/v1/jobs/<job_id> -H "authorization: Bearer $KEY" > job.json
python scripts/eval_clips.py eval/benchmark-2h-labels.csv job.json
```

| Metric | Meaning |
|---|---|
| good rate | share of clips on a moment labelled 2 or 3 |
| mean label | average label of the clips that matched a row |
| great moments found | 3-rated moments that some clip landed on |
| unlabelled | clips on no labelled row (the sheet missed them: label them and re-run) |
| duplicate pairs | two clips on the same moment or less than 60 s apart |
| per quarter | clips in each quarter of the video |

## Regenerating the sheet

`python scripts/make_label_sheet.py <video> eval/benchmark-2h-labels.csv` (overwrites labels; only for a new video).
