"use client";
import { useEffect, useRef, useState } from "react";
import { CAPTION_STYLES, Caption, CaptionStyle, styleName } from "./Caption";
import { Footage, useItem, useWords } from "./Footage";
import { SplitClip } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

const WORDS = ["NO", "WAY", "HE", "JUST", "HIT", "THAT", "JUMP"], KEYS = [1, 6];
const PER_STYLE = 8;          // words said before the demo moves to the next style

// The caption styles, playing on a clip. It walks through every style until the visitor picks one.
export function CaptionStyles({ play }: { play: boolean }) {
  const reduced = useReducedMotion(), tick = useTicker(play && !reduced, 380);
  const [picked, setPicked] = useState<CaptionStyle | null>(null);
  const style = picked ?? CAPTION_STYLES[Math.floor(tick / PER_STYLE) % CAPTION_STYLES.length].id;
  const list = useRef<HTMLUListElement>(null);
  // Real footage: the engine's own render of this style when there is one; otherwise the clip without captions,
  // with the style drawn over it from the clip's own words.
  const rendered = useItem("captions", style), plain = useItem("captions", "plain"), said = useWords("captions", plain);
  const real = said.length >= 4;
  const words = real ? said.slice(0, 16).map((w) => w.text.replace(/[^\p{L}\p{N}'!?]/gu, "").toUpperCase()).filter(Boolean) : WORDS;
  const keys = real ? [] : KEYS;

  // Keep the style being shown in the middle of the list, scrolling the list only (never the page).
  useEffect(() => {
    const ul = list.current, li = ul?.querySelector<HTMLElement>(`[data-style="${style}"]`);
    if (!ul || !li || !play || picked) return;
    const wide = getComputedStyle(ul).flexDirection === "row";
    ul.scrollTo(wide ? { left: li.offsetLeft - ul.clientWidth / 2 + li.clientWidth / 2, behavior: "smooth" }
      : { top: li.offsetTop - ul.clientHeight / 2 + li.clientHeight / 2, behavior: "smooth" });
  }, [style, play, picked]);

  return (
    <div className={`${s.demo} flex h-full items-center justify-center gap-10 narrow:flex-col narrow:gap-4`} data-play={play}>
      <div className="relative aspect-[9/16] h-[440px] shrink-0 overflow-hidden rounded-[16px] ring-1 ring-white/10 narrow:h-[300px]">
        {rendered ? <Footage key={rendered.id} section="captions" item={rendered} play={play} /> : <>
          {plain ? <Footage section="captions" item={plain} play={play} /> : <SplitClip game="gta" />}
          <span className="absolute inset-x-2 top-[33%] z-10 -translate-y-1/2 text-center text-[22px] narrow:text-[16px]">
            <Caption style={style} words={words} keys={keys} at={reduced ? 1 : tick} />
          </span>
        </>}
      </div>

      <div className="flex h-[440px] w-[300px] flex-col overflow-hidden rounded-[16px] bg-black/35 ring-1 ring-white/10 narrow:h-auto narrow:w-full">
        <p className="flex items-baseline justify-between border-b border-white/10 px-4 py-3 text-[14px] font-semibold">
          Caption style<span className="text-[12px] font-normal text-white/50">{CAPTION_STYLES.length} styles</span></p>
        <ul ref={list} className="list-none flex flex-1 flex-col gap-2 overflow-y-auto p-3 narrow:flex-row narrow:overflow-x-auto narrow:overflow-y-hidden">
          {CAPTION_STYLES.map((c) => {
            const on = c.id === style;
            return (
              <li key={c.id} data-style={c.id} className="narrow:w-[112px] narrow:shrink-0">
                <button type="button" aria-pressed={on} onClick={() => setPicked(on && picked ? null : c.id)}
                  className={`flex w-full cursor-pointer flex-col items-center gap-1 rounded-[10px] border-0 px-2 py-2.5 text-white transition-colors ${on ? `${s.glow} bg-white/15` : "bg-white/5 hover:bg-white/10"}`}>
                  <span className="flex h-[30px] items-center text-[15px]"><Caption style={c.id} words={["NO", "WAY", "BRO"]} keys={[1]} at={1} /></span>
                  <span className="text-[12px] text-white/70">{styleName(c.id)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
