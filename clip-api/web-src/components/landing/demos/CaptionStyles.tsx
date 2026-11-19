"use client";
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "../../ComingSoonBadge";
import { CAPTION_STYLES, Caption, CaptionStyle, sampleWords, styleName, Timed } from "./Caption";
import { Footage, useItem, useWords } from "./Footage";
import { SplitClip } from "./Frames";
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

// The caption presets: the clip without burned-in captions plays on the left, and the chosen style is drawn
// over it live from the clip's own word timings, so a pick changes the caption at once.
export function CaptionStyles({ play }: { play: boolean }) {
  const reduced = useReducedMotion();
  const plain = useItem("captions", "plain"), said = useWords("captions", plain);
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
      <li key={id} data-style={id} className="narrow:w-[120px] narrow:shrink-0">
        <button type="button" aria-pressed={on} onClick={() => setPicked(id)}
          className={`flex w-full cursor-pointer flex-col items-center gap-1.5 border-0 bg-transparent p-0 text-white`}>
          <span className={`flex h-[46px] w-full items-center justify-center overflow-hidden rounded-[10px] px-2 text-[15px] transition-colors narrow:text-[11px] ${on ? `${s.glow} bg-white/15` : "bg-white/[.06] hover:bg-white/10"}`}>{face}</span>
          <span className="text-[12px] text-white/70">{label}</span>
        </button>
      </li>
    );
  };

  return (
    <div className={`${s.demo} flex h-full items-center justify-center gap-10 narrow:flex-col narrow:gap-4`} data-play={play}>
      <div className="relative aspect-[9/16] h-[440px] shrink-0 overflow-hidden rounded-[16px] ring-1 ring-white/10 narrow:h-[290px]">
        {plain ? <Footage section="captions" item={plain} play={play} videoRef={video} /> : <SplitClip game="gta" />}
        {style !== "none" && <span className="absolute inset-x-2 top-[33%] z-10 -translate-y-1/2 text-center text-[22px] narrow:text-[15px]">
          <Caption style={style} words={words} at={at} />
        </span>}
      </div>

      <div className="flex h-[440px] w-[300px] flex-col overflow-hidden rounded-[16px] bg-black/35 ring-1 ring-white/10 narrow:h-auto narrow:w-full">
        <div className="flex items-center gap-4 border-b border-white/10 px-4 py-3 text-[14px]">
          <span className="font-semibold text-white">Presets</span>
          <span className="flex items-center gap-1.5 text-white/45">Font <ComingSoonBadge short /></span>
          <span className="flex items-center gap-1.5 text-white/45">Effects <ComingSoonBadge short /></span>
        </div>
        <ul ref={list} className="flex flex-1 list-none flex-col gap-3 overflow-y-auto p-3 narrow:flex-row narrow:overflow-x-auto narrow:overflow-y-hidden">
          {tile("none", "No captions",
            <svg viewBox="0 0 24 24" className="h-6 w-6 text-white/60" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M5.6 5.6l12.8 12.8" /></svg>)}
          {CAPTION_STYLES.map((c) => tile(c.id, styleName(c.id), <Caption style={c.id} words={words} at={last.current} />))}
        </ul>
      </div>
    </div>
  );
}
