<!-- Mirrors store docs/gaming-intelligence-labeling-workflow.md -->

# GTA human-labeling workflow (owner)

**Purpose.** Rate the 30 exported GTA candidates so A/B/C metrics can run.  
**Rule.** ClutchClips scores are proposals only — never ground truth. Do not invent ratings.

---

## What you need locally

1. Sheet: `clip-api/eval/gi-gta-label-sheet.csv` (30 rows, human fields blank).
2. Labeller: open `clip-api/eval/gi-labeller.html` in Chrome.
3. Video: your local `gta-online-1` file under `~/ClutchClips-eval/` (or any path). **Never commit the video.**

R2 object is available to research hosts for agent benches; your machine should use the file you already own.

---

## Steps (~25–40 minutes)

1. Chrome → Open `gi-labeller.html`.
2. **Open sheet** → select `gi-gta-label-sheet.csv`.
3. **Open video** → select the matching local VOD (labeller tries to match `gta-online-1` by filename).
4. For each row (plays start→end):
   - **quality_1_5** — highlight quality (1 junk … 5 post as-is)
   - **entertainment_1_5** — fun / watchability
   - **context_1_5** — how understandable without prior VOD context
   - **suitable_tiktok / shorts / reels** — yes / no / maybe
   - **genuine_highlight** — is this a real gaming highlight for the title?
   - **clutch_correct** — was nominating this interval reasonable?
   - Optional tags/notes; set **rater** once
5. **Save sheet** (downloads CSV). Replace `clip-api/eval/gi-gta-label-sheet.csv` or keep a private copy and pass its path to compare.
6. Optional gap-hunt: add ≥3 owner-found moments the picker missed (new rows) so recall is not only “among proposals”.

Keys: `1`–`5` (quality focus) · `J`/`K` next/prev · `Space` · `R` replay · `Ctrl/Cmd+S` save.

---

## Completeness gate

A row counts as **rated** only when all of these are filled:

`quality_1_5`, `entertainment_1_5`, `context_1_5`, `genuine_highlight`, `clutch_correct`

Check:

```bash
cd clip-api
python3 scripts/gaming_intelligence_cli.py sheet-stats eval/gi-gta-label-sheet.csv
python3 scripts/gaming_intelligence_cli.py compare eval/gi-gta-label-sheet.csv
```

Compare stays **`blocked_no_human_labels`** until you rate. Claim-ready threshold in the harness: **≥20** complete ratings (prefer all 30 + gap-hunt).

---

## Census now (2026-11-21)

| Asset | Status |
| --- | --- |
| Candidates | 30 from labels-v2 / pipeline proposals |
| Human complete ratings | **0** |
| Metrics | blocked — awaiting owner |
