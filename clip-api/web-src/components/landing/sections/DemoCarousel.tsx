"use client";
import { useRef, useState } from "react";
import { ComingSoonBadge } from "../../ComingSoonBadge";
import { CaptionStyles } from "../demos/CaptionStyles";
import { DeadAir } from "../demos/DeadAir";
import { HookText } from "../demos/HookText";
import { useInView } from "../demos/motion";
import { Reframe } from "../demos/Reframe";
import { BRollSoon, VoiceSoon } from "../demos/Soon";
import { VodToClips } from "../demos/VodToClips";
import { linkPhrase } from "@/lib/platforms";

type Card = { id: string; tab: string; title: string; text: string; tone: string; soon?: boolean; Demo: (p: { play: boolean }) => React.ReactNode };

// The hero's demo cards. Built features first; the last ones are not built yet and say so on the card.
const CARDS: Card[] = [
  { id: "clips", tab: "Clips", title: "A stream in, ranked clips out", tone: "#1b2729",
    text: `Drop a VOD or paste ${linkPhrase()}. ClutchClips finds the moments worth posting and cuts them into vertical clips, best first, each with an AI rating.`,
    Demo: VodToClips },
  { id: "captions", tab: "Captions", title: "Caption styles", tone: "#2a2420",
    text: "Word-by-word captions burned into the clip, in twelve styles. Pick one per clip or set it once in a template.",
    Demo: CaptionStyles },
  { id: "reframe", tab: "Reframe", title: "Wide gameplay to vertical", tone: "#24212e",
    text: "Finds your facecam on its own and builds the vertical clip around it: camera over gameplay, gameplay only, or a small camera inset.",
    Demo: Reframe },
  { id: "hook", tab: "Hook", title: "A hook on the opening", tone: "#1c2333",
    text: "The AI writes a short opening line from what was said and puts it on screen for the first seconds. Change the words, tone or position.",
    Demo: HookText },
  { id: "dead-air", tab: "Dead air", title: "Dead air, cut", tone: "#202224",
    text: "Silences and filler words come out of every clip, so it moves at the pace of the stream's best moments.",
    Demo: DeadAir },
  { id: "broll", tab: "B-roll", title: "AI B-roll", tone: "#1d1d21", soon: true, text: "Cutaway shots placed over the slower parts of a clip.", Demo: BRollSoon },
  { id: "voice", tab: "Voice", title: "Voiced hooks", tone: "#1d1d21", soon: true, text: "Your hook line read out loud in a voice you pick.", Demo: VoiceSoon },
];

// Where card i sits relative to the one shown: -1 left neighbour, 1 right, wrapping around the ends.
const offsetOf = (i: number, at: number, n: number) => { const d = (((i - at) % n) + n) % n; return d > n / 2 ? d - n : d; };

export function DemoCarousel() {
  const [at, setAt] = useState(0);
  const n = CARDS.length, box = useRef<HTMLDivElement>(null), seen = useInView(box, "0px");
  const touch = useRef<number | null>(null);
  const go = (to: number) => setAt(((to % n) + n) % n);

  // Cards two or more places away are off screen. The farthest ones wrap from one end to the other, so they
  // are hidden and jump there instead of sliding across the screen.
  const offsets = CARDS.map((_, i) => offsetOf(i, at, n));
  const shown = CARDS[at];

  return (
    <section aria-roledescription="carousel" aria-label="What ClutchClips does" className="w-full overflow-x-clip py-0">
      <div ref={box} className="relative mx-auto h-[580px] [--gap:24px] [--w:min(880px,calc(100vw-240px))] narrow:h-[640px] narrow:[--gap:12px] narrow:[--w:calc(100vw-40px)]"
        onKeyDown={(e) => { if (e.key === "ArrowLeft") go(at - 1); if (e.key === "ArrowRight") go(at + 1); }}
        onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
        onTouchEnd={(e) => { const x = touch.current; touch.current = null; if (x === null) return;
          const dx = e.changedTouches[0].clientX - x; if (Math.abs(dx) > 40) go(at + (dx < 0 ? 1 : -1)); }}>
        {CARDS.map((c, i) => {
          const o = offsets[i], here = o === 0;
          return (
            <div key={c.id} role="group" aria-roledescription="slide" aria-label={`${i + 1} of ${n}: ${c.title}`} aria-hidden={!here} inert={!here}
              className={`absolute left-1/2 top-0 h-full w-[var(--w)] overflow-hidden rounded-stage p-8 shadow-card narrow:p-4 ${Math.abs(o) > 2 ? "" : "transition-[transform,opacity,visibility] duration-500 ease-[cubic-bezier(.2,.8,.2,1)]"} ${here ? "" : "opacity-45"}`}
              style={{ transform: `translateX(calc(-50% + ${o} * (var(--w) + var(--gap))))`, visibility: Math.abs(o) > 2 ? "hidden" : undefined,
                background: `radial-gradient(120% 90% at 50% 0%, ${c.tone}, #0e0f12 80%)` }}>
              {Math.abs(o) <= 2 && <c.Demo play={here && seen} />}
            </div>
          );
        })}
        {([["Previous", -1, "left-[calc(50%-var(--w)/2-68px)]"], ["Next", 1, "right-[calc(50%-var(--w)/2-68px)]"]] as const).map(([label, d, side]) => (
          <button key={label} type="button" aria-label={`${label}: ${CARDS[(at + d + n) % n].title}`} onClick={() => go(at + d)}
            className={`absolute top-1/2 z-10 grid h-11 w-11 -translate-y-1/2 cursor-pointer place-items-center rounded-full border border-white/10 bg-black/60 text-white backdrop-blur transition-colors hover:bg-white hover:text-black narrow:hidden ${side}`}>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {d < 0 ? <path d="M19 12H5m6-6-6 6 6 6" /> : <path d="M5 12h14m-6-6 6 6-6 6" />}</svg>
          </button>
        ))}
      </div>

      <div className="mx-auto mt-6 flex max-w-[1040px] flex-col items-center gap-4 px-5">
        <div className="flex flex-wrap items-center justify-center gap-2" role="group" aria-label="Choose a demo">
          <button type="button" aria-label="Previous demo" onClick={() => go(at - 1)} className="hidden h-9 w-9 cursor-pointer place-items-center rounded-full border border-white/10 bg-white/5 text-white narrow:grid">‹</button>
          {CARDS.map((c, i) => (
            <button key={c.id} type="button" aria-pressed={i === at} onClick={() => go(i)}
              className={`cursor-pointer rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors narrow:hidden ${i === at ? "border-white bg-white text-black" : "border-white/10 bg-white/5 text-white/75 hover:text-white"}`}>
              {c.tab}{c.soon && <ComingSoonBadge short className="ml-1.5" />}
            </button>
          ))}
          <span className="hidden text-[13px] tabular-nums text-white/60 narrow:inline">{at + 1} / {n}</span>
          <button type="button" aria-label="Next demo" onClick={() => go(at + 1)} className="hidden h-9 w-9 cursor-pointer place-items-center rounded-full border border-white/10 bg-white/5 text-white narrow:grid">›</button>
        </div>
        <div className="max-w-[640px] text-center" aria-live="polite">
          <p className="flex items-center justify-center gap-2 text-title text-fg">{shown.title}{shown.soon && <ComingSoonBadge />}</p>
          <p className="mt-1 text-body-lg text-fg-2">{shown.text}</p>
        </div>
      </div>
    </section>
  );
}
