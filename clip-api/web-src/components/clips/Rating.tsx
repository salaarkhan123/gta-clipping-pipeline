"use client";
import { useEffect, useId, useRef, useState } from "react";
import { coachingFor } from "../../lib/coaching";
import { Rating, ratingOf } from "./model";

// The sub-scores as bars, with per-dimension coaching and the AI's overall reason.
// Shared by the card's pop-over and the player's side panel.
export function RatingParts({ r, compact }: { r: Rating; compact?: boolean }) {
  return (
    <div className="grid gap-[10px]">
      {r.parts.length > 0 ? (
        <ul className="m-0 grid list-none gap-[7px] p-0" aria-label="Sub-scores, out of 100">
          {r.parts.map((p) => {
            const tip = coachingFor(p.key, p.value);
            return (
              <li key={p.key} className="grid gap-[3px]" title={tip ?? undefined}>
                <div className="grid grid-cols-[72px_1fr_28px] items-center gap-[10px] text-[12.5px]">
                  <span className="text-fg-2">{p.label}</span>
                  <span className="h-[5px] overflow-hidden rounded-pill bg-[rgba(255,255,255,.08)]" aria-hidden="true">
                    <span className="block h-full rounded-pill bg-lime" style={{ width: `${Math.max(2, Math.min(100, p.value))}%` }} />
                  </span>
                  <b className="text-right font-mono text-[12px] font-medium tabular-nums text-text">{p.value}</b>
                </div>
                {tip && (
                  <p className={`m-0 pl-[82px] leading-[1.35] text-fg-3 ${compact ? "text-[10.5px] line-clamp-1" : "text-[11.5px]"}`}>
                    {tip}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      ) : <p className="m-0 text-[12.5px] text-fg-2">No sub-scores for this clip.</p>}
      {r.why && !compact && <p className="m-0 text-[12.5px] leading-[1.45] text-soft">{r.why}</p>}
      <p className="m-0 text-[11.5px] leading-[1.45] text-fg-3">
        {r.shown !== null && `${r.shown} is the AI rating scaled across this run, so its best clip sits in the 90s. `}
        The AI rating is the AI's opinion of the clip. It does not say how many views a clip will get.
      </p>
    </div>
  );
}

// The AI rating on a card: the number, and its sub-scores on hover, keyboard focus or a tap.
// A clip the AI did not rate shows its place in the run instead, and says so.
export function RatingBadge({ clip }: { clip: any }) {
  const r = ratingOf(clip);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), tip = useId();
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  if (r.shown === null && r.rank === null) return null;
  return (
    <div ref={box} className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
      onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      <button type="button" aria-expanded={open} aria-describedby={tip} onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        aria-label={r.shown !== null ? `AI rating ${r.shown} out of 100. Show the sub-scores.` : `Not rated by the AI. Number ${r.rank} in this run.`}
        className="flex cursor-pointer items-baseline gap-[3px] rounded-pill border-0 bg-[rgba(0,0,0,.62)] px-[10px] py-[5px] font-sans leading-none text-text shadow-[inset_0_0_0_1px_rgba(255,255,255,.12)] [backdrop-filter:blur(8px)] hover:bg-[rgba(0,0,0,.8)]">
        {r.shown !== null
          ? <><b className="text-[17px] font-semibold tabular-nums tracking-[-0.02em] text-lime">{r.shown}</b><small className="text-[10.5px] text-fg-2">/100</small></>
          : <span className="text-[12px] font-medium tabular-nums">#{r.rank}{r.of ? <span className="text-fg-2"> of {r.of}</span> : null}</span>}
      </button>
      {/* Not laid out while closed, so it never widens a phone's page. On a phone it opens as a sheet at the bottom. */}
      <div id={tip} role="tooltip" className={`absolute bottom-[calc(100%+8px)] left-0 z-20 w-[248px] animate-[rise_.15s_ease-out] rounded-16 border border-solid border-line bg-[rgba(20,20,20,.97)] p-[14px] text-left shadow-pop
        [backdrop-filter:blur(10px)] narrow:fixed narrow:inset-x-4 narrow:bottom-4 narrow:z-50 narrow:w-auto ${open ? "block" : "hidden"}`}>
        <p className="m-0 mb-[10px] flex items-baseline justify-between gap-2 text-[13px] font-semibold">
          {r.shown !== null ? <>AI rating <span className="font-mono text-lime">{r.shown}</span></> : "Not rated by the AI"}
          {r.rank !== null && <span className="text-[11.5px] font-normal text-fg-2">#{r.rank}{r.of ? ` of ${r.of}` : ""} in this run</span>}
        </p>
        {r.shown !== null ? <RatingParts r={r} compact />
          : <p className="m-0 text-[12.5px] leading-[1.45] text-fg-2">Placed by how strongly this moment stood out in the video (loudness, chat, speech).</p>}
      </div>
    </div>
  );
}
