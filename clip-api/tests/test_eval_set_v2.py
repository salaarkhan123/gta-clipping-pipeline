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


def job(path, clips, system=None):
    run = {"clips": [{"start_sec": s, "end_sec": e, **extra} for s, e, extra in clips]}
    path.write_text(json.dumps({**run, **({"system": system} if system else {})}))
    return path


def counts(d):
    return {k: d[k] for k in ("n", "hits", "misses", "repeats", "unrated")}


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
    assert counts(s["@20"]) == {"n": 5, "hits": 2, "misses": 1, "repeats": 1, "unrated": 1}
    assert [c["verdict"] for c in s["per_clip"]] == ["hit", "repeat", "miss", "unrated", "hit"]
    assert (s["great"], s["great_found"], s["recall"]) == (2, 1, 0.5)
    assert [m["id"] for m in s["missed"]] == ["4"]
    assert [c["rank"] for c in s["per_clip"]] == [1, 2, 3, 4, 5] and s["per_clip"][0]["rating"] == 3


def test_unrated_clips_are_not_misses_precision_is_a_range():
    rows = [{"id": str(i), "start": 100.0 * i, "end": 100.0 * i + 30, "label": 2 if i < 10 else 1} for i in range(14)]
    clips = [{"start": 100.0 * i, "end": 100.0 * i + 30, "rank": i + 1} for i in range(20)]   # 10 hits, 4 misses, 6 unrated
    a = ev.score_vod(rows, clips)["@20"]
    assert counts(a) == {"n": 20, "hits": 10, "misses": 4, "repeats": 0, "unrated": 6} and not a["short"]
    assert (a["precision_rated"], a["precision_low"], a["precision_high"]) == (0.714, 0.5, 0.8)
    line = ev.fmt_at(a)
    assert line == ("@20: 20 clips · hits 10 · misses 4 · repeats 0 · unrated 6 · precision 71% of rated, "
                    "50% to 80% (unrated as misses / as hits)")
    nothing_rated = ev.score_vod([], clips)["@20"]
    assert nothing_rated["precision_rated"] is None and "precision - of rated, 0% to 100%" in ev.fmt_at(nothing_rated)


def test_a_run_with_fewer_than_k_clips_prints_both_over_k_and_over_n(tmp_path, capsys):
    rows = [{"id": str(i), "start": 100.0 * i, "end": 100.0 * i + 30, "label": 3, "reason": "x"} for i in range(50)]
    full = [{"start": 100.0 * i, "end": 100.0 * i + 30, "rank": i + 1} for i in range(45)]
    s = ev.score_vod(rows, full)
    assert (s["@40"]["n"], s["@40"]["hits"], s["@40"]["short"], s["@40"]["precision_low"]) == (40, 40, False, 1.0)
    assert "run returned only" not in ev.fmt_at(s["@40"])                    # 45 clips fill 40 places
    short = ev.score_vod(rows, full[:12])                                    # 12 clips, all hits
    for k, strict in ((20, 0.6), (40, 0.3)):
        a = short[f"@{k}"]
        assert (a["n"], a["hits"], a["short"], a["precision_low"], a["strict_low"], a["strict_high"]) == (
            12, 12, True, 1.0, strict, strict)
    assert ev.fmt_at(short["@20"]).endswith(
        "100% to 100% (unrated as misses / as hits) · run returned only 12 clips: 60% to 60% of 20 (strict)")
    labels = sheet(tmp_path / "s.csv", [row("v", ev.hms(100 * i), ev.hms(100 * i + 30), "3") for i in range(50)])
    run = job(tmp_path / "r.json", [(100.0 * i, 100.0 * i + 30, {"rank": i + 1}) for i in range(12)])
    assert ev.main([str(labels), f"v={run}", "--json"]) == 0
    a = json.loads(capsys.readouterr().out)["systems"]["clutchclips"]["per_vod"]["v"]["@20"]
    assert (a["n"], a["k"], a["short"], a["strict_low"], a["precision_low"]) == (12, 20, True, 0.6, 1.0)
    assert ev.main([str(labels), f"v={run}"]) == 0
    assert "only 12 of 20: 60% to 60%" in capsys.readouterr().out


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
    s = ev.score_v2(rows, {"clutchclips": {"online": ev.load_clips(online), "rp": ev.load_clips(rp)}})
    ours = s["systems"]["clutchclips"]
    on, held = ours["per_vod"]["online"], ours["per_vod"]["rp"]
    assert counts(on["@20"]) == {"n": 3, "hits": 2, "misses": 0, "repeats": 0, "unrated": 1}   # unrated row: no part
    assert on["recall"] == 1.0
    assert (held["@20"]["hits"], held["recall"], held["held_out"]) == (1, 0.5, True)
    t = ours["tuning"]
    assert (t["vods"], t["great"], t["great_found"], t["recall"]) == (1, 1, 1, 1.0)
    assert (t["@20"]["k"], t["@20"]["n"], t["@20"]["precision_rated"], t["@20"]["strict_low"]) == (20, 3, 1.0, 0.1)
    a = ours["all"]["@20"]                                                    # pooled: counts add up, k too
    assert (a["k"], a["n"], a["hits"], a["unrated"], a["precision_low"], a["precision_high"]) == (40, 5, 3, 2, 0.6, 1.0)
    assert ours["all"]["recall"] == 0.667 and s["unscored"] == {"clutchclips": ["other"]}
    with pytest.raises(ValueError, match="no rows for vod gta-x"):
        ev.score_v2(rows, {"clutchclips": {"gta-x": []}})


def test_two_systems_are_compared_in_one_table(tmp_path, capsys):
    labels, online, rp = two_vods(tmp_path)
    wayin_online = job(tmp_path / "w-online.json", [(1200, 1240, {"rank": 1}), (600, 640, {"rank": 2})], "wayin")
    wayin_rp = job(tmp_path / "w-rp.json", [(1800, 1840, {"rank": 1})], "wayin")
    assert ev.main([str(labels), f"online={online}", f"rp={rp}", f"online={wayin_online}", f"rp={wayin_rp}"]) == 0
    out = capsys.readouterr().out.splitlines()
    head = out[0].split()
    assert head[:3] == ["system", "recall", "of"] and "unrated" in head
    t = [i for i, line in enumerate(out) if line.startswith("tuning (1 vod)")][0]
    assert out[t].split()[3:5] == ["clutchclips", "1"] and out[t + 2].split()[0] == "wayin"     # side by side
    held = [line for line in out if line.startswith("held_out (1 vod)")][0]
    assert "1 of 2 (50%)" in held
    assert any(line.startswith("rp (held out)") for line in out)
    assert "wayin on rp: held out, clips and misses hidden (--show-held-out)" in out
    assert "no clutchclips run given for: other" in out and "no wayin run given for: other" in out
    assert ev.main([str(labels), f"online={online}", f"online={online}"]) == 2          # one run per system and video


def test_the_report_hides_the_held_out_clips_unless_asked(tmp_path, capsys):
    labels, online, rp = two_vods(tmp_path)
    assert ev.main([str(labels), f"online={online}", f"rp={rp}"]) == 0
    out = capsys.readouterr().out
    assert "clutchclips on online, 3 clips:" in out and "#1   0:01:00  hit      rating 3" in out
    assert "clutchclips on rp: held out, clips and misses hidden (--show-held-out)" in out
    assert "0:02:00" not in out and "missed" not in out
    assert ev.main([str(labels), f"online={online}", f"rp={rp}", "--show-held-out"]) == 0
    out = capsys.readouterr().out
    assert "#1   0:02:00  hit      rating 3" in out and "missed 3 line6  0:30:00 to 0:30:40  big moment" in out
    assert ev.main([str(labels), f"rp={rp}", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["systems"]["clutchclips"]["per_vod"]["rp"]["per_clip"] == []


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
        ("gta-rp-1-1", 60.0, "clutchclips:run1#1"), ("gta-rp-1-2", 600.0, "clutchclips:run1#2")]   # best two, by rank
    assert lm.main(args + ["--top", "2"]) == 0 and "added 0 moments" in capsys.readouterr().out.splitlines()[-1]
    v1 = tmp_path / "v1.csv"
    v1.write_text("id,start,end,label,what_happens,notes,source\n7,0:01:20,0:02:00,3,,,top\n8,0:20:00,0:20:30,0,,,q2\n"
                  "9,0:30:00,0:30:30,,,,q3\n")
    assert lm.main(args + ["--sheet", str(v1)]) == 0
    rows, _ = ev.parse_v2(labels)
    assert [(r["start"], r["label"], r["source"]) for r in rows] == [
        (60.0, None, "clutchclips:run1#1+v1:v1#7"), (600.0, None, "clutchclips:run1#2"), (1200.0, 1, "v1:v1#8"),
        (1800.0, None, "v1:v1#9"), (3000.0, None, "clutchclips:run1#3")]   # v1 row 7 covered by run1#1; a 0 is a 1
    other = ["add", str(labels), "--vod", "gta-rp-1", "--game", "gta-online", "--held-out", "yes", "--sheet", str(v1)]
    assert lm.main(other) == 1                                                    # one game per video


def test_add_pools_a_wayin_run_whole_and_tags_shared_moments(tmp_path):
    labels = tmp_path / "labels-v2.csv"
    ours = job(tmp_path / "ours.json", [(100.0 * i, 100.0 * i + 45, {"rank": i}) for i in range(1, 41)])
    theirs = job(tmp_path / "w.json", [(110, 150, {"rank": 2}), (5000, 5060, {"rank": 1})]
                 + [(6000.0 + 100 * i, 6000.0 + 100 * i + 50, {"rank": i + 3}) for i in range(35)], "wayin")
    base = ["add", str(labels), "--vod", "v", "--game", "gta-rp", "--held-out", "no"]
    assert lm.main(base + ["--job", str(ours), "--job", str(theirs)]) == 0
    rows = lm.read_sheet(labels)
    assert len(rows) == 30 + 36                                     # our best 30; all 37 of theirs, one covered by ours
    first = rows[0]
    assert (first["start"], first["source"]) == ("0:01:40", "clutchclips:ours#1+wayin:w#2")    # offered by both
    assert any(r["source"] == "wayin:w#1" and r["start"] == "1:23:20" for r in rows)
    assert [lm.seconds(r["start"]) for r in rows] == sorted(lm.seconds(r["start"]) for r in rows)   # by time
    assert lm.main(base + ["--job", str(ours), "--job", str(theirs)]) == 0 and len(lm.read_sheet(labels)) == 66


def test_wayin_ranks_come_from_the_file_names_or_a_csv(tmp_path):
    names = [tmp_path / n for n in ("02_chase.mp4", "01_crash.mp4", "10_end.mp4")]
    assert lm.wayin_ranks(names, None) == {"01_crash.mp4": 1, "02_chase.mp4": 2, "10_end.mp4": 3}
    plain = [tmp_path / n for n in ("chase.mp4", "crash.mp4")]
    with pytest.raises(ValueError, match="start each file name with its place in Wayin's list"):
        lm.wayin_ranks(plain, None)
    with pytest.raises(ValueError, match="same leading number"):
        lm.wayin_ranks([tmp_path / "1_a.mp4", tmp_path / "01_b.mp4"], None)
    (tmp_path / "r.csv").write_text("filename,rank\nchase.mp4,2\ncrash.mp4,1\n")
    assert lm.wayin_ranks(plain, tmp_path / "r.csv") == {"crash.mp4": 1, "chase.mp4": 2}
    (tmp_path / "s.csv").write_text("filename,score\nchase.mp4,97\ncrash.mp4,99\n")
    assert lm.wayin_ranks(plain, tmp_path / "s.csv") == {"crash.mp4": 1, "chase.mp4": 2}       # higher score first
    (tmp_path / "bad.csv").write_text("filename,score\nchase.mp4,97\n")
    with pytest.raises(ValueError, match="has no score for crash.mp4"):
        lm.wayin_ranks(plain, tmp_path / "bad.csv")
    (tmp_path / "head.csv").write_text("name,place\nchase.mp4,1\n")
    with pytest.raises(ValueError, match="header must be filename,rank or filename,score"):
        lm.wayin_ranks(plain, tmp_path / "head.csv")


def test_the_labeller_is_blind_to_which_system_offered_a_row():
    page = (ROOT / "eval" / "labeller.html").read_text()
    script = page.split("<script>")[1]
    uses = re.findall(r"\.source\b.{0,12}", script)
    assert uses and all(re.match(r'\.source [!=]== "owner"', u) for u in uses), uses   # only "you added it"
    assert not re.search(r"\$\{\s*\w+\.id\s*\}", script)                    # ids are numbered per system: never shown
    assert "mine = () => rows.filter((r) => r.vod === vod).sort((a, b) => a.start - b.start)" in script   # by time


def test_select_writes_a_ranked_job_file_from_a_local_video(video, tmp_path):
    out = tmp_path / "sel.json"
    assert lm.main(["select", str(video), str(out)]) == 0
    system, clips = ev.load_run(out)
    assert system == "clutchclips" and clips and [c["rank"] for c in clips] == list(range(1, len(clips) + 1))
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
