"""Eval set v2: the sheet validator, the matching rule, precision@k and recall per video and held out, and the
labelling helper (label_moments.py and eval/labeller.html)."""
import csv
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev, lm = load("eval_clips"), load("label_moments")


def sheet(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ev.V2_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"id": "", "game": "gta-rp", "rating": "", "reason": "", "held_out": "no", "source": "", **r})
    return path


def job(path, clips):
    path.write_text(json.dumps({"clips": [{"start_sec": s, "end_sec": e, **extra} for s, e, extra in clips]}))
    return path


def row(vod, start, end, rating, **kw):
    return {"vod": vod, "start": start, "end": end, "rating": rating,
            "reason": kw.pop("reason", "big moment" if rating == "3" else ""), **kw}


# ---- the validator ----

def test_a_valid_sheet_has_no_errors_and_unrated_rows_are_kept(tmp_path):
    rows, errors = ev.parse_v2(sheet(tmp_path / "s.csv", [
        row("gta-rp-1", "0:01:00", "0:01:45", "3", held_out="yes"),
        row("gta-rp-1", "0:05:00", "0:05:30", "", held_out="yes"),
        row("valorant-1", "12:00", "12:40", "1", game="valorant"),
    ]))
    assert errors == []
    assert [(r["vod"], r["start"], r["label"], r["held_out"]) for r in rows] == [
        ("gta-rp-1", 60.0, 3, True), ("gta-rp-1", 300.0, None, True), ("valorant-1", 720.0, 1, False)]


@pytest.mark.parametrize("bad, message", [
    ({"vod": "GTA RP"}, "vod 'GTA RP' is not a short id"),
    ({"game": ""}, "game '' is not a short id"),
    ({"start": "1:xx"}, "are not times"),
    ({"end": "0:00:59"}, "must be 5 to 300 s"),                       # ends before it starts
    ({"end": "0:01:03"}, "must be 5 to 300 s"),                       # 3 s
    ({"end": "0:06:01"}, "must be 5 to 300 s"),                       # 301 s
    ({"rating": "0"}, "rating '0' must be 1, 2, 3 or empty"),
    ({"rating": "great"}, "rating 'great' must be"),
    ({"rating": "3", "reason": ""}, "a 3 needs a reason"),
    ({"reason": "x" * 81}, "keep it under 80"),
    ({"held_out": "maybe"}, "held_out 'maybe' must be yes or no"),
])
def test_the_validator_rejects_a_bad_row_with_its_line(tmp_path, bad, message):
    good = row("gta-rp-1", "0:10:00", "0:10:30", "2")
    rows, errors = ev.parse_v2(sheet(tmp_path / "s.csv", [good, {**row("gta-rp-1", "0:01:00", "0:01:45", "2"), **bad}]))
    assert len(errors) == 1 and errors[0].startswith("line 3: ") and message in errors[0], errors
    assert len(rows) == 1                                              # the bad row is left out, the good one kept


def test_the_validator_checks_the_sheet_as_a_whole(tmp_path):
    _rows, errors = ev.parse_v2(sheet(tmp_path / "s.csv", [
        row("a", "0:01:00", "0:01:30", "2", id="x"),
        row("a", "0:01:10", "0:01:40", "1", id="x"),                   # same id; overlaps line 2 by 20 of 30 s
        row("a", "0:05:00", "0:05:30", "2", game="gta-online"),        # game differs within one video
        row("a", "0:09:00", "0:09:30", "2", held_out="yes"),           # held_out differs within one video
        row("a", "0:01:20", "0:01:50", ""),                            # unrated: may overlap anything
        row("b", "0:01:00", "0:01:30", "2"), row("b", "0:01:15", "0:01:45", "2"),   # exactly half: allowed
    ]))
    assert errors == ["line 3: id x is already used on line 2",
                      "line 4: game differs from line 2 for vod a (one value per video)",
                      "line 5: held_out differs from line 2 for vod a (one value per video)",
                      "line 3: overlaps line 2 by more than half: one moment rated twice (merge them, or trim one)"]


def test_a_sheet_without_the_v2_columns_is_refused(tmp_path):
    (tmp_path / "s.csv").write_text("vod,rating,start\n")
    assert ev.parse_v2(tmp_path / "s.csv")[1][0].startswith("header: missing column(s) game, end, reason, held_out")


def test_the_committed_v2_sheet_is_valid():
    assert ev.parse_v2(ROOT / "eval" / "labels-v2.csv")[1] == []


# ---- matching and the metrics ----

def test_matching_takes_the_largest_overlap_then_the_higher_rating():
    a = {"id": "a", "start": 100.0, "end": 130.0, "label": 1}
    b = {"id": "b", "start": 130.0, "end": 160.0, "label": 3}
    assert ev.match({"start": 110, "end": 140}, [a, b])["id"] == "a"          # 20 s on a, 10 s on b
    assert ev.match({"start": 115, "end": 145}, [a, b])["id"] == "b"          # 15 s each: the 3 wins
    assert ev.match({"start": 125, "end": 135}, [a, b])["id"] == "b"          # a 10 s clip needs 3.3 s: 5 s each
    assert ev.match({"start": 155, "end": 200}, [a, b]) is None               # 5 s of a 45 s clip: under 10 s


def test_precision_counts_the_best_ranked_clips_and_a_moment_once():
    rows = [{"id": str(i), "start": 1000.0 * i, "end": 1000.0 * i + 40, "label": lab}
            for i, lab in enumerate([3, 2, 1, 3], 1)]
    clips = [{"start": 1000, "end": 1040, "rank": 1},     # on 3: hit
             {"start": 1005, "end": 1045, "rank": 2},     # same moment again: not a hit
             {"start": 3000, "end": 3040, "rank": 3},     # on a 1: not a hit
             {"start": 9000, "end": 9040, "rank": 4},     # on nothing: unrated
             {"start": 2000, "end": 2040, "rank": 5}]     # on a 2: hit
    s = ev.score_vod(rows, list(reversed(clips)))         # listed order does not matter: rank does
    assert (s["hits@20"], s["precision@20"], s["precision@40"], s["unrated@20"]) == (2, 0.1, 0.05, 1)
    assert (s["great"], s["great_found"], s["recall"]) == (2, 1, 0.5)
    assert [m["id"] for m in s["missed"]] == ["4"]
    assert [c["rank"] for c in s["per_clip"]] == [1, 2, 3, 4, 5] and s["per_clip"][0]["rating"] == 3


def test_only_the_top_k_count():
    rows = [{"id": str(i), "start": 100.0 * i, "end": 100.0 * i + 30, "label": 2} for i in range(50)]
    clips = [{"start": 100.0 * i, "end": 100.0 * i + 30, "score": 1 - i / 100} for i in range(45)]
    s = ev.score_vod(rows, clips)
    assert (s["hits@20"], s["hits@40"], s["precision@20"], s["precision@40"]) == (20, 40, 1.0, 1.0)
    assert ev.score_vod(rows, clips[:10])["precision@20"] == 0.5         # 10 clips cannot fill 20 places


def test_ranking_falls_back_to_score_then_listed_order():
    assert [c["s"] for c in ev.ranked([{"s": 1, "score": 0.2}, {"s": 2, "score": 0.9}])] == [2, 1]
    assert [c["s"] for c in ev.ranked([{"s": 1, "rank": 2, "score": 0.9}, {"s": 2, "rank": 1, "score": 0.1}])] == [2, 1]
    assert [c["s"] for c in ev.ranked([{"s": 1}, {"s": 2}])] == [1, 2]


def two_vods(tmp_path):
    labels = sheet(tmp_path / "s.csv", [
        row("online", "0:01:00", "0:01:40", "3"), row("online", "0:10:00", "0:10:40", "2"),
        row("online", "0:20:00", "0:20:40", ""),
        row("rp", "0:02:00", "0:02:40", "3", held_out="yes"), row("rp", "0:30:00", "0:30:40", "3", held_out="yes"),
        row("other", "0:05:00", "0:05:40", "2", game="valorant"),
    ])
    online = job(tmp_path / "online.json", [(60, 100, {"rank": 1}), (600, 640, {"rank": 2}), (1200, 1240, {"rank": 3})])
    rp = job(tmp_path / "rp.json", [(120, 160, {"rank": 1}), (5000, 5040, {"rank": 2})])
    return labels, online, rp


def test_numbers_per_video_tuning_and_held_out(tmp_path):
    labels, online, rp = two_vods(tmp_path)
    rows, _ = ev.parse_v2(labels)
    s = ev.score_v2(rows, {"online": ev.load_clips(online), "rp": ev.load_clips(rp)})
    on, held = s["per_vod"]["online"], s["per_vod"]["rp"]
    assert (on["hits@20"], on["unrated@20"], on["recall"]) == (2, 1, 1.0)          # the unrated row takes no part
    assert (held["hits@20"], held["recall"], held["held_out"]) == (1, 0.5, True)
    assert s["tuning"] == {"vods": 1, "great": 1, "great_found": 1, "recall": 1.0, "hits@20": 2, "precision@20": 0.1,
                           "unrated@20": 1, "hits@40": 2, "precision@40": 0.05, "unrated@40": 1}
    assert (s["held_out"]["precision@20"], s["held_out"]["recall"]) == (0.05, 0.5)
    assert (s["all"]["hits@20"], s["all"]["precision@20"], s["all"]["recall"]) == (3, 0.075, 0.667)
    assert s["unscored"] == ["other"]
    with pytest.raises(ValueError, match="no rows for vod gta-x"):
        ev.score_v2(rows, {"gta-x": []})


def test_the_report_hides_the_held_out_clips_unless_asked(tmp_path, capsys):
    labels, online, rp = two_vods(tmp_path)
    assert ev.main([str(labels), f"online={online}", f"rp={rp}"]) == 0
    out = capsys.readouterr().out
    assert "tuning (1 vod): precision@20 10% · precision@40 5% · recall 100% (1 of 1 3s)" in out
    assert "held_out (1 vod): precision@20 5%" in out and "rp (held out), 2 clips: " in out
    assert "#1   0:01:00  rating 3" in out and "0:02:00" not in out and "missed" not in out
    assert "no run given for: other" in out
    assert ev.main([str(labels), f"online={online}", f"rp={rp}", "--show-held-out"]) == 0
    out = capsys.readouterr().out
    assert "#1   0:02:00  rating 3" in out and "missed line6  0:30:00 to 0:30:40  big moment" in out
    assert ev.main([str(labels), f"rp={rp}", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["per_vod"]["rp"]["per_clip"] == []


def test_the_cli_checks_a_sheet_and_refuses_bad_input(tmp_path, capsys):
    labels, online, _rp = two_vods(tmp_path)
    assert ev.main([str(labels)]) == 0
    out = capsys.readouterr().out
    assert "6 rows, valid" in out and "online (gta-rp): rated 2 of 3 · 3s 1 · 2s 1 · 1s 0" in out
    assert "warning: other has no 3-rated moment yet" in out and "warning: 5 rated moments" in out
    assert ev.main([str(labels), str(online)]) == 2                                  # no vod=
    assert ev.main([str(labels), f"nope={online}"]) == 2
    bad = sheet(tmp_path / "bad.csv", [row("a", "0:01:00", "0:01:30", "5")])
    assert ev.main([str(bad), f"a={online}"]) == 1
    assert "line 2: rating '5'" in capsys.readouterr().err


# ---- the labelling helper ----

def test_add_fills_a_sheet_once_and_carries_v1_labels(tmp_path, capsys):
    labels = tmp_path / "labels-v2.csv"
    run = job(tmp_path / "run1.json", [(600, 645, {"rank": 2}), (60, 105, {"rank": 1}), (3000, 3045, {"rank": 3})])
    args = ["add", str(labels), "--vod", "gta-rp-1", "--game", "gta-rp", "--held-out", "yes", "--job", str(run)]
    assert lm.main(args + ["--top", "2"]) == 0
    rows, errors = ev.parse_v2(labels)
    assert errors == [] and [(r["id"], r["start"], r["source"]) for r in rows] == [
        ("gta-rp-1-1", 60.0, "run1#1"), ("gta-rp-1-2", 600.0, "run1#2")]          # the best two, by rank
    assert lm.main(args + ["--top", "2"]) == 0 and "added 0 moments" in capsys.readouterr().out.splitlines()[-1]
    v1 = tmp_path / "v1.csv"
    v1.write_text("id,start,end,label,what_happens,notes,source\n7,0:01:20,0:02:00,3,,,top\n8,0:20:00,0:20:30,0,,,q2\n"
                  "9,0:30:00,0:30:30,,,,q3\n")
    second = job(tmp_path / "run2.json", [(3010, 3055, {"rank": 1})])            # covers run1's #3, never added
    assert lm.main(args + ["--job", str(second), "--sheet", str(v1)]) == 0
    rows, _ = ev.parse_v2(labels)
    assert [(r["start"], r["label"], r["source"]) for r in rows] == [
        (60.0, None, "run1#1"), (600.0, None, "run1#2"), (1200.0, 1, "v1:v1#8"), (1800.0, None, "v1:v1#9"),
        (3000.0, None, "run1#3")]                     # v1 row 7 overlaps run1#1 by 25 of 40 s: covered; a 0 is a 1
    other = ["add", str(labels), "--vod", "gta-rp-1", "--game", "gta-online", "--held-out", "yes", "--sheet", str(v1)]
    assert lm.main(other) == 1                                                    # one game per video


def test_select_writes_a_ranked_job_file_from_a_local_video(video, tmp_path):
    out = tmp_path / "sel.json"
    assert lm.main(["select", str(video), str(out)]) == 0
    clips = ev.load_clips(out)
    assert clips and [c["rank"] for c in clips] == list(range(1, len(clips) + 1))
    assert all(0 <= c["start"] < c["end"] <= 41 for c in clips)
    assert not list(tmp_path.glob("**/*.mp4"))                                     # nothing rendered


def test_the_labeller_page_writes_the_same_columns_and_csv_as_the_scripts(tmp_path):
    page = (ROOT / "eval" / "labeller.html").read_text()
    fields = json.loads(re.search(r"const FIELDS = (\[.*?\]);", page).group(1))
    assert fields == ev.V2_FIELDS
    assert (re.search(r"MIN_LEN = (\d+), MAX_LEN = (\d+), REASON_MAX = (\d+)", page).groups()
            == (str(int(ev.MIN_LEN)), str(int(ev.MAX_LEN)), str(ev.REASON_MAX)))
    if not shutil.which("node"):
        pytest.skip("node not installed: CSV round trip not checked")
    js = page.split("// ---- CSV ----")[1].split("// ---- autosave")[0]
    src = sheet(tmp_path / "s.csv", [row("b", "0:01:00", "0:01:30", "3", reason='a "quote", and a comma'),
                                     row("a", "1:59:59", "2:00:30", "")])
    expected = tmp_path / "py.csv"
    lm.write_sheet(expected, list(csv.DictReader(open(src))))
    script = (f"const FIELDS = {json.dumps(ev.V2_FIELDS)}; let rows;\n{js}\n"
              f"const t = parseCsv(require('fs').readFileSync({json.dumps(str(src))}, 'utf8')); const head = t.shift();"
              "rows = t.map((r) => { const o = {}; head.forEach((h, i) => o[h] = r[i] || '');"
              " return { ...o, start: secs(o.start), end: secs(o.end) }; });"
              "process.stdout.write(sheetText());")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert out == expected.read_bytes().decode()          # LF endings, like the page
