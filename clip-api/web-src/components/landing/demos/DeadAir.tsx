"use client";
import { useEffect, useRef, useState } from "react";
import { mediaUrl } from "@/lib/media";
import { Credits, Footage, Item, useItem, usePeaks, useWords, Word } from "./Footage";
import { useReducedMotion } from "./motion";
import s from "./demos.module.css";

// Dead air out: every clip loses its silences over 0.6 s and its filler words (the `tighten` option, on by default,
// app/pipeline/__init__.py). Everything here is the media pipeline's clip and its own data: the struck-out
// silences are the real gaps between its words, the fillers its real "um"s, the filmstrip its own frames and the
// waveform its own audio levels. With no clip yet the card stays empty.
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
  const reduced = useReducedMotion();
  const wide = useItem("editor", "editor-1-wide") as (Item & { strip?: string }) | null, tall = useItem("editor", "editor-1");
  const clip = wide || tall, words = useWords("editor", clip);
  const bits = bitsOf(words);
  const peaks = usePeaks("editor", clip), len = clip?.duration_sec ?? 0;
  const silences = words.flatMap((w, i) => (i && w.start - words[i - 1].end >= SILENCE ? [[words[i - 1].end, w.start]] : []));
  const cut = (t: number) => silences.some(([a, b]) => t >= a && t < b);

  // The playhead follows the playing clip.
  const video = useRef<HTMLVideoElement>(null);
  const [at, setAt] = useState(0);
  useEffect(() => {
    if (!play || reduced || !len) return;
    let raf = 0;
    const step = () => { const v = video.current; if (v) setAt(v.currentTime / len); raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [play, reduced, len]);

  // The line being spoken at the playhead: the word said now with up to two before it, within the same breath.
  const now = at * len, i = words.findIndex((w) => now >= w.start && now <= w.end + .35);
  const said = i < 0 ? "" : words.slice(Math.max(0, i - 2), i + 1).filter((w, k, a) => !k || w.start - a[k - 1].end < SILENCE).map((w) => w.text.trim()).join(" ");

  return (
    <div className={`${s.demo} flex h-full flex-col justify-center gap-4 narrow:gap-3`} data-play={play}>
      <div className="flex items-start gap-8 narrow:flex-col-reverse narrow:gap-3">
        <p className="m-0 min-w-0 flex-1 text-left text-[17px] leading-[1.9] text-white/90 narrow:text-[14px]" aria-label="The clip's transcript, with what gets cut struck out">
          {bits.map((b, i) => "gap" in b
            ? <span key={i} className={`${s.strike} mx-1 inline-flex items-center gap-[5px] rounded-full bg-white/10 px-2 align-middle text-[12px] leading-[20px] text-white/55 line-through`}>
                <span className="h-[5px] w-[5px] rounded-full bg-white/50" />{b.gap.toFixed(1)} s silence</span>
            : b.cut ? <span key={i} className={`${s.strike} text-white/45 line-through`}>{b.word.text} </span> : <span key={i}>{b.word.text} </span>)}
        </p>
        <div className={`relative flex-none overflow-hidden rounded-[14px] bg-white/[.04] shadow-[0_18px_50px_rgba(0,0,0,.4)] ${wide ? "aspect-video w-[47%] narrow:w-full" : "aspect-[9/16] h-[300px]"}`}>
          {clip && <Footage section="editor" item={clip} play={play} videoRef={video} />}
          {/* The words being said at the playhead. */}
          {said && <span className="absolute inset-x-3 bottom-[9%] z-10 text-center text-[22px] font-semibold leading-[1.15] text-white [text-shadow:0_2px_6px_rgba(0,0,0,.9),0_0_2px_#000] narrow:text-[15px]">{said}</span>}
        </div>
      </div>

      {/* The clip's own frames, edge to edge, then its audio: the part already played is bright, the silences that get cut are dim. */}
      {wide?.strip && <div className="h-[57px] flex-none overflow-hidden rounded-[12px] border border-solid border-white/[.16] bg-black/30" aria-hidden="true">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={mediaUrl("editor", wide.strip)} alt="" className="block h-full w-full object-cover" /></div>}
      {peaks && len > 0 && (
        <div className="relative h-[38px] flex-none overflow-hidden rounded-[10px] bg-white/[.07]" aria-hidden="true">
          <div className="absolute inset-x-3 inset-y-[5px] flex items-center gap-px">
            {peaks.map((p, i) => { const t = ((i + .5) / peaks.length) * len;
              return <span key={i} className={`flex-1 rounded-full ${cut(t) ? "bg-white/15" : (i + .5) / peaks.length <= at ? "bg-white" : "bg-white/45"}`} style={{ height: `${Math.max(8, p * 92)}%` }} />; })}
          </div>
          {silences.map(([a, b]) => <span key={a} title="Silence, cut" className="absolute inset-y-0 bg-[repeating-linear-gradient(135deg,rgba(255,255,255,.13)_0_3px,transparent_3px_7px)]"
            style={{ left: `calc(12px + (100% - 24px) * ${a / len})`, width: `calc((100% - 24px) * ${(b - a) / len})` }} />)}
          <span className="absolute inset-y-0 w-[2px] rounded-full bg-white shadow-[0_0_6px_rgba(255,255,255,.6)]" style={{ left: `calc(12px + (100% - 24px) * ${Math.min(1, at)})` }} />
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-[12px] text-white/55">Silences over 0.6 s and filler words come out of every clip. Turn it off per job.</p>
        <Credits items={[clip]} />
      </div>
    </div>
  );
}
