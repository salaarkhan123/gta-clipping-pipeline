"use client";
import { Pill } from "./Bits";
import { Footage, useItems } from "./Footage";
import { Cam, Gameplay, SplitClip } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";

// Wide gameplay with a facecam corner, before; the same moment in our vertical layouts, after. The names are the
// app's (lib/templates.ts LAYOUT_NAMES; "full" and "screen_first" are shown tidied, as the app shows them).
const LAYOUTS = [
  { id: "split2", name: "Split in two", draw: <SplitClip game="gta" /> },
  { id: "full", name: "Full", draw: <Gameplay game="gta" label={false} /> },
  { id: "pip", name: "Picture in picture", draw: <><Gameplay game="gta" label={false} /><span className="absolute left-[6%] top-[4%] aspect-[4/3] w-[38%] overflow-hidden rounded-[8px] ring-1 ring-white/30"><Cam /></span></> },
  { id: "screen_first", name: "Screen first", draw: <span className="absolute inset-0 grid grid-rows-[70%_1fr]"><span className="relative"><Gameplay game="gta" label={false} /></span><span className="relative border-t border-black/60"><Cam /></span></span> },
];

export function Reframe({ play }: { play: boolean }) {
  const reduced = useReducedMotion(), tick = useTicker(play && !reduced, 2600);
  // Real footage: the 16:9 original and the engine's render in each layout. Once the section has media, only the
  // layouts the engine really rendered are shown; a missing one is left out, never drawn.
  const items = useItems("reframe"), find = (id: string) => items.find((i) => i.id === id) ?? null;
  const shown = items.length ? LAYOUTS.filter((l) => find(l.id)) : LAYOUTS;
  const layout = shown.length ? shown[tick % shown.length] : null;
  const original = find("original"), after = layout && find(layout.id);
  return (
    <div className={`${s.demo} flex h-full items-center justify-center gap-8 narrow:flex-col narrow:gap-3`} data-play={play}>
      <figure className="flex w-[min(440px,100%)] flex-col items-center gap-4 narrow:gap-2.5">
        <div className="relative aspect-video w-full overflow-hidden rounded-[12px] ring-1 ring-white/10">
          {original ? <Footage section="reframe" item={original} play={play} /> : <>
            <Gameplay game="gta" />
            <span className="absolute bottom-[6%] left-[3%] aspect-[4/3] w-[24%] overflow-hidden rounded-[6px]"><Cam /></span>
            <span className={`${s.find} absolute bottom-[4%] left-[1.5%] aspect-[4/3] w-[27%] rounded-[8px] border-2 border-dashed border-lime`} aria-hidden="true">
              <span className="absolute -top-6 left-0 whitespace-nowrap rounded-[5px] bg-lime px-1.5 py-0.5 text-[11px] font-semibold text-ink">Facecam found</span>
            </span>
          </>}
        </div>
        <figcaption><Pill>Before · 16:9</Pill></figcaption>
      </figure>

      {layout && <>
        <div className="flex gap-2 narrow:rotate-90" aria-hidden="true">
          {[0, 1, 2].map((i) => <span key={i} className={`${s.dot} h-2 w-2 rounded-full bg-white`} style={{ ["--d" as string]: `${i * 0.2}s` }} />)}
        </div>

        <figure className="flex flex-col items-center gap-4 narrow:gap-2.5">
          <div className="relative aspect-[9/16] h-[400px] overflow-hidden rounded-[14px] ring-1 ring-white/10 narrow:h-[260px]">
            <span key={layout.name} className={`${s.swap} absolute inset-0`}>{after ? <Footage section="reframe" item={after} play={play} /> : layout.draw}</span>
          </div>
          <figcaption><Pill>{layout.name} · 9:16</Pill></figcaption>
        </figure>
      </>}
    </div>
  );
}
