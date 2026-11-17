"use client";
import { useState } from "react";

export type Span = { start: number; end: number };
// Always h:mm:ss, so the two fields line up and read the same for a short clip and a six-hour stream.
export const hms = (s: number) => {
  const t = Math.max(0, Math.round(s));
  return `${Math.floor(t / 3600)}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
};
// "1:02:03", "2:03" or "45" in seconds; null when it is not a time.
function parse(v: string): number | null {
  const parts = v.trim().split(":");
  if (!v.trim() || parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null;
  return parts.map(Number).reduce((t, n) => t * 60 + n, 0);
}

// One end of the range as text. The typed value is taken on Enter or when the field is left; anything that is
// not a time puts the old value back.
function TimeField({ label, sec, onSet }: { label: string; sec: number; onSet: (sec: number) => void }) {
  const [typed, setTyped] = useState<string | null>(null);      // what is being typed; null shows the time itself
  const commit = () => { const n = typed === null ? null : parse(typed); if (n !== null) onSet(Math.round(n)); setTyped(null); };
  return (
    <label className="range2-time">{label}
      <input className="time" inputMode="numeric" value={typed ?? hms(sec)} aria-label={`${label} time, hours:minutes:seconds`}
        onChange={(e) => setTyped(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }} />
    </label>
  );
}

// Which part of the video to search: two handles over its length, and the same two times as editable text.
// `null` is the whole video. Both handles are native sliders, so arrows, Page Up/Down, Home and End work.
export function RangeSlider({ duration, value, onChange, gap }: { duration: number; value: Span | null; onChange: (v: Span | null) => void; gap: number }) {
  const total = Math.max(1, Math.floor(duration)), least = Math.min(gap, total);
  const start = Math.min(value?.start ?? 0, total - least), end = Math.max(Math.min(value?.end ?? total, total), start + least);
  const set = (s: number, e: number) => {
    s = Math.max(0, Math.min(s, total - least));
    e = Math.min(total, Math.max(e, s + least));
    onChange(s <= 0 && e >= total ? null : { start: s, end: e });
  };
  const pct = (sec: number) => `${(sec / total) * 100}%`;
  return (
    <div className="range2-wrap">
      <div className="range2" style={{ "--a": pct(start), "--b": pct(end) } as React.CSSProperties}>
        <input type="range" min={0} max={total} step={1} value={start} aria-label="Start of the part to search" aria-valuetext={hms(start)}
          style={{ zIndex: start > total / 2 ? 3 : 2 }} onChange={(e) => set(Math.min(+e.target.value, end - least), end)} />
        <input type="range" min={0} max={total} step={1} value={end} aria-label="End of the part to search" aria-valuetext={hms(end)}
          style={{ zIndex: 2 }} onChange={(e) => set(start, Math.max(+e.target.value, start + least))} />
      </div>
      <div className="range2-ends">
        <TimeField label="Start" sec={start} onSet={(n) => set(Math.min(n, end - least), end)} />
        <span className="muted small">{value ? `${hms(end - start)} of ${hms(total)} selected` : "The whole video"}</span>
        <TimeField label="End" sec={end} onSet={(n) => set(start, Math.max(n, start + least))} />
      </div>
    </div>
  );
}
