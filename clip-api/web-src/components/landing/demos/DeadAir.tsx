"use client";
import { Caption } from "./Caption";
import { SplitClip } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

// Dead air out: every clip loses its silences over 0.6 s and its filler words (the `tighten` option, on by
// default). Struck-out parts of the transcript are what gets cut; the gaps in the waveform close up.
type Bit = string | { cut: string };
const SAID: Bit[] = ["Okay", "okay,", { cut: "um," }, "watch", "this.", { cut: "1.8 s silence" }, "I'm", "going", "for", "the", "bridge.",
  { cut: "uh," }, "If", "I", "land", "this,", { cut: "2.1 s silence" }, "chat,", "it's", "over.", { cut: "um," }, "NO", "WAY!"];

// The waveform: speech as bars, silence as a flat stretch (its width in %).
const WAVE: (number[] | number)[] = [[5, 9, 7, 12, 6, 10, 8], 9, [7, 11, 14, 9, 13, 6, 10, 12, 8], 7, [6, 9, 13, 15, 11, 8, 12, 14, 9, 7], 10, [10, 15, 18, 14, 16, 12]];

export function DeadAir({ play }: { play: boolean }) {
  const reduced = useReducedMotion(), tick = useTicker(play && !reduced, 400);
  return (
    <div className={`${s.demo} flex h-full flex-col justify-center gap-6 narrow:gap-4`} data-play={play}>
      <div className="flex items-center gap-8">
        <p className="flex-1 text-[22px] leading-[1.75] text-white/90 narrow:text-[16px]" aria-label="A transcript with filler words and silences struck out">
          {SAID.map((b, i) => typeof b === "string" ? <span key={i}>{b} </span>
            : b.cut.includes("silence")
              ? <span key={i} className={`${s.strike} mx-1 inline-block rounded-full bg-white/10 px-2 align-middle text-[13px] text-white/60 line-through`}>{b.cut}</span>
              : <span key={i} className={`${s.strike} text-white/60 line-through`}>{b.cut} </span>)}
        </p>
        <div className="relative aspect-[9/16] h-[300px] shrink-0 overflow-hidden rounded-[14px] ring-1 ring-white/10 narrow:hidden">
          <SplitClip game="gta" />
          <span className="absolute inset-x-2 top-[33%] -translate-y-1/2 text-center text-[17px]">
            <Caption style="pop" words={["I'M", "GOING", "FOR", "THE", "BRIDGE", "NO", "WAY"]} at={reduced ? 1 : tick} />
          </span>
        </div>
      </div>

      <div className="relative flex h-16 items-center gap-[2px] rounded-[12px] bg-black/35 px-3 ring-1 ring-white/10" aria-hidden="true">
        {WAVE.map((w, i) => typeof w === "number"
          ? <span key={i} className={`${s.gap} relative h-px shrink grow-0 bg-white/25`} style={{ ["--w" as string]: `${w}%`, flexBasis: `${w}%` }} />
          : <span key={i} className="flex flex-1 items-center justify-evenly">{w.map((h, j) => <span key={j} className="w-[3px] rounded-full bg-lime/80" style={{ height: `${h * 2.4}px` }} />)}</span>)}
      </div>
      <p className="-mt-3 text-[12px] text-white/55">Silences over 0.6 s and filler words come out of every clip. Turn it off per job.</p>
    </div>
  );
}
