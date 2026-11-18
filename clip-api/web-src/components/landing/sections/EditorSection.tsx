"use client";
import { useRef } from "react";
import { Caption } from "../demos/Caption";
import { Footage, useItem, useWords } from "../demos/Footage";
import { SplitClip } from "../demos/Frames";
import { useInView, useReducedMotion, useTicker } from "../demos/motion";
import s from "../demos/demos.module.css";
import { Section } from "../../site/Section";
import { EyebrowIcon } from "./EyebrowIcon";

// The clip editor as the app has it (components/dash/Editor.tsx): transcript, caption lines and look tabs, a
// trim bar with cuts, Your edit / Current file, Undo all changes, Save and Render. Nothing here that it lacks.
const WORDS = ["Okay", "we", "go", "left,", "wait", "wait", "wait,", "um,", "no,", "right", "side,", "chat", "watch", "this", "jump.", "If",
  "I", "land", "this", "it's", "over.", "NO", "WAY!", "He", "actually", "did", "it."];
const CUT = [4, 5, 6, 7, 8];                       // "wait wait wait, um, no," cut from the transcript
const FILLER = /^(um+|uh+|erm|hmm+)[,.!?]*$/i;         // with real words, the fillers are shown cut

function Icon({ d }: { d: React.ReactNode }) {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;
}
const TABS = [
  { name: "Transcript", d: <><path d="M5 6h14M5 10h14M5 14h9M5 18h6" /></> },
  { name: "Caption lines", d: <><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M7 12h4M13 12h4M7 15h7" /></> },
  { name: "Look", d: <><circle cx="12" cy="12" r="8" /><path d="M12 4v16M4 12h16" /></> },
];

export function EditorSection() {
  const box = useRef<HTMLDivElement>(null), seen = useInView(box, "0px"), reduced = useReducedMotion();
  const tick = useTicker(seen && !reduced, 360);
  // Real footage: the media pipeline's editor clip and its own words; the sample sentence until then.
  const clip = useItem("editor", "editor-1"), said = useWords("editor", clip);
  const words = said.length >= 8 ? said.slice(0, 40).map((w) => w.text.trim()) : WORDS;
  const cut = said.length >= 8 ? words.flatMap((w, i) => (FILLER.test(w) ? [i] : [])) : CUT;
  const spoken = words.map((_, i) => i).filter((i) => !cut.includes(i));
  const now = spoken[tick % spoken.length];
  const caps = words.map((w) => w.replace(/[^\p{L}\p{N}'!?]/gu, "").toUpperCase());

  return (
    <Section id="editor" eyebrow="Editor" icon={<EyebrowIcon name="edit" />} title={<>Let the AI cut it,<br className="narrow:hidden" /> then make it yours</>}
      sub="Every clip opens in the editor. Cut words straight from the transcript, fix a caption line, change the look, then render it again.">
      <div ref={box} className={`${s.demo} overflow-hidden rounded-stage shadow-card`} data-play={seen}
        style={{ background: "radial-gradient(120% 90% at 50% 0%, #2a2219, #0f1013 80%)" }} aria-hidden="true">
        {/* top bar */}
        <div className="flex items-center gap-5 border-b border-white/[.07] px-5 py-3 text-[13px] text-white/80 narrow:gap-3 narrow:px-3">
          <span className="font-semibold text-white narrow:hidden">Edit clip #1</span>
          <span className="flex items-center gap-1.5"><span className="h-3.5 w-2 rounded-[2px] border border-current" />9:16</span>
          <span className="narrow:hidden">Layout: Split in two</span>
          <span>Captions: Impact</span>
          <span className="ml-auto flex rounded-[9px] bg-black/40 p-0.5 text-[12px] ring-1 ring-white/10 narrow:hidden">
            <b className="rounded-[7px] bg-white/15 px-2.5 py-1 font-semibold">Your edit</b><span className="px-2.5 py-1 text-white/60">Current file</span></span>
        </div>

        <div className="grid grid-cols-[1fr_auto_88px] narrow:grid-cols-1">
          {/* transcript */}
          <div className="flex flex-col gap-3 border-r border-white/[.07] p-5 narrow:order-3 narrow:border-r-0 narrow:border-t narrow:p-4">
            <p className="text-[12px] text-white/50">Click a word to jump to it. Shift-click another to select everything between, then cut it.</p>
            <div className="flex items-center gap-2 text-[12px]">
              <span className="text-white/70">{cut.length} word{cut.length === 1 ? "" : "s"} cut</span>
              <span className="rounded-full bg-white/10 px-2.5 py-1 text-white/60 ring-1 ring-white/10">Cut</span>
              <span className="rounded-full bg-white/10 px-2.5 py-1 text-white/80 ring-1 ring-white/10">Restore</span>
            </div>
            <p className="text-[17px] leading-[1.9] narrow:text-[15px]">
              {words.map((w, i) => {
                const out = cut.includes(i);
                return <span key={i} className={`mr-[.22em] inline-block rounded-[4px] px-[1px] ${out ? "bg-white/[.04] text-white/35 line-through" : i === now ? "bg-lime text-ink" : "text-white/90"}`}>{w}</span>;
              })}
            </p>
          </div>

          {/* preview */}
          <div className="flex items-center justify-center px-8 py-6 narrow:order-1 narrow:py-4">
            <div className="relative aspect-[9/16] h-[400px] overflow-hidden rounded-[14px] ring-1 ring-white/10 narrow:h-[300px]">
              {clip ? <Footage section="editor" item={clip} play={seen} /> : <>
                <SplitClip game="gta" />
                <span className="absolute inset-x-[8%] top-[6%] rounded-[7px] bg-lime px-2 py-1 text-center text-[13px] font-extrabold leading-tight text-ink">He actually landed it</span>
                <span className="absolute inset-x-2 top-[33%] -translate-y-1/2 text-center text-[20px]">
                  <Caption style="impact" words={caps} keys={[22]} at={now} />
                </span>
              </>}
            </div>
          </div>

          {/* tabs */}
          <div className="flex flex-col items-center gap-2 border-l border-white/[.07] py-5 narrow:order-2 narrow:flex-row narrow:justify-center narrow:border-l-0 narrow:border-t narrow:py-2">
            {TABS.map((t, i) => (
              <span key={t.name} className={`flex w-[76px] flex-col items-center gap-1 rounded-[10px] py-2 text-center text-[11px] leading-tight ${i === 0 ? "bg-white/10 text-white" : "text-white/60"}`}>
                <Icon d={t.d} />{t.name}</span>
            ))}
          </div>
        </div>

        {/* trim bar and actions */}
        <div className="flex flex-col gap-3 border-t border-white/[.07] px-5 py-4 narrow:px-3">
          <div className="flex items-center gap-4 text-[12px] text-white/70">
            <span className="flex items-center gap-1.5 rounded-full bg-lime px-3 py-1 font-semibold text-ink">
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor"><path d="M7 5v14l12-7z" /></svg>Play</span>
            <span className="tabular-nums">0:04 · clip 0:27</span>
            <span className="ml-auto flex gap-2 narrow:hidden">
              <span className="rounded-full px-3 py-1 ring-1 ring-white/15">Undo all changes</span>
              <span className="rounded-full px-3 py-1 ring-1 ring-white/15">Save</span>
              <span className="rounded-full bg-white px-3 py-1 font-semibold text-black">Render</span>
            </span>
          </div>
          <div className="relative h-12 rounded-[10px] bg-black/40 ring-1 ring-white/10">
            {Array.from({ length: 40 }, (_, i) => <span key={i} className="absolute top-1/2 h-[46%] w-[1.6%] -translate-y-1/2 rounded-[2px] bg-white/10" style={{ left: `${1 + i * 2.45}%` }} />)}
            <span className="absolute inset-y-0 left-[12%] right-[22%] rounded-[8px] border-2 border-lime bg-lime/[.06]" />
            <span className="absolute inset-y-1 left-[30%] w-[7%] rounded-[4px] bg-[repeating-linear-gradient(135deg,rgba(255,92,122,.45)_0_4px,transparent_4px_8px)]" />
            <span className="absolute -bottom-0.5 left-[12%] h-[110%] w-1.5 -translate-x-1/2 rounded-full bg-lime" />
            <span className="absolute -bottom-0.5 right-[22%] h-[110%] w-1.5 translate-x-1/2 rounded-full bg-lime" />
            <span className="absolute inset-y-0 left-[12%] right-[22%]"><span className={`${s.playhead} absolute -top-1 bottom-[-4px] w-0.5 bg-white`} style={{ ["--t" as string]: "9s" }} /></span>
          </div>
        </div>
      </div>
    </Section>
  );
}
