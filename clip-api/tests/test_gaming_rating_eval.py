"""AS-1 gaming rating eval scaffolding: sheet stats only; no parallel scorer; no fake metrics."""
import json
import sys
from pathlib import Path

from app.pipeline.ranking import SCORES, clean, equal_shares, rank_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gaming_rating_eval as gre  # noqa: E402

SHEET = Path(__file__).resolve().parents[1] / "eval" / "gi-gta-label-sheet.csv"
EXAMPLE = Path(__file__).resolve().parents[1] / "eval" / "score_weights_equal.example.json"


def test_gi_sheet_exists_and_is_unrated():
    stats = gre.sheet_stats(SHEET)
    assert stats["ok"] is True
    assert stats["rows"] == 30
    assert stats["rated_rows"] == 0
    assert stats["metrics_ready"] is False
    assert stats["ndcg_claimed"] is False
    assert stats["precision_claimed"] is False
    assert "No human ratings" in stats["note"]
    assert "no parallel scorer" in stats["score_path"]


def test_sheet_stats_cli_json(capsys):
    assert gre.main(["sheet-stats", str(SHEET)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["metrics_ready"] is False and out["rated_rows"] == 0


def test_equal_shares_match_plain_mean_ranking():
    shares = equal_shares()
    assert clean(shares) == shares
    scores = {k: float(i * 10) for i, k in enumerate(SCORES, start=1)}
    assert rank_score(scores, None) == rank_score(scores, shares)


def test_equal_weights_example_json_is_numerically_equal():
    table = json.loads(EXAMPLE.read_text())
    for key, weights in table.items():
        cleaned = clean(weights)
        assert cleaned is not None, key
        scores = {"hook": 90, "payoff": 80, "clarity": 70, "emotion": 60, "pacing": 50}
        assert rank_score(scores, cleaned) == rank_score(scores, None)
