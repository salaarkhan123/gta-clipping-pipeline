"""Visual search: embed sampled frames with CLIP once per upload, then match text queries against them."""
import statistics
import subprocess
import threading

import numpy as np

from .ff import SAFE_IN, Deadline, MediaInfo, PipelineError, run

SIZE = 224          # CLIP input size
STEP = 2.0          # seconds between indexed frames


def _norm(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-8)


class FastembedClip:
    """CLIP ViT-B/32 via ONNX (fastembed). CPU only, no PyTorch. Models are baked into the Docker image."""
    _lock = threading.Lock()
    _models = None

    def _load(self):
        with self._lock:
            if FastembedClip._models is None:
                from fastembed import ImageEmbedding, TextEmbedding
                FastembedClip._models = (ImageEmbedding("Qdrant/clip-ViT-B-32-vision"),
                                         TextEmbedding("Qdrant/clip-ViT-B-32-text"))
        return FastembedClip._models

    def embed_images(self, frames: np.ndarray) -> np.ndarray:
        from PIL import Image
        img, _ = self._load()
        out = np.asarray(list(img.embed([Image.fromarray(f) for f in frames], batch_size=32)), dtype=np.float32)
        return _norm(out)

    def embed_text(self, texts: list[str]) -> np.ndarray:
        _, txt = self._load()
        return _norm(np.asarray(list(txt.embed(texts)), dtype=np.float32))


def keyframe_gap(src, deadline: Deadline | None = None) -> float | None:
    """Median seconds between keyframes in the first 90 s, or None if it cannot be read."""
    try:
        res = run(["ffprobe", "-v", "error", *SAFE_IN, "-select_streams", "v:0", "-skip_frame", "nokey",
                   "-show_entries", "frame=pts_time,best_effort_timestamp_time", "-of", "csv=p=0",
                   "-read_intervals", "%+90", src], deadline, cap=120)
    except PipelineError as e:
        if e.code == "timeout":
            raise
        return None
    times = []
    for line in res.stdout.splitlines():
        for part in line.split(","):
            try:
                times.append(float(part))
                break
            except ValueError:
                continue
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    return statistics.median(gaps) if len(gaps) >= 2 else None


def iter_frames(src, step: float, keyframes_only: bool, deadline: Deadline | None = None, batch: int = 32):
    """Yields uint8 arrays of shape (k, SIZE, SIZE, 3), one frame per `step` seconds, streamed from ffmpeg."""
    cmd = ["ffmpeg", "-loglevel", "error", "-nostdin", *(["-skip_frame", "nokey"] if keyframes_only else []),
           *SAFE_IN, "-i", str(src), "-an", "-vf", f"fps=1/{step:g},scale={SIZE}:{SIZE}",
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    timer = None
    if deadline and deadline.at is not None:
        timer = threading.Timer(max(1.0, deadline.remaining()), proc.kill)   # never hang past the job deadline
        timer.start()
    n = SIZE * SIZE * 3
    try:
        while True:
            if deadline:
                deadline.remaining()
            buf = proc.stdout.read(n * batch)
            k = len(buf) // n
            if k == 0:
                break
            yield np.frombuffer(buf[:k * n], np.uint8).reshape(k, SIZE, SIZE, 3)
    finally:
        if timer:
            timer.cancel()
        proc.kill()
        proc.wait()


def build_visual_index(src, info: MediaInfo, embedder, deadline: Deadline | None = None, on_progress=None):
    """Returns (embeddings float16 [frames, dim], step_seconds). Decodes keyframes only when they are dense enough."""
    gap = keyframe_gap(src, deadline)
    total = max(1, int(info.duration / STEP))
    for keyframes_only in ([True, False] if gap is not None and gap <= 4.0 else [False]):
        embs, done = [], 0
        for frames in iter_frames(src, STEP, keyframes_only, deadline):
            embs.append(embedder.embed_images(frames))
            done += len(frames)
            if on_progress:
                on_progress(min(done, total), total)
        if embs:
            return np.concatenate(embs).astype(np.float16), STEP
    raise PipelineError("no_frames", "Could not read any video frames from this file.")


def search_visual(emb: np.ndarray, step: float, embedder, query: str, limit: int, duration: float,
                  min_sim: float = 0.2, min_z: float = 2.5) -> list[dict]:
    """Frames that match the query far better than the rest of the same video, grouped into moments."""
    tv = embedder.embed_text([query, f"a screenshot of {query}"]).mean(axis=0)
    tv = tv / max(float(np.linalg.norm(tv)), 1e-8)
    sims = emb.astype(np.float32) @ tv
    med = float(np.median(sims))
    mad = float(np.median(np.abs(sims - med)))
    z = (sims - med) / max(1.4826 * mad, 0.01)   # floor: near-static videos must not turn noise into matches
    hot = np.flatnonzero((z >= min_z) & (sims >= min_sim))
    groups, cur = [], []
    for i in hot:
        if cur and i - cur[-1] > 2:
            groups.append(cur)
            cur = []
        cur.append(int(i))
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        zmax = float(z[g].max())
        out.append({"start": round(g[0] * step, 2), "end": round(min(duration, (g[-1] + 1) * step), 2),
                    "text": f"Looks like: {query}", "score": round(min(0.95, 0.5 + zmax / 12), 3), "kind": "visual"})
    out.sort(key=lambda m: (-m["score"], m["start"]))
    return out[:limit]
