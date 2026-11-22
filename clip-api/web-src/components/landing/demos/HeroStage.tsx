"use client";
import { useEffect, useMemo, useState } from "react";
import { PlatformBadge, PlatformId } from "@/components/ui/PlatformGlyph";
import { Score } from "@/components/ui/Score";
import { mediaUrl } from "@/lib/media";
import { pastePrompt } from "@/lib/platforms";
import { LinkIcon } from "./Bits";
import { aiRated, Credits, Footage, Item, useItems } from "./Footage";
import { useReducedMotion } from "./motion";
import st from "./demos.module.css";

// The hero's first slide, a decorative walkthrough of the product on approved footage, one game per pass: that
// game's long video comes in, a pointing hand moves to "Get clips" and presses it, the video is read, then the
// finished clips come out of the video card and spread into a row, each in its platform's shape with that
// platform's badge on its top edge and, when the AI judge rated the moment, its AI rating bottom-left. Then the
// next game. It runs only while its slide is shown and on screen; under prefers-reduced-motion it is the first
// game's finished row, still. The real field is the one above the stage.
// Every size is a multiple of --u (1% of the stage's width; larger on a phone), so the slide scales with the stage.

// One game's set from public/media/hero-clean/manifest.json (scripts/make-hero-clean.py): its source and its clips.
type HeroItem = Item & { set?: string; role?: "source" | "tile"; source_duration_sec?: number };
type HeroSet = { id: string; vod: HeroItem; tiles: HeroItem[] };

function setsOf(items: HeroItem[]): HeroSet[] {
  const sets: HeroSet[] = [];
  for (const it of items) {
    if (it.role === "source") sets.push({ id: it.set ?? it.id, vod: it, tiles: [] });
    else if (it.role === "tile" && sets.length && sets[sets.length - 1].id === it.set) sets[sets.length - 1].tiles.push(it);
  }
  return sets.filter((s) => s.tiles.length);
}

// "clips": the row is out and holds; "out": the row and the video leave; "in": the next game's video arrives; then
// the hand moves, presses, and the video is read.
type Phase = "clips" | "out" | "in" | "move" | "press" | "read";
const NEXT: Record<Phase, [Phase, number]> = { clips: ["out", 4600], out: ["in", 450], in: ["move", 650], move: ["press", 1300], press: ["read", 320], read: ["clips", 1000] };
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

// The phase and which game is shown; the game moves on as each pass begins.
function useLoop(run: boolean, count: number): { phase: Phase; at: number } {
  const [s, setS] = useState<{ phase: Phase; at: number }>({ phase: "clips", at: 0 });
  useEffect(() => {
    if (!run) return;
    const [next, ms] = NEXT[s.phase];
    const t = setTimeout(() => setS(({ at }) => ({ phase: next, at: next === "in" ? (at + 1) % Math.max(count, 1) : at })), ms);
    return () => clearTimeout(t);
  }, [s, run, count]);
  return s;
}

// The next game's media, fetched while this one plays, so its video and clips appear without a blank frame.
function Preload({ set }: { set: HeroSet | undefined }) {
  if (!set) return null;
  return (
    <span className="pointer-events-none absolute h-0 w-0 overflow-hidden opacity-0" aria-hidden="true">
      {[set.vod, ...set.tiles].map((i) => <span key={i.id}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {i.poster && <img src={mediaUrl("hero-clean", i.poster)} alt="" decoding="async" />}
        <video src={mediaUrl("hero-clean", i.src)} muted playsInline preload="auto" />
      </span>)}
    </span>
  );
}

export function HeroStage({ play }: { play: boolean }) {
  const reduced = useReducedMotion();
  const items = useItems("hero-clean") as HeroItem[];
  const sets = useMemo(() => setsOf(items), [items]);
  const loop = useLoop(play && !reduced && sets.length > 0, sets.length);
  const phase: Phase = reduced ? "clips" : loop.phase;
  const set = sets[reduced ? 0 : loop.at % Math.max(sets.length, 1)];
  const vod = set?.vod ?? null, tiles = set?.tiles ?? [];
  const shown = phase === "clips", hidden = phase === "in" || phase === "move" || phase === "press" || phase === "read";
  const pressed = phase === "press", aimed = phase === "move" || pressed;
  const mid = (tiles.length - 1) / 2;

  return (
    <div className="relative flex h-full flex-col items-center justify-center [--u:1cqw] narrow:[--u:1.72cqw]" style={{ gap: u(1.6) }} aria-hidden="true">
      <div className={`relative z-10 aspect-video flex-none overflow-hidden bg-black shadow-[0_10px_30px_rgba(0,0,0,.35)] transition-opacity duration-[400ms] ease-out
          ${phase === "out" ? "opacity-40" : "opacity-100"}`} style={{ width: u(34), borderRadius: u(1.2) }}>
        {/* The next game's video comes in over the last one (keyed, so it plays its entrance once per game). */}
        {vod && <span key={vod.id} className={`absolute inset-0 ${reduced ? "" : st.swap}`}><Footage section="hero-clean" item={vod} play={play} /></span>}
        <span className={`absolute inset-y-0 w-[18%] bg-gradient-to-r from-transparent via-lime/30 to-transparent transition-[left] ease-linear
          ${phase === "read" ? "left-full duration-[950ms]" : "left-[-18%] duration-0"}`} />
        {vod?.source_duration_sec ? <span className="absolute rounded-[6px] bg-black/70 font-medium tabular-nums text-white"
          style={{ right: u(.6), bottom: u(.6), padding: `${u(.2)} ${u(.6)}`, fontSize: u(1.15) }}>{clock(vod.source_duration_sec)}</span> : null}
      </div>

      <div className="relative z-10 flex flex-none items-center rounded-pill bg-black/45 shadow-[inset_0_0_0_1px_rgba(255,255,255,.1)]"
        style={{ width: u(46), height: u(4.8), paddingLeft: u(1.7), paddingRight: u(.5), gap: u(.9) }}>
        <span className="flex-none text-white/55" style={{ width: u(1.7), height: u(1.7) }}><LinkIcon className="block h-full w-full" /></span>
        <span className="min-w-0 flex-1 truncate text-left text-white/70" style={{ fontSize: u(1.5) }}>{pastePrompt()}</span>
        {/* The stage's button is the logo's green; the page's real button above stays white. */}
        <span className={`flex-none rounded-pill font-medium text-ink transition-[transform,background-color] duration-fast ease-out ${pressed ? "scale-[.94] bg-[#9fe02f]" : "bg-lime"}`}
          style={{ fontSize: u(1.5), padding: `${u(.95)} ${u(1.8)}`, lineHeight: 1.2 }}>Get clips</span>
        {!reduced && <span className="pointer-events-none absolute z-20 origin-[44%_6%] will-change-transform" data-hand={aimed ? "aimed" : "away"}
          style={{ width: u(3.6), height: u(3.6), right: u(2.4), top: u(2.1), opacity: aimed ? 1 : 0,
            // One eased glide on the compositor (transform only), a short settle, then a small press. Once faded out it
            // jumps back to the start; Chrome never runs a 0 ms transition that has a delay, so the jump takes 1 ms.
            transform: aimed ? `translate3d(0, 0, 0) scale(${pressed ? .88 : 1})` : "translate3d(9cqw, 12cqw, 0) scale(1)",
            transition: pressed ? "transform 140ms cubic-bezier(.3,0,.2,1)" : aimed ? "transform 820ms cubic-bezier(.45,.05,.2,1), opacity 260ms ease-out" : "opacity 200ms ease-out, transform 1ms linear 220ms" }}><HandPointer /></span>}
      </div>

      <ol className="m-0 flex list-none items-start justify-center p-0" style={{ gap: u(1.2), marginTop: u(2.4), height: u(19.5) }} data-set={set?.id}>
        {tiles.map((c, i) => (
          <li key={c.id} style={{ height: u(19.5), transitionDelay: shown ? `${i * 80}ms` : "0ms",
            transform: hidden ? `translate(${u((mid - i) * 13)}, ${u(-21)}) scale(.3)` : "none" }}
            className={`relative flex-none ${SHAPE[c.aspect || "9:16"]} ease-out ${c.aspect === "16:9" ? "narrow:hidden" : ""}
              ${shown ? "opacity-100 transition-[opacity,transform] duration-[620ms]" : hidden ? "opacity-0 transition-none" : "opacity-0 transition-opacity duration-[400ms]"}`}>
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
      {!reduced && play && <Preload set={sets[(loop.at + 1) % Math.max(sets.length, 1)]} />}
    </div>
  );
}
