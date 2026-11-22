"use client";
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "../../ComingSoonBadge";
import { CaptionStyles } from "../demos/CaptionStyles";
import { DeadAir } from "../demos/DeadAir";
import { HeroStage } from "../demos/HeroStage";
import { HookText } from "../demos/HookText";
import { useInView } from "../demos/motion";
import { Reframe } from "../demos/Reframe";
import { BRollSoon, VoiceSoon } from "../demos/Soon";
import { Icon, IconName } from "@/components/dash/Icon";

type Card = { id: string; tab: string; icon: IconName; title: string; text: string; fluid?: boolean; soon?: boolean; tone?: string; Demo: (p: { play: boolean }) => React.ReactNode };

// The stage under the hero: one large card showing the product working, the next and previous cards dimmed at its
// sides, and a row of tabs under it. Only features that work today get a card.
const CARDS: Card[] = [
  { id: "clips", tab: "AI clipping", icon: "scissors", title: "A stream in, ranked clips out", fluid: true,
    text: "Drop in a stream. ClutchClips finds the moments worth posting and cuts them into clips, best first.", Demo: HeroStage },
  { id: "captions", tab: "Captions", icon: "captions", title: "Captions on every word", tone: "radial-gradient(110% 120% at 28% 8%, #5a524c, #37322f 58%, #2a2725)",
    text: "Word-by-word captions burned into the clip. Pick a style per clip, or set it once in your brand kit.", Demo: CaptionStyles },
  { id: "reframe", tab: "Reframe", icon: "reframe", title: "Wide gameplay, framed for vertical",
    text: "Camera over gameplay, gameplay only, or a small camera inset. The layout follows the footage.", Demo: Reframe },
  { id: "hook", tab: "Hook", icon: "hook", title: "A hook on the opening",
    text: "A short opening line written from what was said, on screen for the first seconds.", Demo: HookText },
  { id: "dead-air", tab: "Dead air", icon: "wave", title: "Dead air, cut", tone: "radial-gradient(110% 120% at 70% 0%, #3d4347, #26292b 60%, #1e2021)",
    text: "Silences and filler words come out of every clip, so it moves at the pace of the stream's best moments.", Demo: DeadAir },
  { id: "broll", tab: "B-roll", icon: "image", title: "AI B-roll", soon: true, text: "Cutaway shots placed over the slower parts of a clip.", Demo: BRollSoon },
  { id: "voice", tab: "Voice", icon: "mic", title: "Voiced hooks", soon: true, text: "Your hook line read out loud in a voice you pick.", Demo: VoiceSoon },
];
// The size the older demos were laid out for. They are drawn at it and scaled to the stage.
const DESIGN_W = 1000, DESIGN_H = 600;

// The stage arrows are 48 px round buttons; after a click or on keyboard focus they wear a double ring, white then the logo's green.
// Where card i sits relative to the one shown: -1 left neighbour, 1 right, wrapping around the ends.
const offsetOf = (i: number, at: number, n: number) => { const d = (((i - at) % n) + n) % n; return d > n / 2 ? d - n : d; };

export function DemoCarousel() {
  const [at, setAt] = useState(0), [scale, setScale] = useState(1), [phone, setPhone] = useState(false);
  const n = CARDS.length, box = useRef<HTMLDivElement>(null), seen = useInView(box, "0px");
  const touch = useRef<number | null>(null);
  const go = (to: number) => setAt(((to % n) + n) % n);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => { const w = parseFloat(getComputedStyle(el).getPropertyValue("--w-px")) || el.clientWidth; setScale(Math.min(1, w / DESIGN_W)); setPhone(window.innerWidth <= 860); };
    const ro = new ResizeObserver(fit); ro.observe(el); fit();
    return () => ro.disconnect();
  }, []);
  const shown = CARDS[at];

  return (
    <section aria-roledescription="carousel" aria-label="What ClutchClips does" className="w-full overflow-x-clip py-0">
      {/* The stage is 1000 x 600 at most and keeps that shape as the window narrows; on a phone it is taller. */}
      <div ref={box} className="relative mx-auto aspect-[5/3] w-[min(1000px,calc(100vw-280px))] [--gap:24px] narrow:aspect-[10/11] narrow:w-[calc(100vw-32px)] narrow:[--gap:10px]"
        onKeyDown={(e) => { if (e.key === "ArrowLeft") go(at - 1); if (e.key === "ArrowRight") go(at + 1); }}
        onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
        onTouchEnd={(e) => { const x = touch.current; touch.current = null; if (x === null) return;
          const dx = e.changedTouches[0].clientX - x; if (Math.abs(dx) > 40) go(at + (dx < 0 ? 1 : -1)); }}>
        {CARDS.map((c, i) => {
          const o = offsetOf(i, at, n), here = o === 0, far = Math.abs(o) > 1;
          return (
            <div key={c.id} role="group" aria-roledescription="slide" aria-label={`${i + 1} of ${n}: ${c.title}`} aria-hidden={!here} inert={!here}
              className={`absolute inset-0 overflow-hidden rounded-20 bg-[#171718] shadow-[inset_0_1px_0_rgba(255,255,255,.06)] [container-type:inline-size] ${far ? "" : "transition-[transform,opacity] duration-slow ease-out"} ${here ? "" : "opacity-40"}`}
              style={{ transform: `translateX(calc(${o} * (100% + var(--gap))))`, visibility: far ? "hidden" : undefined, background: c.tone }}>
              {!far && (c.fluid || phone
                ? <div className="h-full w-full p-[2.4cqw] narrow:p-3"><c.Demo play={here && seen} /></div>
                : <div className="absolute left-0 top-0 origin-top-left px-9 py-7" style={{ width: DESIGN_W, height: DESIGN_H, transform: `scale(${scale})` }}><c.Demo play={here && seen} /></div>)}
            </div>
          );
        })}
        {([["Previous", -1, "left-[-72px]"], ["Next", 1, "right-[-72px]"]] as const).map(([label, d, side]) => (
          <button key={label} type="button" aria-label={`${label}: ${CARDS[(at + d + n) % n].title}`} onClick={() => go(at + d)}
            className={`absolute top-1/2 z-10 grid h-12 w-12 -translate-y-1/2 cursor-pointer place-items-center rounded-full border-0 bg-[#2a2a2a] text-white outline-none transition-[background-color,box-shadow] duration-base hover:bg-[#3a3a3a]
              focus:shadow-[0_0_0_2px_#fff,0_0_0_4px_#b8ff3c] narrow:hidden ${side}`}>
            <Icon name="arrow" size={22} className={d < 0 ? "rotate-180" : ""} /></button>
        ))}
      </div>

      <div className="mx-auto mt-8 grid max-w-[1000px] justify-items-center gap-4 px-4 text-center narrow:mt-5">
        {/* Tab buttons measured from the reference: 35 px tall, 10 px radius, 16 px icon, 13.5 px label, 11 px apart;
            a hairline on the unselected ones, the selected one filled. */}
        <div className="flex max-w-full items-center gap-[11px] overflow-x-auto pb-1 [scrollbar-width:none]" role="tablist" aria-label="Choose a demo">
          {CARDS.map((c, i) => (
            <button key={c.id} type="button" role="tab" aria-selected={i === at} onClick={() => go(i)}
              className={`inline-flex h-[35px] flex-none cursor-pointer items-center gap-[9px] rounded-[10px] border border-solid px-3 font-sans text-[13.5px] font-medium text-white transition-colors duration-base
                ${i === at ? "border-transparent bg-[#1c1c1c]" : "border-white/[.12] bg-transparent hover:bg-white/[.05]"}`}>
              <Icon name={c.icon} size={16} />{c.tab}{c.soon && <ComingSoonBadge short />}</button>
          ))}
        </div>
        <p className="m-0 max-w-[620px] text-[15px] leading-[1.5] text-fg-2" aria-live="polite"><span className="font-medium text-fg">{shown.title}{shown.soon && <> <ComingSoonBadge /></>}.</span> {shown.text}</p>
      </div>
    </section>
  );
}
