"use client";
import { Caption, sampleWords } from "./Caption";
import { Credits, Footage, useItem, useItems } from "./Footage";
import { Gameplay } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

// The on-screen hook: a line the AI writes from what was said, near-black on lime (captions.py HOOK_TEXT,
// HOOK_BOX), at the start of the clip for 2.5 s unless set otherwise. Text only: there is no voice.
// The clip is one clear subject: NICKMERCS over the Warzone truck (hook-4; hook-3 shows an in-game chat bubble with a
// slur). Otherwise the first non-Fortnite clip.
const HOOK = "He tried the bridge jump. Twice.";
const SAMPLE = sampleWords(["watch", "this", "one", "more", "time"]);
const TONES = ["Serious", "Casual", "Humorous", "Dramatic", "Excited", "Calm"];   // 6 of the 13 hook styles

function pickHook(items: ReturnType<typeof useItems>) {
  const preferred = items.find((i) => i.id === "hook-4")
    || items.find((i) => i.game && !/fortnite/i.test(i.game))
    || items.find((i) => i.id === "hook-1")
    || null;
  return preferred;
}

export function HookText({ play }: { play: boolean }) {
  const reduced = useReducedMotion(), tick = useTicker(play && !reduced, 420);
  const items = useItems("hook");
  const fallback = useItem("hook", "hook-4");
  const real = pickHook(items) || fallback;
  const hook = real?.hook || HOOK;
  return (
    // The clip is 75% of the stage's height (450 of 600) and the panel is drawn larger to match; the two are centred
    // on each other, with the clip's timeline and credit hanging under it.
    <div className={`${s.demo} flex h-full items-center justify-center gap-12 narrow:flex-col-reverse narrow:gap-4`} data-play={play}>
      <div className="flex w-[396px] flex-col gap-5 rounded-[18px] bg-black/35 p-6 ring-1 ring-white/10 narrow:w-full narrow:gap-3 narrow:p-4" aria-hidden="true">
        <p className="text-[16px] font-semibold">Hook</p>
        <div className="grid gap-2">
          <span className="text-[13.5px] text-white/55">Hook text <span className="text-white/40">· written by the AI</span></span>
          <span className="rounded-[11px] bg-white/5 px-3.5 py-3 text-[16px] text-white ring-1 ring-white/10">{hook}<span className={s.caret} /></span>
        </div>
        <div className="grid gap-2">
          <span className="text-[13.5px] text-white/55">Hook style</span>
          <div className="flex flex-wrap gap-2">
            {TONES.map((t) => <span key={t} className={`rounded-full px-3 py-1.5 text-[13.5px] ${t === "Excited" ? "bg-lime font-semibold text-ink" : "bg-white/5 text-white/70 ring-1 ring-white/10"}`}>{t}</span>)}
            <span className="px-1 py-1.5 text-[13.5px] text-white/45">+7 more</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3.5 narrow:hidden">
          <div className="grid gap-2"><span className="text-[13.5px] text-white/55">Position</span>
            <span className="flex rounded-[11px] bg-white/5 p-1 text-[13.5px] ring-1 ring-white/10"><b className="flex-1 rounded-[8px] bg-white/15 py-1.5 text-center font-semibold">Beginning</b><span className="flex-1 py-1.5 text-center text-white/60">End</span></span></div>
          <div className="grid gap-2"><span className="text-[13.5px] text-white/55">On screen</span>
            <span className="rounded-[11px] bg-white/5 px-3.5 py-2 text-[14.5px] ring-1 ring-white/10">2.5 s</span></div>
        </div>
      </div>

      <figure className="relative m-0">
        <div className="relative aspect-[9/16] h-[450px] overflow-hidden rounded-[18px] ring-1 ring-white/10 narrow:h-[230px]">
          {real ? <Footage section="hook" item={real} play={play} /> : <>
            <Gameplay game="gta" label={false} />
            <span className={`${s.hook} absolute inset-x-[8%] top-[11%] rounded-[8px] bg-lime px-2.5 py-1.5 text-center text-[17px] font-extrabold leading-tight text-ink narrow:text-[12px]`}>{HOOK}</span>
            <span className="absolute inset-x-2 top-[74%] text-center text-[22px] narrow:text-[16px]">
              <Caption style="impact" words={SAMPLE} at={reduced ? 0 : tick % SAMPLE.length} />
            </span>
          </>}
        </div>
        <figcaption className="absolute inset-x-0 top-full flex flex-col items-center gap-2 pt-3 narrow:static">
          <span className="relative h-1.5 w-full overflow-hidden rounded-full bg-white/10" aria-hidden="true">
            <span className="absolute inset-y-0 left-0 w-1/2 rounded-full bg-lime/60" />
            <span className={`${s.hookbar} absolute inset-y-[-3px] w-0.5 bg-white`} />
          </span>
          <span className="whitespace-nowrap text-[12px] text-white/55 narrow:hidden">Hook on screen for the first 2.5 s</span>
          <Credits items={[real]} />
        </figcaption>
      </figure>
    </div>
  );
}
