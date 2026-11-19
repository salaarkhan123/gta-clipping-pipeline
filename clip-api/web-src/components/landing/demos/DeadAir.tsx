"use client";
import { Credits, Footage, useItem, useWords, Word } from "./Footage";
import s from "./demos.module.css";

// Dead air out: every clip loses its silences over 0.6 s and its filler words (the `tighten` option, on by default,
// app/pipeline/__init__.py). Everything here is the media pipeline's clip and its own word timings: the struck-out
// silences are the real gaps between its words, the fillers its real "um"s. With no clip yet the card stays empty.
const SILENCE = 0.6, FILLER = /^(um+|uh+|erm|hmm+)[,.!?]*$/i;

type Bit = { word: Word; cut: boolean } | { gap: number };
function bitsOf(words: Word[]): Bit[] {
  const out: Bit[] = [];
  words.forEach((w, i) => {
    const gap = i ? w.start - words[i - 1].end : 0;
    if (gap >= SILENCE) out.push({ gap });
    out.push({ word: w, cut: FILLER.test(w.text.trim()) });
  });
  return out;
}

export function DeadAir({ play }: { play: boolean }) {
  const clip = useItem("editor", "editor-1"), words = useWords("editor", clip);
  const bits = bitsOf(words), span = words.length ? words[words.length - 1].end - words[0].start : 0;
  return (
    <div className={`${s.demo} flex h-full flex-col justify-center gap-5 narrow:gap-4`} data-play={play}>
      <div className="flex items-center gap-8">
        <p className="min-h-[120px] flex-1 text-[20px] leading-[1.75] text-white/90 narrow:text-[15px]" aria-label="The clip's transcript, with what gets cut struck out">
          {bits.map((b, i) => "gap" in b
            ? <span key={i} className={`${s.strike} mx-1 inline-block rounded-full bg-white/10 px-2 align-middle text-[13px] text-white/60 line-through`}>{b.gap.toFixed(1)} s silence</span>
            : b.cut ? <span key={i} className={`${s.strike} text-white/60 line-through`}>{b.word.text} </span> : <span key={i}>{b.word.text} </span>)}
        </p>
        <div className="relative aspect-[9/16] h-[300px] shrink-0 overflow-hidden rounded-[14px] bg-white/[.04] ring-1 ring-white/10 narrow:hidden">
          {clip && <Footage section="editor" item={clip} play={play} />}
        </div>
      </div>

      {/* The clip's timeline from its word timings: speech as blocks, silences as a flat line that closes up. */}
      <div className="relative flex h-14 items-center rounded-[12px] bg-black/35 px-3 ring-1 ring-white/10" aria-hidden="true">
        {span > 0 && bits.map((b, i) => "gap" in b
          ? <span key={i} className={`${s.gap} h-px shrink-0 bg-white/30`} style={{ ["--w" as string]: `${(b.gap / span) * 100}%`, flexBasis: `${(b.gap / span) * 100}%` }} />
          : <span key={i} className={`h-5 shrink-0 rounded-[3px] border-r border-black/40 ${b.cut ? "bg-white/25" : "bg-lime/80"}`}
              style={{ flexBasis: `${(Math.max(0.05, b.word.end - b.word.start) / span) * 100}%` }} />)}
      </div>
      <div className="-mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12px] text-white/55">Silences over 0.6 s and filler words come out of every clip. Turn it off per job.</p>
        <Credits items={[clip]} />
      </div>
    </div>
  );
}
