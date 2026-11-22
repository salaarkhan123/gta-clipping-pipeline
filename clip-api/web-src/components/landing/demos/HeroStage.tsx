"use client";
import { useEffect, useState } from "react";
import { PlatformBadge, PlatformId } from "@/components/ui/PlatformGlyph";
import { Score } from "@/components/ui/Score";
import { pastePrompt } from "@/lib/platforms";
import { LinkIcon } from "./Bits";
import { aiRated, Credits, Footage, Item, useItem, useItems } from "./Footage";
import { useReducedMotion } from "./motion";

// The hero's first slide, a decorative walkthrough of the product on approved footage: the long video, the import
// field under it, a pointing hand that moves to "Get clips" and presses it, the video being read, then the finished
// clips coming out of the video card and spreading into a row, each in its platform's shape with that platform's
// badge on its top edge and its AI rating bottom-left. It loops while its slide is shown and on screen; the row
// stays in view (dimmed) between passes so the card is never empty. Under prefers-reduced-motion it is the still
// end state. The real field is the one above the stage.
// Every size is a multiple of --u (1% of the stage's width; larger on a phone), so the slide scales with the stage.

type Phase = "clips" | "out" | "move" | "press" | "read";
const NEXT: Record<Phase, [Phase, number]> = { clips: ["out", 4600], out: ["move", 400], move: ["press", 1300], press: ["read", 320], read: ["clips", 1000] };
const SHAPE: Record<string, string> = { "16:9": "aspect-video", "9:16": "aspect-[9/16]", "4:5": "aspect-[4/5]", "1:1": "aspect-square" };
const u = (n: number) => `calc(var(--u) * ${n})`;

const clock = (sec: number) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`;
};

// Our own pointing-hand pointer: white with a dark outline, the fingertip at the top.
export function HandPointer() {
  return (
    <svg viewBox="0 0 32 32" className="block h-full w-full drop-shadow-[0_2px_5px_rgba(0,0,0,.55)]">
      <path fill="#fff" stroke="#111" strokeWidth="1.6" strokeLinejoin="round"
        d="M12 3.5a2 2 0 0 1 4 0v9.2l1.2.2a2 2 0 0 1 3.6.9 2 2 0 0 1 3.4 1.1 1.9 1.9 0 0 1 2.8 1.7v5.4c0 4.4-3 8-7.4 8h-3.2c-2.6 0-4.4-1.2-5.8-3.3l-4.4-6.6a2 2 0 0 1 3.1-2.5l2.7 2.8V3.5Z" />
      <path fill="none" stroke="#111" strokeWidth="1.3" strokeLinecap="round" d="M16 12.7v4M19.8 13.6v3.4M23.2 14.9v2.6" />
    </svg>
  );
}

function usePhase(run: boolean): Phase {
  const [phase, setPhase] = useState<Phase>("clips");
  useEffect(() => {
    if (!run) return;
    const [next, ms] = NEXT[phase];
    const t = setTimeout(() => setPhase(next), ms);
    return () => clearTimeout(t);
  }, [phase, run]);
  return phase;
}

export function HeroStage({ play }: { play: boolean }) {
  const reduced = useReducedMotion();
  const moving = usePhase(play && !reduced);
  const phase: Phase = reduced ? "clips" : moving;
  const vod = useItem("hero-long-video", "vod");
  const tiles = useItems("hero-clean");
  const shown = phase === "clips", pressed = phase === "press", aimed = phase === "move" || pressed;
  const mid = (tiles.length - 1) / 2;

  return (
    <div className="relative flex h-full flex-col items-center justify-center [--u:1cqw] narrow:[--u:1.72cqw]" style={{ gap: u(1.6) }} aria-hidden="true">
      <div className="relative z-10 aspect-video flex-none overflow-hidden bg-black shadow-[0_10px_30px_rgba(0,0,0,.35)]" style={{ width: u(34), borderRadius: u(1.2) }}>
        {vod && <Footage section="hero-long-video" item={vod} play={play} />}
        <span className={`absolute inset-y-0 w-[18%] bg-gradient-to-r from-transparent via-lime/30 to-transparent transition-[left] ease-linear
          ${phase === "read" ? "left-full duration-[950ms]" : "left-[-18%] duration-0"}`} />
        {vod?.duration_sec ? <span className="absolute rounded-[6px] bg-black/70 font-medium tabular-nums text-white"
          style={{ right: u(.6), bottom: u(.6), padding: `${u(.2)} ${u(.6)}`, fontSize: u(1.15) }}>{clock(vod.duration_sec)}</span> : null}
      </div>

      <div className="relative z-10 flex flex-none items-center rounded-pill bg-black/45 shadow-[inset_0_0_0_1px_rgba(255,255,255,.1)]"
        style={{ width: u(46), height: u(4.8), paddingLeft: u(1.7), paddingRight: u(.5), gap: u(.9) }}>
        <span className="flex-none text-white/55" style={{ width: u(1.7), height: u(1.7) }}><LinkIcon className="block h-full w-full" /></span>
        <span className="min-w-0 flex-1 truncate text-left text-white/70" style={{ fontSize: u(1.5) }}>{pastePrompt()}</span>
        {/* The stage's button is the logo's green; the page's real button above stays white. */}
        <span className={`flex-none rounded-pill font-medium text-ink transition-[transform,background-color] duration-fast ease-out ${pressed ? "scale-[.94] bg-[#9fe02f]" : "bg-lime"}`}
          style={{ fontSize: u(1.5), padding: `${u(.95)} ${u(1.8)}`, lineHeight: 1.2 }}>Get clips</span>
        {!reduced && <span className="pointer-events-none absolute z-20 origin-[44%_6%] will-change-transform"
          style={{ width: u(3.6), height: u(3.6), right: u(2.4), top: u(2.1), opacity: aimed ? 1 : 0,
            // One eased glide on the compositor (transform only), a short settle, then a small press.
            transform: aimed ? `translate3d(0, 0, 0) scale(${pressed ? .88 : 1})` : "translate3d(9cqw, 12cqw, 0) scale(1)",
            transition: pressed ? "transform 140ms cubic-bezier(.3,0,.2,1)" : aimed ? "transform 820ms cubic-bezier(.45,.05,.2,1), opacity 260ms ease-out" : "opacity 200ms ease-out, transform 0ms 220ms" }}><HandPointer /></span>}
      </div>

      <ol className="m-0 flex list-none items-start justify-center p-0" style={{ gap: u(1.2), marginTop: u(2.4), height: u(19.5) }}>
        {tiles.map((c: Item, i) => (
          <li key={c.id} style={{ height: u(19.5), transitionDelay: shown ? `${i * 80}ms` : "0ms",
            transform: shown ? "none" : phase === "read" ? `translate(${u((mid - i) * 13)}, ${u(-21)}) scale(.3)` : "none" }}
            className={`relative flex-none ${SHAPE[c.aspect || "9:16"]} ease-out ${c.aspect === "16:9" ? "narrow:hidden" : ""}
              ${shown ? "opacity-100 transition-[opacity,transform] duration-[620ms]" : phase === "read" ? "opacity-0 transition-none" : "opacity-30 transition-opacity duration-slow"}`}>
            <span className="absolute left-1/2 top-0 z-10 block -translate-x-1/2 -translate-y-1/2" style={{ width: u(4), height: u(4) }}>
              <PlatformBadge id={c.platform as PlatformId} className="h-full w-full" /></span>
            <span className="absolute inset-0 overflow-hidden bg-white/[.04]" style={{ borderRadius: u(1.1) }}>
              <Footage section="hero-clean" item={c} play={play && shown} />
              {aiRated(c) && <Score value={c.rating!} kind="ai" size="sm" className="absolute bottom-[6px] left-[6px] z-10" />}
            </span>
          </li>
        ))}
      </ol>
      <Credits items={[vod, ...tiles]} className="m-0" />
    </div>
  );
}
