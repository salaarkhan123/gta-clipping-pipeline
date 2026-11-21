"use client";
// Adjust range: a filmstrip of the video with two drag handles, and the start, length and end as text.
// The strip is drawn from the video itself when the browser can play it (an upload); a link that is not in
// yet shows its own thumbnail across the strip. `null` is the whole video (the API's `range: null`).
import { useEffect, useRef, useState } from "react";
import { hms, Span } from "../RangeSlider";

const FRAMES = 10, W = 160, H = 90;
const parse = (v: string): number | null => {
  const parts = v.trim().split(":");
  if (!v.trim() || parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null;
  return parts.map(Number).reduce((t, n) => t * 60 + n, 0);
};

// Draws FRAMES evenly spaced frames of `src` into the canvas, one after another. Gives up quietly (the strip
// keeps its background) when the browser cannot read the file.
function useFilmstrip(src: string | null | undefined, duration: number, canvas: React.RefObject<HTMLCanvasElement | null>) {
  const [drawn, setDrawn] = useState(0);
  useEffect(() => {
    const c = canvas.current;
    if (!src || !c || duration <= 0) return;
    const ctx = c.getContext("2d");
    const v = document.createElement("video");
    let i = 0, alive = true;
    v.muted = true; v.preload = "auto"; v.playsInline = true; v.src = src;
    const next = () => { if (alive && i < FRAMES) v.currentTime = Math.min(duration - 0.5, ((i + 0.5) / FRAMES) * duration); };
    v.onloadedmetadata = next;
    v.onseeked = () => {
      if (!alive || !ctx) return;
      const scale = Math.max(W / v.videoWidth, H / v.videoHeight), w = v.videoWidth * scale, h = v.videoHeight * scale;
      ctx.drawImage(v, i * W + (W - w) / 2, (H - h) / 2, w, h);
      setDrawn(++i);
      next();
    };
    return () => { alive = false; v.removeAttribute("src"); v.load(); };
  }, [src, duration, canvas]);
  return drawn;
}

function TimeField({ label, sec, onSet, disabled }: { label: string; sec: number; onSet: (s: number) => void; disabled?: boolean }) {
  const [typed, setTyped] = useState<string | null>(null);
  const commit = () => { const n = typed === null ? null : parse(typed); if (n !== null) onSet(Math.round(n)); setTyped(null); };
  return (
    <label className="m-0 grid gap-1 text-center text-[12px] font-normal text-muted">
      <input inputMode="numeric" value={typed ?? hms(sec)} disabled={disabled} aria-label={`${label}, hours:minutes:seconds`}
        onChange={(e) => setTyped(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }}
        className="w-full rounded-12 border border-solid border-line-soft bg-surface px-2 py-[10px] text-center text-[14px] tabular-nums text-text" />
      {label}
    </label>
  );
}

export function RangeStrip({ duration, value, onChange, gap, video, thumb }: { duration: number | null; value: Span | null; onChange: (v: Span | null) => void;
  gap: number; video?: string | null; thumb?: string | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const total = Math.max(1, Math.floor(duration || 0)), known = !!duration && duration > gap;
  const drawn = useFilmstrip(known ? video : null, total, canvas);
  const least = Math.min(gap, total);
  const start = Math.min(value?.start ?? 0, total - least), end = Math.max(Math.min(value?.end ?? total, total), start + least);
  const set = (s: number, e: number) => {
    s = Math.max(0, Math.min(s, total - least));
    e = Math.min(total, Math.max(e, s + least));
    onChange(s <= 0 && e >= total ? null : { start: s, end: e });
  };
  const pct = (sec: number) => `${(sec / total) * 100}%`;
  return (
    <div className="grid gap-3">
      <div className="relative h-14 overflow-hidden rounded-12 border border-solid border-line bg-raised">
        {thumb && !drawn && <span className="absolute inset-0 [background-position:center] [background-repeat:repeat-x] [background-size:auto_100%] opacity-70"
          style={{ backgroundImage: `url("${thumb.replace(/"/g, "%22")}")` }} aria-hidden="true" />}
        <canvas ref={canvas} width={FRAMES * W} height={H} className="absolute inset-0 h-full w-full" aria-hidden="true" />
        {known && <>
          <span className="pointer-events-none absolute inset-y-0 left-0 bg-[rgba(0,0,0,.62)]" style={{ width: pct(start) }} />
          <span className="pointer-events-none absolute inset-y-0 right-0 bg-[rgba(0,0,0,.62)]" style={{ width: `calc(100% - ${pct(end)})` }} />
          <span className="pointer-events-none absolute inset-y-0 rounded-8 border-2 border-solid border-text" style={{ left: pct(start), width: `calc(${pct(end)} - ${pct(start)})` }} />
          <div className="range2 trim-handles" style={{ "--a": pct(start), "--b": pct(end) } as React.CSSProperties}>
            <input type="range" min={0} max={total} step={1} value={start} aria-label="Start of the part to clip" aria-valuetext={hms(start)}
              style={{ zIndex: start > total / 2 ? 3 : 2 }} onChange={(e) => set(Math.min(+e.target.value, end - least), end)} />
            <input type="range" min={0} max={total} step={1} value={end} aria-label="End of the part to clip" aria-valuetext={hms(end)}
              style={{ zIndex: 2 }} onChange={(e) => set(start, Math.max(+e.target.value, start + least))} />
          </div>
        </>}
      </div>
      <div className="grid grid-cols-3 gap-2">
        <TimeField label="Start" sec={start} disabled={!known} onSet={(n) => set(Math.min(n, end - least), end)} />
        <TimeField label="Length" sec={end - start} disabled={!known} onSet={(n) => set(start, start + Math.max(least, n))} />
        <TimeField label="End" sec={end} disabled={!known} onSet={(n) => set(start, Math.max(n, start + least))} />
      </div>
      {!known && <p className="m-0 text-[12.5px] text-muted">{duration ? "This video is too short to pick a part of it." : "You can pick a part of the video once its length is known."}</p>}
    </div>
  );
}
