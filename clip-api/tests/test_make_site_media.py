"""scripts/make_site_media.py: candidate ids, and publish copying only the owner's featured picks."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_site_media.py"


def _script():
    spec = importlib.util.spec_from_file_location("make_site_media", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_expand_gives_one_candidate_per_moment_with_its_cid():
    m = _script()
    shots = m.expand([
        {"section": "hero-vertical-clips", "source": "xqc", "moment": [1, 3]},
        {"section": "captions", "variant": "plain", "source": "xqc", "moment": 2, "words_from": "impact"},
    ])
    assert [s["cid"] for s in shots] == ["xqc-m1", "xqc-m3", "plain--xqc-m2"]
    assert shots[2]["words_from"] == "impact--xqc-m2"


def _candidate(out: Path, section: str, cid: str, creator: str, words: str | None = None) -> dict:
    for ext in ("mp4", "webm", "webp"):
        (out / section / f"{cid}.{ext}").write_bytes(cid.encode())
    c = {"cid": cid, "kind": "video", "src": f"{cid}.mp4", "webm": f"{cid}.webm", "poster": f"{cid}.webp",
         "credit": f"Footage: {creator}", "source": {"id": "s", "creator": creator, "url": f"https://x/{creator}"}}
    if words:
        c["words"] = words
    return c


def test_publish_copies_only_featured_in_order_with_public_ids_and_credits(tmp_path):
    m = _script()
    out, public = tmp_path / "cand", tmp_path / "public"
    for section in ("hero-vertical-clips", "captions"):
        (out / section).mkdir(parents=True)
    (out / "captions" / "impact--xqc-m2.words.json").write_text('{"words": []}')
    hero = [_candidate(out, "hero-vertical-clips", cid, who)
            for cid, who in (("tgg-m1", "TGG"), ("xqc-m1", "xQc"), ("ninja-m2", "Ninja"))]
    caps = [_candidate(out, "captions", "impact--xqc-m2", "xQc", "impact--xqc-m2.words.json"),
            _candidate(out, "captions", "plain--xqc-m2", "xQc", "impact--xqc-m2.words.json"),
            _candidate(out, "captions", "impact--tgg-m1", "TGG")]
    for section, cands in (("hero-vertical-clips", hero), ("captions", caps)):
        (out / section / "candidates.json").write_text(json.dumps({"section": section, "candidates": cands}))
    (public / "hero-vertical-clips").mkdir(parents=True)
    (public / "hero-vertical-clips" / "stale.mp4").write_text("old")
    featured = tmp_path / "featured.json"
    featured.write_text(json.dumps({"version": 1, "sections": {
        "hero-vertical-clips": {"show": 2, "clips": ["ninja-m2", "missing-m9", "tgg-m1", "xqc-m1"]},
        "captions": {"clips": ["plain--xqc-m2", "impact--tgg-m1", "impact--xqc-m2"]}}}))

    assert m.publish({"permission": "owner-confirmed 2026-11-18"}, featured, out, public) == 0

    hero_m = json.loads((public / "hero-vertical-clips" / "manifest.json").read_text())
    assert hero_m["permission"] == "owner-confirmed 2026-11-18"
    # `show` picks in the owner's order; the cid with no candidate is skipped and does not use up a slot
    assert [(i["id"], i["candidate"]) for i in hero_m["items"]] == [("clip-1", "ninja-m2"), ("clip-2", "tgg-m1")]
    assert [c["creator"] for c in hero_m["credits"]] == ["Ninja", "TGG"]
    assert sorted(p.name for p in (public / "hero-vertical-clips").iterdir()) == [
        "clip-1.mp4", "clip-1.webm", "clip-1.webp", "clip-2.mp4", "clip-2.webm", "clip-2.webp", "manifest.json"]

    cap_m = json.loads((public / "captions" / "manifest.json").read_text())
    assert [i["id"] for i in cap_m["items"]] == ["plain", "impact", "impact-2"]
    assert cap_m["items"][0]["words"] == "plain.words.json"          # impact's words, copied under plain's name
    assert (public / "captions" / "plain.words.json").exists()
    assert [i["credit"] for i in cap_m["items"]] == ["Footage: xQc", "Footage: TGG", "Footage: xQc"]


def test_publish_leaves_sections_the_owner_did_not_pick(tmp_path):
    m = _script()
    (tmp_path / "public" / "reframe").mkdir(parents=True)
    (tmp_path / "public" / "reframe" / "manifest.json").write_text("{}")
    featured = tmp_path / "featured.json"
    featured.write_text(json.dumps({"version": 1, "sections": {}}))
    assert m.publish({}, featured, tmp_path / "cand", tmp_path / "public") == 0
    assert (tmp_path / "public" / "reframe" / "manifest.json").read_text() == "{}"
