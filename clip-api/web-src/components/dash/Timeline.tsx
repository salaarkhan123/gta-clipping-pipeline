"use client";
import { useState } from "react";
import { clock } from "@/lib/api";
import { nameOf } from "./ClipCard";

const TIERS: Record<string, string> = { top: "Top pick", strong: "Strong", solid: "Solid", long_shot: "Long shot" };
const describe = (c: any) => `${nameOf(c)} · ${clock(c.start_sec)} to ${clock(c.end_sec)}${c.tier ? ` · ${TIERS[c.tier]}` : ""}`;

// The source video as a strip, with one marker per clip where it was cut from. Picking a marker jumps to its card.
export function Timeline({ duration, clips, onPick }: { duration: number; clips: any[]; onPick: (clip: any) => void }) {
  const [over, setOver] = useState<any>(null);
  const marks = clips.filter((c) => duration > 0 && c.start_sec < duration).sort((a, b) => a.start_sec - b.start_sec);
  const pct = (sec: number) => Math.min(100, Math.max(0, (sec / duration) * 100));
  return (
    <div className="timeline" role="group" aria-label="Where each clip came from">
      <div className="timeline-track">
        {marks.map((c) => (
          <button key={c.id} type="button" className={`mark ${c.tier || ""}`} aria-label={`Go to ${describe(c)}`}
            style={{ left: `${pct(c.start_sec)}%`, width: `${pct(c.end_sec) - pct(c.start_sec)}%` }}
            onClick={() => onPick(c)} onMouseEnter={() => setOver(c)} onMouseLeave={() => setOver(null)}
            onFocus={() => setOver(c)} onBlur={() => setOver(null)} />))}
      </div>
      <div className="timeline-ends" aria-hidden="true"><span>0:00</span><span>{clock(duration)}</span></div>
      <p className="muted timeline-note">{over ? describe(over)
        : marks.length ? `${marks.length} clip${marks.length === 1 ? "" : "s"} on the timeline. Pick a marker to jump to its clip.`
        : "Markers show up here for every clip made from this video."}</p>
    </div>
  );
}
