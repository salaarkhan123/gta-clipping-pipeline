#!/usr/bin/env python3
"""Cut the hero row's clean tiles: one full-frame gameplay crop per platform shape, from the approved wide masters.

Each tile is the same 8-second moment as an approved hero clip (public/media/hero-vertical-clips/manifest.json),
cut from that clip's 1080p master segment with a crop that keeps the streamer's camera out of the picture. The
tile keeps the AI rating of the clip it is a cut of (`rating_of_candidate`), as `clip-wide` already does.
No new footage, no new numbers.

  python3 scripts/make-hero-clean.py --seg ~/ClutchClips-eval/website-media/_work/seg --public public/media

Needs ffmpeg on PATH. Writes public/media/hero-clean/{<id>.mp4, <id>.webp, manifest.json}; editor/editor-1-wide.* (the dead-air slide's wide
clip and filmstrip); and, with --captions-clip, captions/lucia-jason.* (the captions slide's clip and word timings).
Copy public/media to ../web/media afterwards: tests/test_make_site_media.py checks the two match.
"""
import argparse, glob, json, os, subprocess
from pathlib import Path

# id: (hero clip it is a cut of, platform, shape, crop x, crop y, crop w, crop h) on the 1920x1080 master.
TILES = {
    "youtube-wide": ("clip-1", "youtube", "16:9", 384, 140, 1536, 864),      # camera and chat sit in the top-left corner
    "tiktok": ("clip-2", "tiktok", "9:16", 630, 0, 608, 1080),               # the car; camera is at the right edge
    "instagram": ("clip-3", "instagram", "9:16", 660, 0, 608, 1080),         # the pack, right of the streamer
    "facebook": ("clip-4", "facebook", "4:5", 595, 0, 864, 1080),            # between the camera and the scoreboard
    "youtube-shorts": ("clip-5", "youtube", "9:16", 615, 0, 608, 1080),      # the truck; camera is at the right edge
}
HEIGHT = 720
# Seconds into the moment the still is taken from, where 3 s lands on a transition.
POSTER_AT = {"facebook": 1.0}


def run(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", *map(str, args)], check=True, timeout=300)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seg", type=Path, required=True, help="folder of master segments (<name>.mp4 and <name>.json)")
    p.add_argument("--public", type=Path, required=True, help="clip-api/web-src/public/media")
    p.add_argument("--captions-clip", type=Path, help="folder of an approved 4K master with clips.json, for the captions slide")
    p.add_argument("--captions-cid", default="lj-1")
    a = p.parse_args()
    hero = json.loads((a.public / "hero-vertical-clips" / "manifest.json").read_text())
    clips = {i["id"]: i for i in hero["items"]}
    segs = {Path(f).stem: json.loads(Path(f).read_text()) for f in glob.glob(str(a.seg.expanduser() / "*.json"))}
    out = a.public / "hero-clean"
    out.mkdir(parents=True, exist_ok=True)
    items = []
    for tid, (clip_id, platform, shape, x, y, w, h) in TILES.items():
        clip = clips[clip_id]
        src = clip["source"]
        name, seg = next((k, v) for k, v in segs.items()
                         if v["source"] == src["id"] and v["start"] <= src["start_sec"] + .01 and v["end"] >= src["end_sec"] - .01)
        start, seconds = src["start_sec"] - seg["start"], src["end_sec"] - src["start_sec"]
        vf = f"crop={w}:{h}:{x}:{y},scale=-2:{HEIGHT}:flags=lanczos,fps=30"
        master = a.seg.expanduser() / f"{name}.mp4"
        run("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", master, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out / f"{tid}.mp4")
        run("-ss", f"{start + POSTER_AT.get(tid, 3.0):.3f}", "-i", master, "-frames:v", "1", "-vf", vf.rsplit(",", 1)[0], "-quality", "82", out / f"{tid}.webp")
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out / f"{tid}.mp4")],
                               capture_output=True, text=True, check=True, timeout=60).stdout.strip().split(",")
        items.append({"id": tid, "label": f"{clip['game']} ({shape})", "kind": "video", "src": f"{tid}.mp4", "poster": f"{tid}.webp",
                      "width": int(probe[0]), "height": int(probe[1]), "duration_sec": seconds, "game": clip["game"], "aspect": shape, "platform": platform,
                      "rating": clip["rating"], "rating_source": clip["rating_source"], "rating_of_candidate": clip.get("candidate", clip_id),
                      "credit": clip["credit"], "commercial_permission": clip.get("commercial_permission"), "source": src})
        print(tid, probe, os.path.getsize(out / f"{tid}.mp4") // 1024, "KB")
    manifest = {"section": "hero-clean", "version": 1, "permission": hero.get("permission"), "credits": hero.get("credits"), "items": items}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    editor_wide(a.public, segs, a.seg.expanduser())
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


def caption_wide(public: Path, segs: dict, seg_dir: Path):
    """The captions slide's wide clip: the same moment and word timings as captions/plain, cut 16:9 without the camera."""
    path = public / "captions" / "manifest.json"
    manifest = json.loads(path.read_text())
    plain = next(i for i in manifest["items"] if i["id"] == "plain")
    src = plain["source"]
    name, seg = next((k, v) for k, v in segs.items()
                     if v["source"] == src["id"] and v["start"] <= src["start_sec"] + .01 and v["end"] >= src["end_sec"] - .01)
    start, seconds = src["start_sec"] - seg["start"], src["end_sec"] - src["start_sec"]
    vf = f"crop=1516:852:404:114,scale=-2:{HEIGHT}:flags=lanczos,fps=30"
    run("-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", seg_dir / f"{name}.mp4", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "22",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", public / "captions" / "plain-wide.mp4")
    run("-ss", f"{start + 3:.3f}", "-i", seg_dir / f"{name}.mp4", "-frames:v", "1", "-vf", vf.rsplit(",", 1)[0], "-quality", "82", public / "captions" / "plain-wide.webp")
    wide = {**plain, "id": "plain-wide", "label": "No captions, wide (words for a live overlay)", "src": "plain-wide.mp4", "poster": "plain-wide.webp",
            "width": 1280, "height": 720, "aspect": "16:9"}
    wide.pop("webm", None)
    manifest["items"] = [i for i in manifest["items"] if i["id"] != "plain-wide"] + [wide]
    path.write_text(json.dumps(manifest, indent=1) + "\n")
    print("captions/plain-wide", os.path.getsize(public / "captions" / "plain-wide.mp4") // 1024, "KB")


if __name__ == "__main__":
    main()
