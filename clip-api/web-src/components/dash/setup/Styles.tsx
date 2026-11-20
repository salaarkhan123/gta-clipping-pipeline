"use client";
// Caption styles and hook tones as tiles, drawn in our own fonts. The words are ours; nothing here is footage.
import { useState } from "react";
import { tidy } from "@/lib/templates";
import { Tile } from "./parts";

// How each caption style reads, close to how the renderer draws it (render/captions): weight, case, the accent word.
export const CAPTION: Record<string, { box: string; hot: string; text?: [string, string] }> = {
  impact: { box: "font-black uppercase tracking-[-0.01em] text-white [text-shadow:0_2px_0_#000,0_0_3px_#000]", hot: "text-lime" },
  pop: { box: "font-extrabold text-white [text-shadow:0_2px_0_#000]", hot: "text-[#ffe14d] text-[1.18em]" },
  bold: { box: "font-black uppercase text-white [text-shadow:0_3px_0_#000]", hot: "" },
  neon: { box: "font-extrabold uppercase text-white [text-shadow:0_0_8px_rgba(122,255,102,.8)]", hot: "text-[#7aff66]" },
  boxed: { box: "font-bold text-white [&>span]:rounded-[4px] [&>span]:bg-black [&>span]:px-[5px]", hot: "" },
  clean: { box: "font-semibold text-white", hot: "", text: ["no way he", "hit that"] },
  bounce: { box: "font-black uppercase text-white [text-shadow:0_2px_0_#000]", hot: "inline-block -rotate-6 text-[#ff7ad9]" },
  karaoke: { box: "font-extrabold uppercase text-[rgba(255,255,255,.55)]", hot: "rounded-[4px] bg-[#7c5cff] px-1 text-white" },
  reveal: { box: "font-extrabold uppercase text-white", hot: "opacity-40" },
  outline: { box: "font-black uppercase text-transparent [-webkit-text-stroke:1.5px_#fff]", hot: "" },
  subtitle: { box: "rounded-[4px] bg-[rgba(0,0,0,.65)] px-2 py-[2px] text-[13px] font-medium text-white", hot: "", text: ["no way he", "hit that"] },
  tag: { box: "font-extrabold uppercase text-white", hot: "rounded-[4px] bg-[#ff4d4d] px-1" },
};
const TAG_NAMES: Record<string, string> = { tag: "Tag", bold: "Heavy" };
export const captionName = (s: string) => TAG_NAMES[s] || tidy(s);

export function CaptionStyles({ styles, value, onChange }: { styles: string[]; value: string; onChange: (s: string) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? styles : styles.slice(0, 5);
  return (
    <div className="grid gap-2">
      <div className={`grid gap-3 ${all ? "grid-cols-[repeat(auto-fill,minmax(124px,1fr))]" : "grid-cols-[repeat(5,minmax(112px,1fr))] overflow-x-auto pb-1 narrow:grid-cols-[repeat(5,112px)]"}`}
        role="group" aria-label="Caption style">
        {shown.map((s) => {
          const c = CAPTION[s] || CAPTION.clean, [a, b] = c.text || ["no way", "he hit that"];
          return <Tile key={s} name={captionName(s)} on={value === s} onClick={() => onChange(s)} className="aspect-[16/10] w-full [background:linear-gradient(160deg,#2a2f3a,#121419)]">
            <span className={`grid place-items-center px-2 text-center font-sans text-[17px] leading-[1.1] ${c.box}`}><span>{a} <span className={c.hot}>{b.split(" ")[0]}</span> {b.split(" ").slice(1).join(" ")}</span></span>
          </Tile>;
        })}
      </div>
      {styles.length > 5 && <button type="button" className="link small justify-self-end" onClick={() => setAll(!all)}>{all ? "Show fewer" : `View all ${styles.length}`}</button>}
    </div>
  );
}

// A sample opening line for each hook tone, in our words.
export const HOOK_LINES: Record<string, string> = {
  serious: "This is how the heist really ended", casual: "ok so this happened on stream", informative: "How to lose a five-star chase",
  conversational: "You won't guess what chat said next", humorous: "My driving instructor would cry", parody: "A totally normal day in the city",
  inspirational: "Down 1v4. Didn't give up.", dramatic: "Nobody saw this ending coming", empathetic: "We've all lost a run like this",
  persuasive: "Stay for the last ten seconds", neutral: "The final thirty seconds", excited: "HE DID NOT JUST DO THAT", calm: "A quiet moment before the chaos",
};
const BACKS = ["linear-gradient(170deg,#3a2a1f,#0f0d0c)", "linear-gradient(170deg,#1f2a3a,#0b0e13)", "linear-gradient(170deg,#2a1f3a,#0e0b13)", "linear-gradient(170deg,#1f3a2c,#0b130f)"];

export function HookTones({ tones, value, onChange }: { tones: string[]; value: string; onChange: (s: string) => void }) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-1" role="group" aria-label="Hook tone">
      {tones.map((s, i) => <div key={s} className="w-[92px] flex-none"><Tile name={tidy(s)} on={value === s} onClick={() => onChange(s)} className="aspect-[9/16] w-full">
        <span className="absolute inset-0" style={{ background: BACKS[i % 4] }} />
        <img src={`/media/setup/hook-${(i % 4) + 1}.webp`} alt="" className="absolute inset-0 h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        <span className="absolute inset-x-2 top-[18%] rounded-[4px] bg-white px-1 py-[3px] text-center font-sans text-[10px] font-bold leading-[1.15] text-black">{HOOK_LINES[s] || tidy(s)}</span>
      </Tile></div>)}
    </div>
  );
}
