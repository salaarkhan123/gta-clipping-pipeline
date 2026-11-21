"""HUD OCR exact-match sheet: a new path, not labels-v2.csv. Empty template is valid."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from tests.test_eval_set import load  # noqa: E402

ev = load("eval_clips")
SHEET = ROOT / "eval" / "labels-hud-ocr.csv"


def write_ocr(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ev.OCR_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"id": "", "vod": "gta-online-1", "game": "gta-online", "notes": "", **r})
    return path


def test_the_committed_ocr_sheet_is_an_empty_valid_template():
    rows, errors = ev.parse_ocr(SHEET)
    assert errors == [] and rows == []
    assert ev.is_ocr(SHEET) and not ev.is_v2(SHEET)
    assert ev.main([str(SHEET)]) == 0


def test_labels_v2_is_not_an_ocr_sheet():
    v2 = ROOT / "eval" / "labels-v2.csv"
    assert ev.is_v2(v2) and not ev.is_ocr(v2)


def test_ocr_exact_match_is_case_fold_and_within_the_time_window(tmp_path):
    sheet = write_ocr(tmp_path / "l.csv", [
        {"id": "a", "t": "0:00:12", "region": "killfeed", "expected_text": "P1 killed P2"},
        {"id": "b", "t": "0:00:21", "region": "banner", "expected_text": "WASTED"},
        {"id": "c", "t": "0:01:00", "region": "banner", "expected_text": "busted"},
        {"id": "d", "t": "0:02:00", "region": "killfeed", "expected_text": ""},   # not labelled yet
    ])
    rows, errors = ev.parse_ocr(sheet)
    assert errors == [] and [r["id"] for r in rows] == ["a", "b", "c", "d"]
    events = [
        {"vod": "gta-online-1", "t": 12.4, "region": "killfeed", "text": "p1 killed p2"},
        {"vod": "gta-online-1", "t": 21.0, "region": "banner", "text": "Wasted"},
        {"vod": "gta-online-1", "t": 90.0, "region": "banner", "text": "mission passed"},  # wrong line
    ]
    s = ev.score_ocr(rows, events)
    assert (s["labelled"], s["hits"], s["misses"], s["unlabelled"]) == (3, 2, 1, 1)
    assert s["exact_match"] == 2 / 3
    assert s["feeds_ranking"] is False and s["gate"] == 0.9
    assert [r["hit"] for r in s["per_row"]] == [True, True, False]


def test_ocr_cli_scores_a_run(tmp_path, capsys):
    sheet = write_ocr(tmp_path / "l.csv", [
        {"id": "a", "t": "12", "region": "banner", "expected_text": "wasted"},
        {"id": "b", "t": "20", "region": "banner", "expected_text": "wasted"},
    ])
    (tmp_path / "e.json").write_text(json.dumps({
        "events": [{"vod": "gta-online-1", "t": 12.0, "region": "banner", "text": "WASTED"},
                   {"vod": "gta-online-1", "t": 20.0, "region": "banner", "text": "WASTED"}]}))
    assert ev.main([str(sheet), str(tmp_path / "e.json"), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["exact_match"] == 1.0 and out["feeds_ranking"] is True and out["hits"] == 2


def test_ocr_cli_refuses_an_unlabelled_sheet(tmp_path):
    sheet = write_ocr(tmp_path / "l.csv", [{"t": "12", "region": "banner", "expected_text": ""}])
    (tmp_path / "e.json").write_text(json.dumps({"events": []}))
    assert ev.main([str(sheet), str(tmp_path / "e.json")]) == 2


def test_ocr_validator_rejects_a_bad_region(tmp_path):
    sheet = write_ocr(tmp_path / "l.csv", [{"t": "12", "region": "minimap", "expected_text": "x"}])
    rows, errors = ev.parse_ocr(sheet)
    assert rows == [] and any("killfeed or banner" in e for e in errors)
