"use client";
import { useState } from "react";
import { Pill } from "./Bits";
import { Credits, Footage, Item, useItems } from "./Footage";
import { Cam, Gameplay } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

// Wide gameplay with a facecam corner, before; the same moment in each vertical layout, after. `name` is the app's
// (lib/templates.ts LAYOUT_NAMES, tidied as the app shows them); `says` is what the layout does.
const LAYOUTS = [
  { id: "split2", name: "Split in two", says: "Facecam over gameplay" },
  { id: "screen_first", name: "Screen first", says: "Gameplay over facecam" },
  { id: "pip", name: "Picture in picture", says: "Facecam inset on gameplay" },
  { id: "full", name: "Full", says: "Gameplay fills the frame" },
];
type Box = [number, number, number, number];             // x, y, w, h as fractions of the 16:9 frame
type Boxes = { facecam?: Box; crop?: Record<string, Box> };

const isBox = (b: unknown): b is Box => Array.isArray(b) && b.length === 4 && b.every((n) => typeof n === "number" && n >= 0 && n <= 1);
const at = (b: Box) => ({ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${b[2] * 100}%`, height: `${b[3] * 100}%` });

// An outline the engine reported, with its label inside it: the camera's at the top, the crop's at the bottom,
// so the two never cover each other. Neutral (white) labels only — no green Facecam sticker.
function Outline({ box, label, tone }: { box: Box; label: string; tone: "lime" | "white" }) {
  const right = box[0] + box[2] > 0.75;
  return (
    <span className={`absolute rounded-[6px] border-2 transition-all duration-500 ${tone === "lime" ? "border-lime" : "border-white/90"}`} style={at(box)} aria-hidden="true">
      {/* The tag hangs outside the outline, under its corner, so it never covers what the box is drawn around. */}
      <span className={`absolute top-[calc(100%+4px)] whitespace-nowrap rounded-[4px] px-1 py-px text-[9px] font-semibold leading-[12px] ${right ? "right-0" : "left-0"} ${tone === "lime" ? "bg-lime text-ink" : "bg-white text-black"}`}>{label}</span>
    </span>
  );
}

export const boxesOf = (item: Item | null): Boxes | null => ((item as (Item & { boxes?: Boxes }) | null)?.boxes) ?? null;

// The 16:9 original with the facecam and the crop of one layout outlined, both from the engine's own plan. With no
// footage yet: an empty frame, never invented boxes.
export function BeforeFrame({ item, layout, play }: { item: Item | null; layout: string | null; play: boolean }) {
  const boxes = boxesOf(item);
  const cam = isBox(boxes?.facecam) ? boxes!.facecam! : null, crop = layout && isBox(boxes?.crop?.[layout]) ? boxes!.crop![layout] : null;
  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-[12px] bg-white/[.04] ring-1 ring-white/10">
      {item && <>
        <Footage section="reframe" item={item} play={play} />
        {crop && <Outline box={crop} label="Gameplay crop" tone="white" />}
        {cam && <Outline box={cam} label="Camera" tone="white" />}
      </>}
    </div>
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
  const face = (l: (typeof LAYOUTS)[number], live: boolean) => { const it = find(l.id); return it ? <Footage section="reframe" item={it} play={live} /> : <span className="absolute inset-0 bg-white/[.04]" />; };

  // Placeholder morph when the media pipeline has not delivered reframe footage yet: 16:9 → 9:16 with the
  // camera panel kept clear of the gameplay crop (no green Facecam sticker).
  if (!items.length) {
    return (
      <div className={`${s.demo} flex h-full flex-col items-center justify-center gap-4`} data-play={play}>
        <div className="relative flex h-[360px] w-full max-w-[560px] items-center justify-center narrow:h-[260px]">
          <div className={`${reduced ? "aspect-[9/16] h-full" : s.morph} relative overflow-hidden bg-white/[.04] ring-1 ring-white/10`}>
            <Gameplay game="gta" label={false} />
            <span className={`${s.morphPip} absolute bottom-[8%] left-[5%] aspect-[4/3] w-[24%] overflow-hidden rounded-[6px] ring-1 ring-white/25`}>
              <Cam /></span>
            <span className={`${s.morphCam} absolute inset-x-0 top-0 h-[32%] overflow-hidden border-b border-black/50`}>
              <Cam /></span>
          </div>
        </div>
        <Pill>16:9 → 9:16 · camera over gameplay</Pill>
        <p className="text-[12px] text-white/45">Approved reframe footage pending · layout animation only</p>
      </div>
    );
  }

  return (
    <div className={`${s.demo} flex h-full flex-col items-center justify-center gap-3`} data-play={play}>
    <div className="flex w-full items-center justify-center gap-6 narrow:flex-col narrow:gap-3">
      <figure className="flex w-[480px] shrink-0 flex-col items-center gap-4 narrow:w-full narrow:gap-2.5">
        <BeforeFrame item={original} layout={layout?.id ?? null} play={play} />
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
          <div className="relative h-[360px] w-[203px] narrow:h-[220px] narrow:w-[124px]">
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
    <Credits items={items} />
    </div>
  );
}
