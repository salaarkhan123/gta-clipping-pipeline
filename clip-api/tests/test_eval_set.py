"""The eval set: label sheet generation and scoring a run against labels."""
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev, sheet = load("eval_clips"), load("make_label_sheet")


def write_labels(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "start", "end", "label", "what_happens", "notes", "source"])
        w.writeheader()
        for r in rows:
            w.writerow({"what_happens": "", "notes": "", "source": "top", **r})


LABELS = [
    {"id": 1, "start": "0:05:00", "end": "0:05:30", "label": 3},     # great
    {"id": 2, "start": "0:20:00", "end": "0:20:30", "label": 0},     # junk
    {"id": 3, "start": "1:00:00", "end": "1:00:30", "label": 2},     # good
    {"id": 4, "start": "1:30:00", "end": "1:30:30", "label": 3},     # great, missed below
    {"id": 5, "start": "1:45:00", "end": "1:45:30", "label": ""},    # not labelled yet: ignored
]


def test_seconds_parses_hms_and_plain():
    assert ev.seconds("1:02:03") == 3723 and ev.seconds("2:03") == 123 and ev.seconds("45") == 45


def test_score_counts_good_great_duplicates_and_quarters(tmp_path):
    write_labels(tmp_path / "l.csv", LABELS)
    rows = ev.load_labels(tmp_path / "l.csv")
    assert [r["id"] for r in rows] == ["1", "2", "3", "4"]           # unlabelled row 5 ignored
    clips = [{"start": 302, "end": 332, "title": "a"},               # on row 1 (3)
             {"start": 310, "end": 340, "title": "b"},               # same moment again: duplicate
             {"start": 1200, "end": 1230, "title": "c"},             # on row 2 (0)
             {"start": 3605, "end": 3635, "title": "d"},             # on row 3 (2)
             {"start": 6600, "end": 6630, "title": "e"}]             # on no row: unlabelled
    s = ev.score(rows, clips, duration=7200)
    assert s["clips"] == 5 and s["good_rate"] == 0.6                 # a, b, d are on 2-3 rows
    assert s["great_found"] == "1 of 2" and s["great_recall"] == 0.5
    assert s["great_missed"] == [{"id": "4", "start": 5400.0, "end": 5430.0}]
    assert "missed row 4  1:30:00 to 1:30:30" in ev.report(s)
    assert s["unlabelled"] == 1 and s["duplicate_pairs"] == 1
    assert s["per_quarter"] == [3, 0, 1, 1]
    assert s["mean_label"] == round((3 + 3 + 0 + 2) / 4, 2)


def test_a_small_overlap_is_not_a_match():
    rows = [{"id": "1", "start": 100.0, "end": 130.0, "label": 3}]
    assert ev.match({"start": 125, "end": 155}, rows) is None          # 5 s of overlap
    assert ev.match({"start": 115, "end": 145}, rows)["id"] == "1"     # 15 s


def test_cli_reads_a_job_response(tmp_path, capsys):
    write_labels(tmp_path / "l.csv", LABELS)
    job = {"id": "job_x", "clips": [{"id": "c1", "start_sec": 300.0, "end_sec": 330.0, "title": "Plane into the bay"}]}
    (tmp_path / "job.json").write_text(json.dumps(job))
    assert ev.main([str(tmp_path / "l.csv"), str(tmp_path / "job.json"), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["good_rate"] == 1.0 and out["per_clip"][0]["row"] == "1"


def test_cli_refuses_an_unlabelled_sheet(tmp_path):
    write_labels(tmp_path / "l.csv", [{"id": 1, "start": "0:01:00", "end": "0:01:30", "label": ""}])
    (tmp_path / "job.json").write_text(json.dumps({"clips": []}))
    assert ev.main([str(tmp_path / "l.csv"), str(tmp_path / "job.json")]) == 2


def test_sheet_covers_every_quarter_even_when_one_half_is_louder():
    # Signal strong only in the second half: the global top alone would skip the first half.
    score = np.zeros(4000)
    score[2000:] = np.linspace(0.5, 1.0, 2000)
    score[[300, 1300]] = 0.2
    rows = sheet.candidates(score, 4000, 30, top=5, per_quarter=2)
    starts = [s for s, _e, _src in rows]
    assert any(s < 1000 for s in starts) and any(1000 <= s < 2000 for s in starts)
    assert all(rows[i][0] < rows[i + 1][0] for i in range(len(rows) - 1))           # sorted by time
    assert all(rows[i][1] <= rows[i + 1][0] for i in range(len(rows) - 1))          # merged: no overlaps


def test_sheet_csv_has_empty_label_columns(tmp_path):
    sheet.write_sheet([(65.0, 95.0, "q1"), (4000.0, 4030.0, "top+q3")], tmp_path / "s.csv")
    rows = list(csv.DictReader(open(tmp_path / "s.csv")))
    assert rows[0]["start"] == "0:01:05" and rows[1]["end"] == "1:07:10" and rows[0]["label"] == ""
    assert ev.load_labels(tmp_path / "s.csv") == []                                  # nothing labelled yet


def test_wayin_benchmark_sheet_loads_fifteen_moments():
    rows = ev.load_labels(Path(__file__).resolve().parent.parent / "eval" / "wayin-zias-iceman.csv")
    assert len(rows) == 15 and all(r["label"] == 3 and r["end"] > r["start"] for r in rows)
    assert (rows[0]["start"], rows[0]["end"]) == (2338.0, 2430.0)            # their #1: 38:58 to 40:30
    found = ev.score(rows, [{"start": 2340, "end": 2400, "title": "a"}], duration=4680)
    assert found["great_found"] == "1 of 15" and len(found["great_missed"]) == 14


def test_v1_scores_of_a_real_run_stay_the_same():
    # The selection-only run on staging 347ca2f, scored by the v1 harness before eval set v2: 7 of 15, the same
    # moments as the 2026-11-16 benchmark in docs/super-board/runs/2026-11-16-swarm.md.
    root = Path(__file__).resolve().parent.parent / "eval"
    rows = ev.load_labels(root / "wayin-zias-iceman.csv")
    s = ev.score(rows, ev.load_clips(root / "runs" / "zias-iceman.staging-347ca2f.json"))
    assert (s["clips"], s["good_rate"], s["mean_label"], s["great_found"], s["great_recall"]) == (23, 0.304, 3.0, "7 of 15", 0.467)
    assert (s["unlabelled"], s["duplicate_pairs"], s["per_quarter"]) == (16, 0, [6, 6, 6, 5])
    assert sorted(int(c["row"]) for c in s["per_clip"] if c["row"]) == [1, 3, 5, 9, 11, 12, 15]
    assert (s["precision@20"], s["precision@40"]) == (0.3, 0.175)        # new in v2: 6 of the best 20, 7 of 40
