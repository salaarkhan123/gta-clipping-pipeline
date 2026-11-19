"use client";
import { useState } from "react";
import { Pill } from "./Bits";
import { Footage, Item, useItems } from "./Footage";
import { Cam, Gameplay, SplitClip } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

// Wide gameplay with a facecam corner, before; the same moment in each vertical layout, after. `name` is the app's
// (lib/templates.ts LAYOUT_NAMES, tidied as the app shows them); `says` is what the layout does.
const LAYOUTS = [
  { id: "split2", name: "Split in two", says: "Facecam over gameplay", draw: <SplitClip game="gta" /> },
  { id: "screen_first", name: "Screen first", says: "Gameplay over facecam", draw: <span className="absolute inset-0 grid grid-rows-[70%_1fr]"><span className="relative"><Gameplay game="gta" label={false} /></span><span className="relative border-t border-black/60"><Cam /></span></span> },
  { id: "pip", name: "Picture in picture", says: "Facecam inset on gameplay", draw: <><Gameplay game="gta" label={false} /><span className="absolute left-[6%] top-[4%] aspect-[4/3] w-[38%] overflow-hidden rounded-[8px] ring-1 ring-white/30"><Cam /></span></> },
  { id: "full", name: "Full", says: "Gameplay fills the frame", draw: <Gameplay game="gta" label={false} /> },
];
type Box = [number, number, number, number];             // x, y, w, h as fractions of the 16:9 frame
type Boxes = { facecam?: Box; crop?: Record<string, Box> };

const isBox = (b: unknown): b is Box => Array.isArray(b) && b.length === 4 && b.every((n) => typeof n === "number" && n >= 0 && n <= 1);
const at = (b: Box) => ({ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${b[2] * 100}%`, height: `${b[3] * 100}%` });

function Outline({ box, label, tone }: { box: Box; label: string; tone: "lime" | "white" }) {
  return (
    <span className={`absolute rounded-[6px] border-2 transition-all duration-500 ${tone === "lime" ? "border-lime" : "border-white/90"}`} style={at(box)} aria-hidden="true">
      <span className={`absolute left-1 top-1 whitespace-nowrap rounded-[5px] px-1.5 py-0.5 text-[10px] font-semibold ${tone === "lime" ? "bg-lime text-ink" : "bg-white text-black"}`}>{label}</span>
    </span>
  );
}

export function Reframe({ play }: { play: boolean }) {
  const reduced = useReducedMotion(), tick = useTicker(play && !reduced, 2800);
  const [picked, setPicked] = useState<number | null>(null);
  // Real footage: the 16:9 original and the engine's render in each layout. Once the section has media, only the
  // layouts the engine rendered are shown; the outlines come only from the boxes the engine reported.
  const items = useItems("reframe"), find = (id: string): Item | null => items.find((i) => i.id === id) ?? null;
  const shown = items.length ? LAYOUTS.filter((l) => find(l.id)) : LAYOUTS;
  const n = shown.length, i = n ? (picked ?? tick) % n : 0, layout = n ? shown[i] : null;
  const original = find("original");
  const boxes = ((original as (Item & { boxes?: Boxes }) | null)?.boxes) ?? null;
  const cam = isBox(boxes?.facecam) ? boxes!.facecam! : null, crop = layout && isBox(boxes?.crop?.[layout.id]) ? boxes!.crop![layout.id] : null;
  const face = (l: (typeof LAYOUTS)[number], live: boolean) => { const it = find(l.id); return it ? <Footage section="reframe" item={it} play={live} /> : l.draw; };

  return (
    <div className={`${s.demo} flex h-full items-center justify-center gap-10 narrow:flex-col narrow:gap-4`} data-play={play}>
      <figure className="flex w-[min(420px,100%)] flex-col items-center gap-4 narrow:gap-2.5">
        <div className="relative aspect-video w-full overflow-hidden rounded-[12px] ring-1 ring-white/10">
          {original ? <>
            <Footage section="reframe" item={original} play={play} />
            {cam && <Outline box={cam} label="Facecam" tone="lime" />}
            {crop && <Outline box={crop} label="Gameplay crop" tone="white" />}
          </> : <>
            <Gameplay game="gta" />
            <span className="absolute bottom-[6%] left-[3%] aspect-[4/3] w-[24%] overflow-hidden rounded-[6px]"><Cam /></span>
            <Outline box={[0.015, 0.6, 0.27, 0.36]} label="Facecam" tone="lime" />
            <Outline box={[0.36, 0.02, 0.32, 0.96]} label="Gameplay crop" tone="white" />
          </>}
        </div>
        <figcaption><Pill>Before · 16:9</Pill></figcaption>
      </figure>

      {layout && <>
        <div className="flex gap-2 narrow:order-last" role="group" aria-label="Layouts">
          {shown.map((l, j) => (
            <button key={l.id} type="button" aria-label={l.says} aria-pressed={j === i} onClick={() => setPicked(j)}
              className={`h-2.5 w-2.5 cursor-pointer rounded-full border-0 p-0 transition-colors ${j === i ? "bg-white" : "bg-white/30 hover:bg-white/60"}`} />
          ))}
        </div>

        <figure className="flex flex-col items-center gap-4 narrow:gap-2.5">
          <div className="relative h-[400px] w-[225px] narrow:h-[240px] narrow:w-[135px]">
            {/* the next two layouts peek out behind the one shown */}
            {[2, 1].filter((k) => k < n).map((k) => (
              <span key={k} className="absolute inset-0 overflow-hidden rounded-[14px] opacity-40 ring-1 ring-white/10 transition-transform duration-500"
                style={{ transform: `translateX(${k * 14}px) scale(${1 - k * 0.06})` }} aria-hidden="true">{face(shown[(i + k) % n], false)}</span>
            ))}
            <span key={layout.id} className={`${s.swap} absolute inset-0 overflow-hidden rounded-[14px] ring-1 ring-white/15`}>{face(layout, play)}</span>
          </div>
          <figcaption className="flex flex-col items-center gap-1">
            <Pill>{layout.says}</Pill>
            <span className="text-[12px] text-white/50">{layout.name} · 9:16</span>
          </figcaption>
        </figure>
      </>}
    </div>
  );
}
