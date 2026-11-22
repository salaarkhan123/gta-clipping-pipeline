#!/usr/bin/env python3
"""Cut the homepage stage's clipping media from approved masters. No new footage, no new numbers.

The clipping slide cycles through one set per game. A set is one source (the stream's whole frame, with the stream's
true length) and five finished cuts of that same source in the platform shapes, cropped to keep the streamer's
camera out of the picture. A tile shows the AI rating recorded for the moment it is cut from (the hero candidates'
judge run, or the rating run recorded in a new-clips folder's clips.json); a moment with none gets no rating.

  python scripts/make-hero-clean.py --media ~/ClutchClips-eval/website-media --new-clips ~/ClutchClips-eval/redesign/new-clips \\
      --public public/media [--editor-wide] [--captions-clip <folder>]

Needs ffmpeg on PATH. Writes public/media/hero-clean/{<set>-source.*, <set>-<n>.*, manifest.json}; with --editor-wide,
editor/editor-1-wide.* (the dead-air slide's wide clip and filmstrip); with --captions-clip, captions/lucia-jason.*.
Copy public/media to ../web/media afterwards: tests/test_make_site_media.py checks the two match.
"""
import argparse, glob, json, os, subprocess
from pathlib import Path

# The rotation, in order: consecutive sets are different games and the two Call of Duty sets are never adjacent.
# A stream set's clips are approved moments in website-media/hero-vertical-clips/candidates.json, cut from their 1080p
# master segments; a folder set's are approved 4K clips listed in new-clips/<folder>/clips.json.
# Each tile: (platform, shape, clip, seconds into the clip, crop on the master as x, y, w, h).
SHAPES = [("youtube", "16:9"), ("tiktok", "9:16"), ("instagram", "9:16"), ("facebook", "4:5"), ("youtube", "9:16")]
SETS = [
    {"id": "gta-vi", "source": "xqc", "card": "xqc-m3", "tiles": [        # camera and chat down the left
        ("xqc-m3", 0, (404, 114, 1516, 852)), ("xqc-m4", 0, (790, 0, 608, 1080)), ("xqc-m10", 0, (700, 0, 608, 1080)),
        ("xqc-m1", 0, (600, 0, 864, 1080)), ("xqc-m9", 2, (700, 0, 608, 1080))]},
    {"id": "forza", "source": "forza", "card": "forza-m1", "tiles": [     # camera top-right
        ("forza-m1", 0, (0, 114, 1516, 852)), ("forza-m6", 0, (630, 0, 608, 1080)), ("forza-m3", 0, (630, 0, 608, 1080)),
        ("forza-m4", 0, (420, 0, 864, 1080)), ("forza-m2", 0, (630, 0, 608, 1080))]},
    # Burned-in word captions, no camera. m2 opens on a censored swear, so its card and tiles start 3 s in; m3 opens
    # underwater for 3 s.
    {"id": "gta-rp", "folder": "gta-rp", "scout": "treyten-rob", "card": "wide--treyten-rob-m2", "card_at": 3, "tiles": [
        ("wide--treyten-rob-m2", 3, (0, 0, 3840, 2160)), ("wide--treyten-rob-m1", 0, (1312, 0, 1216, 2160)),
        ("wide--treyten-rob-m3", 3, (1312, 0, 1216, 2160)), ("wide--treyten-rob-m2", 3, (1056, 0, 1728, 2160)),
        ("wide--treyten-rob-m1", 3, (1312, 0, 1216, 2160))]},
    {"id": "cdl", "folder": "cod-competitive", "scout": "cdl-champs25", "card": "wide--cdl-champs25-m1", "tiles": [   # player camera bottom-right
        ("wide--cdl-champs25-m2", 0, (0, 0, 3128, 1760)), ("wide--cdl-champs25-m1", 0, (1232, 0, 1216, 2160)),
        ("wide--cdl-champs25-m3", 0, (1312, 0, 1216, 2160)), ("wide--cdl-champs25-m1", 4, (700, 0, 1728, 2160)),
        ("wide--cdl-champs25-m2", 4, (1232, 0, 1216, 2160))]},
    {"id": "valorant", "source": "timmy", "card": "timmy-m3", "tiles": [  # camera top-left
        ("timmy-m3", 0, (442, 125, 1478, 831)), ("timmy-m5", 0, (700, 0, 608, 1080)), ("timmy-m6", 0, (700, 0, 608, 1080)),
        ("timmy-m4", 0, (595, 0, 864, 1080)), ("timmy-m7", 0, (700, 0, 608, 1080))]},
    # Stream overlays along the top (camera top-left, chat top-right); kai-gta5a-m1 is left out for its language.
    {"id": "gta-v", "folder": "gta-v", "scout": "kai-gta5b", "card": "wide--kai-gta5b-m3", "tiles": [
        ("wide--kai-gta5b-m1", 0, (192, 216, 3456, 1944)), ("wide--kai-gta5b-m3", 0, (1312, 0, 1216, 2160)),
        ("wide--kai-gta5b-m1", 2, (1312, 0, 1216, 2160)), ("wide--kai-gta5b-m2", 0, (1056, 0, 1728, 2160)),
        ("wide--kai-gta5b-m3", 3, (1312, 0, 1216, 2160))]},
    {"id": "warzone", "source": "cod-nick", "card": "cod-nick-m1", "tiles": [   # camera right, mid height
        ("cod-nick-m1", 0, (0, 125, 1478, 831)), ("cod-nick-m3", 0, (615, 0, 608, 1080)), ("cod-nick-m2", 0, (615, 0, 608, 1080)),
        ("cod-nick-m1", 2, (500, 0, 864, 1080)), ("cod-nick-m3", 2, (615, 0, 608, 1080))]},
    {"id": "fortnite", "source": "ninja", "card": "ninja-m1", "tiles": [  # 720p master; camera left, mid height
        ("ninja-m1", 0, (280, 40, 960, 540)), ("ninja-m2", 0, (438, 0, 405, 720)), ("ninja-m1", 2, (330, 0, 405, 720)),
        ("ninja-m2", 2, (352, 0, 576, 720)), ("ninja-m1", 0, (330, 0, 405, 720))]},
    # Streamer cut-out bottom-left; viewer chat and an in-game chat bubble top-right (m1's bubble shows a slur, so the
    # card is m2 and every crop stays below and left of the bubble). m3 goes black for a second mid-moment: unused.
    {"id": "ea-fc", "source": "fifa-speed", "card": "fifa-speed-m2", "tiles": [
        ("fifa-speed-m1", 0, (562, 170, 1040, 585)), ("fifa-speed-m2", 0, (630, 0, 608, 1080)), ("fifa-speed-m1", 2, (630, 0, 608, 1080)),
        ("fifa-speed-m1", 2, (620, 160, 736, 920)), ("fifa-speed-m2", 2, (630, 0, 608, 1080))]},
]
# Encoded at twice the size the stage shows them at its widest (a 195 px row, a 340 px source card).
TILE_H, CARD_W, CARD_H, SECONDS, POSTER_AT = 400, 704, 396, 6.0, 2.0


def run(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", *map(str, args)], check=True, timeout=300)


# A bitrate ceiling keeps fast footage (Warzone) as small as calm footage; the stage only ever loads two sets at once.
def encode(master, start, vf, out: Path, name: str, crf=27, maxrate="700k"):
    run("-ss", f"{start:.3f}", "-t", f"{SECONDS:.3f}", "-i", master, "-an", "-vf", vf + ",fps=30", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-maxrate", maxrate, "-bufsize", "1400k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out / f"{name}.mp4")
    run("-ss", f"{start + POSTER_AT:.3f}", "-i", master, "-frames:v", "1", "-vf", vf, "-quality", "80", out / f"{name}.webp")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out / f"{name}.mp4")],
                           capture_output=True, text=True, check=True, timeout=60).stdout.strip().split(",")
    return int(probe[0]), int(probe[1])


class Clips:
    """Where a set's clips come from: (master file, seconds into it where the clip starts, its candidate record)."""

    def __init__(self, media: Path, new_clips: Path):
        self.seg = media / "_work" / "seg"
        self.cands = {c["cid"]: c for c in json.loads((media / "hero-vertical-clips" / "candidates.json").read_text())["candidates"]}
        self.media, self.new_clips = media, new_clips

    def clip(self, s: dict, cid: str):
        if "folder" in s:
            folder = self.new_clips / s["folder"]
            clips = {c["cid"]: c for c in json.loads((folder / "clips.json").read_text())["clips"]}
            wide = clips[cid]
            # The rating run is recorded on the 9:16 cut of the same moment (the clip the judge saw).
            rated = clips.get(cid.removeprefix("wide--"), wide)
            return folder / wide["src"], 0.0, {**wide, **{k: rated[k] for k in ("rating", "rating_source", "rating_run") if k in rated}}
        cand = self.cands[cid]
        seg = json.loads((self.seg / f"{cid}.json").read_text())
        return self.seg / f"{cid}.mp4", cand["source"]["start_sec"] - seg["start"], cand

    def duration(self, s: dict) -> float:
        scout = self.media / ("_work-creator" if "folder" in s else "_work") / "scout" / f"{s.get('scout', s.get('source'))}.json"
        return json.loads(scout.read_text())["duration_sec"]


def hero_clean(media: Path, new_clips: Path, public: Path):
    clips, out = Clips(media, new_clips), public / "hero-clean"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        old.unlink()
    items = []
    for s in SETS:
        master, start, card = clips.clip(s, s["card"])
        src = card["source"]
        common = {"set": s["id"], "kind": "video", "game": card["game"], "credit": card["credit"], "commercial_permission": card.get("commercial_permission"),
                  "duration_sec": SECONDS}
        w, h = encode(master, start + s.get("card_at", 0), f"scale={CARD_W}:{CARD_H}:flags=lanczos", out, f"{s['id']}-source")
        items.append({**common, "id": f"{s['id']}-source", "role": "source", "label": f"{card['game']}: the stream", "src": f"{s['id']}-source.mp4",
                      "poster": f"{s['id']}-source.webp", "width": w, "height": h, "aspect": "16:9", "source_duration_sec": clips.duration(s),
                      "source": {k: src[k] for k in ("creator", "title", "url") if k in src}})
        for n, ((cid, offset, (x, y, cw, ch)), (platform, shape)) in enumerate(zip(s["tiles"], SHAPES), 1):
            master, start, c = clips.clip(s, cid)
            assert c["source"].get("title") == src.get("title"), f"{cid} is not from the {s['id']} source"
            name = f"{s['id']}-{n}"
            w, h = encode(master, start + offset, f"crop={cw}:{ch}:{x}:{y},scale=-2:{TILE_H}:flags=lanczos", out, name)
            item = {**common, "id": name, "role": "tile", "label": f"{c['game']} ({shape})", "src": f"{name}.mp4", "poster": f"{name}.webp", "width": w,
                    "height": h, "aspect": shape, "platform": platform, "rating_of_candidate": cid.removeprefix("wide--"),
                    "source": {**{k: src[k] for k in ("creator", "title", "url") if k in src},
                               "start_sec": round(c["source"]["start_sec"] + offset, 2), "end_sec": round(c["source"]["start_sec"] + offset + SECONDS, 2)}}
            if c.get("rating") is not None and c.get("rating_source") == "ai":
                item.update(rating=c["rating"], rating_source="ai")
                if c.get("rating_run"):
                    item["rating_run"] = c["rating_run"]
            items.append(item)
        print(s["id"], "done")
    credits = {i["source"]["creator"]: i["source"].get("url") for i in items if i["role"] == "source"}
    manifest = {"section": "hero-clean", "version": 2, "permission": "owner-confirmed 2026-11-18; Call of Duty League, Treyten, Kai Cenat: owner-approved 2026-11-21",
                "credits": [{"creator": k, "url": v} for k, v in credits.items()], "items": items}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print("hero-clean", sum(f.stat().st_size for f in out.glob("*")) // 1024, "KB in", len(items), "items")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--media", type=Path, required=True, help="~/ClutchClips-eval/website-media (masters in _work/seg, candidates, scout data)")
    p.add_argument("--new-clips", type=Path, required=True, help="~/ClutchClips-eval/redesign/new-clips (approved 4K clips, one folder per set)")
    p.add_argument("--public", type=Path, required=True, help="clip-api/web-src/public/media")
    p.add_argument("--editor-wide", action="store_true", help="also cut editor/editor-1-wide for the dead-air slide")
    p.add_argument("--captions-clip", type=Path, help="folder of an approved 4K master with clips.json, for the captions slide")
    p.add_argument("--captions-cid", default="lj-1")
    a = p.parse_args()
    media = a.media.expanduser()
    hero_clean(media, a.new_clips.expanduser(), a.public)
    if a.editor_wide:
        seg_dir = media / "_work" / "seg"
        editor_wide(a.public, {Path(f).stem: json.loads(Path(f).read_text()) for f in glob.glob(str(seg_dir / "*.json"))}, seg_dir)
    if a.captions_clip:
        captions_clip(a.public, a.captions_clip.expanduser(), a.captions_cid)



def captions_clip(public: Path, folder: Path, cid: str):
    """The captions slide's clip: a web encode of an approved 4K master (its clips.json names the credit and source),
    cropped to the picture inside its letterbox, with word timings from the repo's own transcriber (faster-whisper)."""
    meta = next(c for c in json.loads((folder / "clips.json").read_text())["clips"] if c["cid"] == cid)
    out, master = public / "captions", folder / meta["src"]
    vf = "crop=3414:1920:213:120,scale=1920:1080:flags=lanczos,fps=30"
    run("-i", master, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "25", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out / "lucia-jason.mp4")
    run("-i", master, "-an", "-vf", vf, "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", "0", "-row-mt", "1", out / "lucia-jason.webm")
    run("-ss", "4", "-i", master, "-frames:v", "1", "-vf", vf.rsplit(",", 1)[0], "-quality", "84", out / "lucia-jason.webp")
    import numpy as np
    from faster_whisper import WhisperModel   # the worker's transcriber; runs locally, no key
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(master), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True, timeout=120).stdout
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    segments, _ = WhisperModel("small.en", compute_type="int8").transcribe(audio, word_timestamps=True)
    words = [{"start": round(w.start, 2), "end": round(w.end, 2), "text": w.word.strip()} for seg in segments for w in seg.words]
    (out / "lucia-jason.words.json").write_text(json.dumps({"words": words}, indent=1) + "\n")
    path = out / "manifest.json"
    manifest = json.loads(path.read_text())
    item = {"id": "lucia-jason", "candidate": cid, "label": "No captions, wide (words for a live overlay)", "kind": "video", "src": "lucia-jason.mp4",
            "webm": "lucia-jason.webm", "poster": "lucia-jason.webp", "width": 1920, "height": 1080, "duration_sec": meta["duration_sec"], "game": meta["game"],
            "aspect": "16:9", "words": "lucia-jason.words.json", "credit": meta["credit"], "commercial_permission": meta["commercial_permission"],
            "source": {k: meta["source"][k] for k in ("creator", "title", "url", "start_sec", "end_sec")}}
    manifest["items"] = [i for i in manifest["items"] if i["id"] != "lucia-jason"] + [item]
    if not any(c.get("creator") == meta["source"]["creator"] for c in manifest.get("credits", [])):
        manifest.setdefault("credits", []).append({"creator": meta["source"]["creator"], "url": meta["source"]["url"]})
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    print("captions/lucia-jason", os.path.getsize(out / "lucia-jason.mp4") // 1024, "KB mp4,", os.path.getsize(out / "lucia-jason.webm") // 1024, "KB webm;", " ".join(w["text"] for w in words))


STRIP_FRAMES = 14


def editor_wide(public: Path, segs: dict, seg_dir: Path):
    """The dead-air slide's wide clip: the same moment, words and audio levels as editor/editor-1, as the whole 16:9
    frame with the streamer's camera in it (the slide is about someone talking), plus a filmstrip of its own frames
    (STRIP_FRAMES evenly spaced stills in one row)."""
    path = public / "editor" / "manifest.json"
    manifest = json.loads(path.read_text())
    tall = next(i for i in manifest["items"] if i["id"] == "editor-1")
    src = tall["source"]
    name, seg = next((k, v) for k, v in segs.items()
                     if v["source"] == src["id"] and v["start"] <= src["start_sec"] + .01 and v["end"] >= src["end_sec"] - .01)
    start, seconds = src["start_sec"] - seg["start"], src["end_sec"] - src["start_sec"]
    crop = "crop=1920:1080:0:0"
    master, out = seg_dir / f"{name}.mp4", public / "editor"
    run("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", master, "-an", "-vf", f"{crop},scale=-2:{HEIGHT}:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "slow",
        "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out / "editor-1-wide.mp4")
    run("-ss", f"{start + 3:.3f}", "-i", master, "-frames:v", "1", "-vf", f"{crop},scale=-2:{HEIGHT}:flags=lanczos", "-quality", "82", out / "editor-1-wide.webp")
    run("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", master, "-frames:v", "1",
        "-vf", f"{crop},fps={STRIP_FRAMES}/{seconds:.3f},scale=192:108:flags=lanczos,tile={STRIP_FRAMES}x1", "-quality", "80", out / "editor-1-wide.strip.webp")
    wide = {**tall, "id": "editor-1-wide", "label": "Transcript editor, wide", "src": "editor-1-wide.mp4", "poster": "editor-1-wide.webp",
            "width": 1280, "height": 720, "aspect": "16:9", "strip": "editor-1-wide.strip.webp", "strip_frames": STRIP_FRAMES}
    wide.pop("webm", None)
    manifest["items"] = [i for i in manifest["items"] if i["id"] != "editor-1-wide"] + [wide]
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    print("editor/editor-1-wide", os.path.getsize(out / "editor-1-wide.mp4") // 1024, "KB")


STRIP_FRAMES = 14


def editor_wide(public: Path, segs: dict, seg_dir: Path):
    """The dead-air slide's wide clip: the same moment, words and audio levels as editor/editor-1, as the whole 16:9
    frame with the streamer's camera in it (the slide is about someone talking), plus a filmstrip of its own frames
    (STRIP_FRAMES evenly spaced stills in one row)."""
    path = public / "editor" / "manifest.json"
    manifest = json.loads(path.read_text())
    tall = next(i for i in manifest["items"] if i["id"] == "editor-1")
    src = tall["source"]
    name, seg = next((k, v) for k, v in segs.items()
                     if v["source"] == src["id"] and v["start"] <= src["start_sec"] + .01 and v["end"] >= src["end_sec"] - .01)
    start, seconds = src["start_sec"] - seg["start"], src["end_sec"] - src["start_sec"]
    crop = "crop=1920:1080:0:0"
    master, out = seg_dir / f"{name}.mp4", public / "editor"
    run("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", master, "-an", "-vf", f"{crop},scale=-2:{HEIGHT}:flags=lanczos,fps=30", "-c:v", "libx264", "-preset", "slow",
        "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out / "editor-1-wide.mp4")
    run("-ss", f"{start + 3:.3f}", "-i", master, "-frames:v", "1", "-vf", f"{crop},scale=-2:{HEIGHT}:flags=lanczos", "-quality", "82", out / "editor-1-wide.webp")
    run("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", master, "-frames:v", "1",
        "-vf", f"{crop},fps={STRIP_FRAMES}/{seconds:.3f},scale=192:108:flags=lanczos,tile={STRIP_FRAMES}x1", "-quality", "80", out / "editor-1-wide.strip.webp")
    wide = {**tall, "id": "editor-1-wide", "label": "Transcript editor, wide", "src": "editor-1-wide.mp4", "poster": "editor-1-wide.webp",
            "width": 1280, "height": 720, "aspect": "16:9", "strip": "editor-1-wide.strip.webp", "strip_frames": STRIP_FRAMES}
    wide.pop("webm", None)
    manifest["items"] = [i for i in manifest["items"] if i["id"] != "editor-1-wide"] + [wide]
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    print("editor/editor-1-wide", os.path.getsize(out / "editor-1-wide.mp4") // 1024, "KB")



if __name__ == "__main__":
    main()
