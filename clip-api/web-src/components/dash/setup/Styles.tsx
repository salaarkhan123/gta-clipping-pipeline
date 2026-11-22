"use client";
// How caption styles and hook tones are drawn in pickers, in our own fonts. The words are ours; nothing here is footage.
import { tidy } from "@/lib/templates";

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

// A sample opening line for each hook tone, in our words.
export const HOOK_LINES: Record<string, string> = {
  serious: "This is how the heist really ended", casual: "ok so this happened on stream", informative: "How to lose a five-star chase",
  conversational: "You won't guess what chat said next", humorous: "My driving instructor would cry", parody: "A totally normal day in the city",
  inspirational: "Down 1v4. Didn't give up.", dramatic: "Nobody saw this ending coming", empathetic: "We've all lost a run like this",
  persuasive: "Stay for the last ten seconds", neutral: "The final thirty seconds", excited: "HE DID NOT JUST DO THAT", calm: "A quiet moment before the chaos",
};
