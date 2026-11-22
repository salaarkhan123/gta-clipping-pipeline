# Engagement study and historical pilot

A short upload can draw views through distribution, an established audience or an eye-catching title. Audience retention, sharing after exposure and an editor's rating of the underlying play answer different questions. Keep them as separate outcomes. The present evidence supports **no production virality coefficient**.

## Observed retrospective sample

On 19–20 November 2026 we screened 668,552 complete records from a fixed 125,000,000-byte prefix of the **YouNiverse** English-language video metadata release. The 2019 archive predates YouTube Shorts. Records include lifetime views at crawl, upload/crawl dates, duration and category. We selected 8–90 s gaming uploads at least 30 days old with one recognizable game in the title or tags and excluded evident news, trailers and similar titles. This left 1,321 candidates. We matched high and low observed reach within channel, game family and upload year, requiring dates within 90 days and duration difference at most 20 s. Sampling and thresholds are exploratory. [Ribeiro and West, original release](https://zenodo.org/records/4650046) · [Field definitions and 2019 crawl dates](https://github.com/epfl-dlab/YouNiverse#video-metadata) · [CC BY 4.0 release metadata](https://api.datacite.org/dois/10.5281/zenodo.4650046)

| Recorded measure | Result |
|---|---|
| Unique higher-reach cases / lower-reach controls | 116 / 116, nine creators. One creator contributes 44 pairs. Each case is in its stratum's top quarter and has at least twice its matched control's views. Controls come from the bottom quarter. |
| Matched pairs per game family | CS:GO 48, Minecraft 25, Overwatch 11, LoL 8, Halo 8, Dota 2 6, Call of Duty 5, GTA 3, Rocket League 2. CS:GO and unspecified GTA/CoD editions cannot establish results for CS2, GTA RP or Warzone. |
| Median historical views and duration | Cases 7,527.5 views, controls 1,297.5. Both median durations were 51 s. The count difference follows from the selection rule. |
| Titles mentioning an action / highlight marker | 40/116 cases (34%) and 49/116 controls (42%). In 34 pairs both titles matched, in 61 neither did, in six only the case did and in 15 only the control did. A printed title tag alone gives no basis for a positive ranking weight. |
| One record-level check | The archived LoL upload `_Ezadqy1S6E` had 662,754 views at 35 s, paired with `tN_9-9VUMXw` at 318,266 views and 37 s. Counts describe the 2019 crawl, independent of availability today. |

These are **higher- and lower-reach gaming uploads**, identified from public research metadata. No researcher viewed the 232 videos, and lexical filters can admit commentary or exclude genuine plays. The archive prefix is ordered, covers only nine matched channels, and omits current patches, TikTok, Twitch, vertical-first editing, ordinary VOD periods, exposure counts and creator size at publication. Nine creator clusters are inadequate for reliable inference about title markers or generalization. The controls are less successful *relative to their own peer group*. Some are quite popular in absolute terms.

### Reproduce the cohort

Use Python 3.8+ and curl from the command line, with space for a 125 MB compressed research metadata sample. The prefix ends in a partial JSON record, which the selector discards. The source was a separately licensed research release. No calls to YouTube, downloads of video/audio, user profiles, private eval labels or dependent packages are required. The reproducibility unit is the release, prefix hash and pair-list hash. To materialize the ID pairs, write each high and low ID used by the final digest line into a private CSV. Grant access to an analyst separately from any access to media.

```sh
curl --fail --location --range 0-124999999 --max-filesize 125000000 \
  'https://zenodo.org/records/4650046/files/yt_metadata_en.jsonl.gz' -o sample.gz
# Run the Python block below as: python3 select_pairs.py sample.gz
```

Expected input SHA-256 `6813f25b618130b80358cd1db4a0c2cd868e639854310dd7c820db0aaef33f61`. Expected ordered case/control ID digest `4b2b306449b8379b5906cbdd9d4da2c50a126915ffc90d2b2b556a3bc405aca5`. The selector also accepts successive compressed byte ranges as arguments, in order.

```python
import collections, datetime as dt, hashlib, json, re, statistics, sys, zlib

games = {
    "CS:GO": r'\b(cs\s?:?\s?go|counter[- ]strike)\b',
    "Call of Duty": r'\b(call of duty|cod|mw[23]|black ops|bo[234])\b',
    "GTA": r'\b(gta\s?(?:v|5|online)?|grand theft auto)\b',
    "Minecraft": r'\bminecraft\b', "Fortnite": r'\bfortnite\b',
    "LoL": r'\bleague of legends\b', "Rocket League": r'\brocket league\b',
    "Apex Legends": r'\bapex legends\b', "Siege": r'\b(rainbow six|r6s)\b',
    "Overwatch": r'\boverwatch\b', "Dota 2": r'\bdota\s?2\b',
    "Halo": r'\bhalo\b', "Battlefield": r'\bbattlefield\b',
}
excluded = re.compile(r'\b(news|review|trailer|teaser|giveaway|preview|update|patch|roster|announced|unboxing|tutorial|ranking|reaction to|animation|ad|commercial)\b', re.I)
events = re.compile(r'\b(ace|clutch|[1-5]v[1-5]|kill\w*|shot\w*|headshot|highlight\w*|goal\w*|overtime|round|wipe|penta\w*|trickshot|gameplay|fail\w*|vs|combo|glitch|save\w*|frag\w*|funny|montage|snipe\w*|snip\w*|[345]k)\b', re.I)
dec, tail, digest = zlib.decompressobj(31), b'', hashlib.sha256()
rows, seen, strata = 0, set(), collections.defaultdict(list)
for path in sys.argv[1:]:
    with open(path, 'rb') as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
            *lines, tail = (tail + dec.decompress(chunk)).split(b'\n')
            for line in lines:
                rows += 1
                x = json.loads(line)
                if x['categories'] != 'Gaming' or not 8 <= x['duration'] <= 90: continue
                title = x['title'] or ''
                if excluded.search(title) or x['display_id'] in seen: continue
                def hits(text):
                    return [g for g,p in games.items() if re.search(p, text, re.I)]
                candidates = hits(title) or hits(x['tags'] or '')
                if len(candidates) != 1 or x['view_count'] is None: continue
                day = dt.date.fromisoformat(x['upload_date'][:10])
                if (dt.date.fromisoformat(x['crawl_date'][:10])-day).days < 30: continue
                seen.add(x['display_id'])
                strata[x['channel_id'], candidates[0], day.year].append(
                    (int(x['view_count']), x['display_id'], day, x['duration'], bool(events.search(title))))
pairs=[]
for (creator, game, year), items in sorted(strata.items()):
    ranked=sorted(items)
    n=len(ranked)//4
    if n < 2: continue
    low=ranked[:n]
    for hi in reversed(ranked[-n:]):
        candidates=[lo for lo in low if abs((hi[2]-lo[2]).days)<=90 and abs(hi[3]-lo[3])<=20 and hi[0]>=2*max(lo[0],1)]
        if candidates:
            lo=min(candidates,key=lambda z:(abs((hi[2]-z[2]).days),abs(hi[3]-z[3]),z[1]))
            low.remove(lo)
            pairs.append((game,creator,hi,lo))
print('bytes SHA256',digest.hexdigest(),'complete records',rows,'eligible IDs',len(seen))
print('pairs',len(pairs),'creators',len({p[1] for p in pairs}), 'game counts',collections.Counter(p[0] for p in pairs))
print('title markers high/low',sum(p[2][4] for p in pairs),sum(p[3][4] for p in pairs))
print('medians',[(statistics.median(p[i][0] for p in pairs),statistics.median(p[i][3] for p in pairs)) for i in [2,3]])
print('creator max',max(collections.Counter(p[1] for p in pairs).values()))
print('cohort SHA256',hashlib.sha256(''.join(f'{p[2][1]},{p[3][1]}\n' for p in pairs).encode()).hexdigest())
print('example',[(g,hi[1],hi[0],hi[3],lo[1],lo[0],lo[3]) for g,c,hi,lo in pairs[::max(1,len(pairs)//4)][:4]])
print('paired marker cells',collections.Counter((p[2][4],p[3][4]) for p in pairs))
```

## Prospective predictors and outcomes

Wu, Rizoiu and Xie report that watch percentage depends strongly on duration and that channel history carries predictive information. Their duration-conditioned approach suggests a control for this study. Their data covered ordinary YouTube videos in 2016 and cannot establish contemporary game-specific effects. Platform changes can alter the meaning of a view. YouTube's Shorts view-count definition changed on 31 March 2025. Keep metric definition, platform, format, measurement time and era alongside every observation. [Beyond Views](https://cdn.aaai.org/ojs/15031/15031-28-18550-1-2-20201228.pdf) · [YouTube’s explanation of the measurement change](https://support.google.com/youtube/answer/10059070?hl=en)

| Feature family | Prespecified measurement | Plausible confound or falsifier |
|---|---|---|
| Hook and narrative | Seconds to intelligible premise, seconds to first salient cue and central event, presence of setup, reversal and payoff | A recognizable character or tournament can draw attention without an early hook. Blind coders to outcomes. |
| Duration and ending | Total source/published duration, post-payoff dwell, resolved stakes, abrupt cut, loop, dead air | Retention favors short or looping posts. Use duration bins and separate rewatch measures where available. |
| Game intensity | Duration and rate of HUD-confirmed changes, number of distinct actions, contrast to preceding 30 s | Continuous combat and repeated replays inflate simple counts. Require distinct events and a replay flag. |
| Reaction and audience | Visible or audible reaction, onset relative to payoff, lagged unique-chat rate relative to stream baseline | Music, alerts, spectator audio, missing facecam, raids and channel audience size change these values. Track missing separately. |
| Editing and captions | Cuts per 10 s, reframing, caption presence/timing/readability, audio gain change, source vs edit | Captions and editing are publishing decisions. Treat as unavailable to unedited VOD ranking unless testing a separate editing policy. |

Primary outcome for an owner-authorized fixed-age sample is day-7 share of qualified starts reaching the payoff or a prespecified completion threshold, with uncertainty from its exposure denominator. Use the platform's actual retention measure when the payoff curve is unavailable, and keep those endpoints separate. Secondary outcomes are day-7 shares per eligible impression and qualified reach relative to creator history. Record day-1/day-30 for sensitivity. Use only denominators documented as comparable and appropriately licensed. Never compare raw platform view counts as if each platform counted the same action.

Estimate the marginal value of each signal by comparing a creator/game/age/platform/duration baseline against that baseline plus one frozen feature family. Use a regularized model appropriate to the outcome (binomial with exposure denominators for completion, or paired conditional logistic regression for a case/control study). Estimate conditional associations, not population prevalence, from selected pairs. For reach regressions use the full posting frame or inverse-probability weights with known inclusion probabilities. Prespecify which metrics are primary.

Compute held-out paired concordance and group-aware bootstrap intervals by independent creator/session. For calibrated probability claims use natural-prevalence holdouts, reliability diagrams and Brier score. Fit normalization, age curves, hyperparameters and thresholds on development/calibration groups only. Hold out entire creators and a later publication period. Test subgroup stability, feature ablations and missing-signal cases. A claim of useful prediction requires held-out improvement over the metadata-only baseline with a prespecified practically important effect, uncertainty and consistency across games. To claim a causal editing benefit, randomize permissible hook/caption/boundary variants within creators under comparable posting/exposure conditions. The retrospective pilot supplies no causal estimate and no coefficients for VOD ranking. [Dataset design and authorization](DATASET-PLAN.md)
