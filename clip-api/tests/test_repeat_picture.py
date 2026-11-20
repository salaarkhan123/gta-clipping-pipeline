"""Repetitive content: two candidates on the same screen (a lobby, a respawn screen, a loop) are one moment, and the
test stays off in a video whose pictures all look alike (a fixed camera)."""
import random
from types import SimpleNamespace as C

import numpy as np
from PIL import Image

import app.pipeline as P
from app.pipeline import Timer
from app.pipeline.variety import PICTURE_VARIES, SAME_PICTURE, bits_apart, pick_distinct, picture_hash, pictures_differ


def cand(start, picture, score=0.5):
    return C(start=start, end=start + 30.0, score=score, picture=picture, meta={"title": f"t{start}"}, speech="")


def distinct(cands, n=50):
    ranked = sorted(cands, key=lambda c: -c.score)
    return pick_distinct(ranked, n, window=lambda c: (c.start, c.end), meta=lambda c: c.meta, speech=lambda c: c.speech,
                         picture=lambda c: c.picture)


def flip(bits: int, n: int, seed: int) -> int:
    for k in random.Random(seed).sample(range(64), n):
        bits ^= 1 << k
    return bits


def varied(count, seed=1):
    rng = random.Random(seed)
    return [rng.getrandbits(64) for _ in range(count)]


# ---------- the hash ----------

def image(path, pixels):
    Image.fromarray(np.asarray(pixels, dtype=np.uint8)).save(path)
    return path


def test_the_same_screen_hashes_the_same_and_another_picture_does_not(tmp_path):
    rng = np.random.default_rng(3)
    lobby = rng.integers(0, 255, (72, 128), dtype=np.uint8)
    noisy = np.clip(lobby.astype(int) + rng.integers(-6, 6, lobby.shape), 0, 255)       # the same screen, re-encoded
    other = rng.integers(0, 255, (72, 128), dtype=np.uint8)
    a, b, c = (picture_hash(image(tmp_path / f"{n}.png", px)) for n, px in (("a", lobby), ("b", noisy), ("c", other)))
    assert bits_apart(a, b) <= SAME_PICTURE < PICTURE_VARIES <= bits_apart(a, c)
    assert picture_hash(None) is None and picture_hash(tmp_path / "missing.jpg") is None
    (tmp_path / "broken.jpg").write_bytes(b"not an image")
    assert picture_hash(tmp_path / "broken.jpg") is None


# ---------- the rule ----------

def test_five_moments_on_one_screen_become_one_and_the_best_is_kept():
    lobby = 0x0123456789ABCDEF
    # Like the 2-hour benchmark: five moments on one screen 0-2 bits apart, minutes apart, among varied gameplay.
    same = [cand(329, lobby, 0.6), cand(475, flip(lobby, 1, 1), 0.9), cand(590, flip(lobby, 1, 2), 0.5),
            cand(754, lobby, 0.4), cand(876, flip(lobby, 2, 3), 0.7)]
    others = [cand(1500 + 200 * i, p, 0.3) for i, p in enumerate(varied(12))]
    picked, skipped = distinct(same + others)
    assert [c.start for c in picked if c.start < 1000] == [475]                # the best of the five
    assert sum(1 for _i, why in skipped if why == "same picture as a picked clip") == 4
    assert len(picked) == 13                                                   # nothing else is lost


def test_the_same_screen_hours_apart_is_still_one_moment():
    lobby = 0xFFFF0000FFFF0000
    picked, _ = distinct([cand(100, lobby, 0.9), cand(6000, flip(lobby, 2, 5), 0.8)]
                         + [cand(1000 + 300 * i, p, 0.3) for i, p in enumerate(varied(8))])
    assert 100 in [c.start for c in picked] and 6000 not in [c.start for c in picked]


def test_a_fixed_camera_video_keeps_its_clips():
    # Like the Zias react video: every frame is the same couch, so near-identical frames say nothing.
    couch = 0x00FF00FF00FF00FF
    cands = [cand(200 * i, flip(couch, i % 5, i), 0.5 + i / 100) for i in range(20)]
    assert not pictures_differ([c.picture for c in cands])
    picked, skipped = distinct(cands)
    assert len(picked) == 20 and skipped == []


def test_without_frames_or_with_too_few_nothing_changes():
    cands = [cand(200 * i, None, 0.5) for i in range(10)]
    assert len(distinct(cands)[0]) == 10
    few = [cand(0, 5, 0.9), cand(500, 5, 0.8), cand(1000, 7, 0.7)]             # three frames: not enough to tell
    assert len(distinct(few)[0]) == 3
    ranked = sorted(few, key=lambda c: -c.score)
    plain = pick_distinct(ranked, 3, window=lambda c: (c.start, c.end), meta=lambda c: c.meta, speech=lambda c: c.speech)
    assert len(plain[0]) == 3                                                  # the old call, no picture argument


# ---------- in the pipeline ----------

def test_the_judge_records_each_candidates_picture(tmp_path, monkeypatch):
    frame = image(tmp_path / "frame.png", np.random.default_rng(1).integers(0, 255, (72, 128), dtype=np.uint8))
    monkeypatch.setattr(P, "_frame", lambda src, t, out, deadline: frame)
    monkeypatch.setattr(type(frame), "unlink", lambda self, missing_ok=False: None)
    cands = [P._Candidate(start=100.0 * i, end=100.0 * i + 30, base=1.0, signals={}, features={}) for i in range(2)]
    out = P._judge(cands, lambda text, f, ctx: {"title": "t", "virality": {"score": 80}}, tmp_path / "none.mp4", tmp_path,
                   lambda *a: None, None, timer=Timer())
    assert all(c.features["picture"] == f"{picture_hash(frame):016x}" for c in out)
