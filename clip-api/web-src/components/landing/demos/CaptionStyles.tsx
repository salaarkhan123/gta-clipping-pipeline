"use client";
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "../../ComingSoonBadge";
import { CAPTION_STYLES, Caption, CaptionStyle, sampleWords, styleName, Timed } from "./Caption";
import { Credits, Footage, useItem, useWords } from "./Footage";
import { SplitClip } from "./Frames";
import { HandPointer } from "./HeroStage";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

// Only until the media pipeline's clip loads: the placeholder frame has no words of its own.
const SAMPLE = sampleWords(["Watch", "this", "jump,", "chat", "no", "way", "he", "landed", "it"]);
const PER_STYLE = 3200;       // ms each style shows while the demo walks through them, until the visitor picks one
type Pick = CaptionStyle | "none";

// The word being said at `t` seconds: the last one started, while it lasts (plus a beat), else -1.
function wordAt(words: Timed[], t: number): number {
  let at = -1;
  for (let i = 0; i < words.length && words[i].start <= t; i++) at = i;
  return at >= 0 && t <= words[at].end + 0.5 ? at : -1;
}

// The caption presets: a wide clip without burned-in captions fills the left of the card, and the chosen style is
// drawn low on it live from the clip's own word timings, so a pick changes the caption at once. The presets run down
// the right side; the pointing hand walks them until the visitor picks one.
export function CaptionStyles({ play }: { play: boolean }) {
  const reduced = useReducedMotion();
  // The wide clip (and its own word timings) when the section has one; the vertical clip otherwise.
  const tall = useItem("captions", "plain"), wide = useItem("captions", "lucia-jason");
  const plain = wide || tall, said = useWords("captions", plain);
  const real = !!plain && said.length > 0, words = real ? said : SAMPLE;

  // Which word is being said: the playing video's own time, or a steady count over the sample words.
  const video = useRef<HTMLVideoElement>(null);
  const [now, setNow] = useState(0);
  const tick = useTicker(play && !reduced && !real, 380);
  useEffect(() => {
    if (!real || !play || reduced) return;
    let raf = 0;
    const step = () => { const v = video.current; if (v) setNow(wordAt(said, v.currentTime)); raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [real, play, reduced, said]);
  const at = reduced ? 0 : real ? now : tick % SAMPLE.length;
  // Tiles keep the last words said through a pause, so they never go blank.
  const last = useRef(0);
  if (at >= 0) last.current = at;

  // The style walks through the list until the visitor picks one.
  const walk = useTicker(play && !reduced, PER_STYLE);
  const [picked, setPicked] = useState<Pick | null>(null);
  const style: Pick = picked ?? CAPTION_STYLES[walk % CAPTION_STYLES.length].id;

  const list = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const ul = list.current, li = ul?.querySelector<HTMLElement>(`[data-style="${style}"]`);
    if (!ul || !li || !play || picked) return;
    const wide = getComputedStyle(ul).flexDirection === "row";
    ul.scrollTo(wide ? { left: li.offsetLeft - ul.clientWidth / 2 + li.clientWidth / 2, behavior: "smooth" }
      : { top: li.offsetTop - ul.clientHeight / 2 + li.clientHeight / 2, behavior: "smooth" });
  }, [style, play, picked]);

  const tile = (id: Pick, label: string, face: React.ReactNode) => {
    const on = id === style;
    return (
      <li key={id} data-style={id} className="relative narrow:w-[150px] narrow:shrink-0">
        <button type="button" aria-pressed={on} onClick={() => setPicked(id)}
          className="flex w-full cursor-pointer flex-col items-center gap-[7px] border-0 bg-transparent p-0 text-white">
          <span className={`flex h-[62px] w-full items-center justify-center overflow-hidden rounded-[12px] bg-white/[.13] px-3 text-[22px] transition-[box-shadow,background-color] duration-base narrow:h-[52px] narrow:text-[17px]
            ${on ? "shadow-[inset_0_0_0_2px_#fff]" : "hover:bg-white/[.18]"}`}>{face}</span>
          <span className="text-[13px] text-white/60">{label}</span>
        </button>
        {/* The pointing hand rests on the preset being shown, until the visitor picks one. */}
        {on && !picked && !reduced && <span aria-hidden="true" className="pointer-events-none absolute right-[18px] top-[34px] z-10 h-8 w-8 animate-[rise_.3s_ease-out] narrow:hidden"><HandPointer /></span>}
      </li>
    );
  };

  // The layout of the slide: a wide clip filling the left of the card with the caption low on it, and the presets
  // panel down the right side, running past the card's bottom edge.
  const clip = wide || plain;
  return (
    <div className={`${s.demo} relative h-full`} data-play={play}>
      <div className="absolute bottom-0 left-0 top-0 flex w-[58%] flex-col justify-center gap-3 narrow:static narrow:w-full">
        <div className={`relative w-full overflow-hidden rounded-[14px] bg-black shadow-[0_18px_50px_rgba(0,0,0,.4)] ${wide ? "aspect-video" : "mx-auto aspect-[9/16] w-[46%]"}`}>
          {clip ? <Footage section="captions" item={clip} play={play} videoRef={video} /> : <SplitClip game="gta" />}
          {style !== "none" && <span className={`absolute inset-x-3 z-10 -translate-y-1/2 text-center ${wide ? "top-[80%] text-[30px] narrow:text-[17px]" : "top-[33%] text-[22px] narrow:text-[15px]"}`}>
            <Caption style={style} words={words} at={at} />
          </span>}
        </div>
        <Credits items={[clip]} className="m-0 !text-left" />
      </div>

      <div className="absolute bottom-[-40px] right-0 top-[6px] flex w-[33%] flex-col overflow-hidden rounded-t-[16px] bg-white/[.09] shadow-[inset_0_1px_0_rgba(255,255,255,.12)] narrow:static narrow:mt-3 narrow:w-full narrow:rounded-[14px]">
        <div className="flex h-[52px] flex-none items-center gap-6 border-0 border-b border-solid border-white/10 px-5 text-[15px]">
          <span className="font-semibold text-white">Presets</span>
          <span className="flex items-center gap-1.5 text-white/45">Font <ComingSoonBadge short /></span>
          <span className="flex items-center gap-1.5 text-white/45">Effects <ComingSoonBadge short /></span>
        </div>
        <ul ref={list} className="m-0 flex flex-1 list-none flex-col gap-[14px] overflow-y-auto p-[18px] pb-16 [scrollbar-width:none] narrow:flex-row narrow:overflow-x-auto narrow:overflow-y-hidden narrow:p-3">
          {tile("none", "No captions",
            <svg viewBox="0 0 24 24" className="h-7 w-7 text-white/70" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M5.6 5.6l12.8 12.8" /></svg>)}
          {CAPTION_STYLES.map((c) => tile(c.id, styleName(c.id), <Caption style={c.id} words={words} at={last.current} />))}
        </ul>
      </div>
    </div>
  );
}
