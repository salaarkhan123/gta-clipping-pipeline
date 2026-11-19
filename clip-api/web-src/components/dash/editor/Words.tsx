"use client";
// Text-based caption editing (#215) and the caption look (#213) in the editor: the word menu, the look controls of
// the Captions tool, and the caption drawn over the preview with the same font, size, colours and row the renderer
// uses. Each part shows the Coming soon mark when this API does not have its route or option yet.
import { useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import type { EditWord } from "@/lib/edit";
import type { CaptionLookSpec } from "@/lib/routes";
import { tidy } from "@/lib/templates";
import { CAPTION_FONTS, DEFAULT_FONT, EMOJI_FAMILY, WEIGHT_CSS } from "./captionFonts";

export type CaptionLook = { font?: string | null; weight?: string | null; italic?: boolean; underline?: boolean; colour?: string | null;
  outline_colour?: string | null; size?: number | null; case?: string; y?: number | null };

const EMOJI = ["🔥", "😂", "💀", "😱", "🏆", "👀", "🎯", "💥"];
const ITEM = "inline-flex min-h-[34px] cursor-pointer items-center gap-[6px] rounded-full border border-solid border-line bg-transparent px-3 font-sans text-[13px] text-label hover:border-line-strong hover:text-text disabled:cursor-default disabled:opacity-40 aria-pressed:border-text aria-pressed:text-text";

// ---------- the word menu ----------
// `picked` are the indexes of the selected words. Edit word works on one word; the rest work on all of them.
export function WordMenu({ on, words, picked, onWords, onCutWithVideo }: { on: boolean; words: EditWord[] | null; picked: number[];
  onWords: (next: EditWord[]) => void; onCutWithVideo: () => void }) {
  const [typing, setTyping] = useState<string | null>(null);
  if (!picked.length) return null;
  if (!on || !words) return (
    <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-muted" aria-label="Word menu">
      Edit word, split, emoji, highlight and remove caption <ComingSoonBadge short />
    </div>
  );
  const sel = picked.map((i) => words[i]).filter(Boolean);
  const all = (k: keyof EditWord) => sel.every((w) => !!w[k]);
  const change = (fn: (w: EditWord, i: number) => EditWord) => onWords(words.map((w, i) => (picked.includes(i) ? fn(w, i) : w)));
  const first = Math.min(...picked), last = Math.max(...picked), one = picked.length === 1 ? words[first] : null;
  const colour = sel.find((w) => w.highlight)?.highlight || "#ffd400";
  return (
    <div className="grid gap-2 rounded-16 border border-solid border-line-soft bg-surface p-3" role="group" aria-label="Word menu">
      <div className="flex flex-wrap items-center gap-2">
        {one && (typing === null
          ? <button type="button" className={ITEM} onClick={() => setTyping(one.text)}>Edit word</button>
          : <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); const v = typing.trim().replace(/[{}\\]/g, "");
              if (v) change((w) => ({ ...w, text: v.slice(0, 60) })); setTyping(null); }}>
              <input autoFocus value={typing} maxLength={60} aria-label="The word as shown" onChange={(e) => setTyping(e.target.value)}
                className="w-40 rounded-full px-3 py-[6px] text-[14px]" />
              <button className="btn small primary">Save</button>
              <button type="button" className="btn small ghost" onClick={() => setTyping(null)}>Cancel</button>
            </form>)}
        <button type="button" className={ITEM} aria-pressed={!!words[first]?.break_before} onClick={() => onWords(words.map((w, i) => (i === first ? { ...w, break_before: !w.break_before } : w)))}>
          Split here</button>
        <label className={`${ITEM} relative m-0 font-normal`}>Highlight
          <input type="color" value={colour} aria-label="Highlight colour" onChange={(e) => change((w) => ({ ...w, highlight: e.target.value }))}
            className="h-5 w-6 cursor-pointer border-0 bg-transparent p-0" /></label>
        {sel.some((w) => w.highlight) && <button type="button" className={ITEM} onClick={() => change((w) => ({ ...w, highlight: null }))}>No highlight</button>}
        <button type="button" className={ITEM} aria-pressed={all("hidden")} onClick={() => { const v = !all("hidden"); change((w) => ({ ...w, hidden: v })); }}>Remove caption</button>
        <button type="button" className={ITEM} aria-pressed={all("cut")} onClick={() => { change((w) => ({ ...w, cut: true })); onCutWithVideo(); }}>Remove caption &amp; video</button>
      </div>
      <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Add emoji after the last selected word">
        <span className="mr-1 text-[12.5px] text-muted">Add emoji</span>
        {EMOJI.map((e) => <button key={e} type="button" aria-pressed={words[last]?.emoji === e} onClick={() => onWords(words.map((w, i) => (i === last ? { ...w, emoji: w.emoji === e ? null : e } : w)))}
          className="grid h-8 w-8 cursor-pointer place-items-center rounded-full border border-solid border-transparent bg-transparent text-[17px] hover:bg-chip-hover aria-pressed:border-text"
          style={{ fontFamily: EMOJI_FAMILY }} aria-label={`Emoji ${e}`}>{e}</button>)}
      </div>
    </div>
  );
}

// How one word reads in the transcript once edited: its text, highlight, emoji, a split mark, removed captions.
export function WordFace({ w }: { w: EditWord }) {
  return <>
    {w.break_before && <span className="mr-[3px] text-dim" aria-hidden="true">¶</span>}
    <span style={w.highlight ? { color: w.highlight } : undefined} className={w.hidden ? "underline decoration-dashed decoration-1 opacity-50" : ""}>{w.text}</span>
    {w.emoji && <span className="ml-[2px]" style={{ fontFamily: EMOJI_FAMILY }}>{w.emoji}</span>}
  </>;
}

// ---------- the caption over the preview ----------
// The words on screen at time `t`, grouped the way the renderer groups them: impact shows one or two words at a
// time, the other styles a line of up to 7 words; a split always starts a new caption. Hidden and cut words leave.
export function captionAt(words: EditWord[], t: number, style: string): EditWord[] | null {
  const shown = words.filter((w) => !w.hidden && !w.cut);
  const max = style === "impact" ? 2 : 7, groups: EditWord[][] = [];
  let cur: EditWord[] = [];
  for (const w of shown) {
    if (cur.length && (w.break_before || cur.length >= max || w.start - cur[cur.length - 1].end > 0.6)) { groups.push(cur); cur = []; }
    cur.push(w);
  }
  if (cur.length) groups.push(cur);
  return groups.find((g) => t >= g[0].start && t < Math.max(g[g.length - 1].end, g[0].start + 0.2)) || null;
}

// Drawn in the frame's own units (the frame is a size container), so it scales like the render: size 100 % is 6 %
// of the frame's height; `y` is the caption's row as a share of the height; with no row, the lower third.
export function CaptionOverlay({ words, look }: { words: EditWord[]; look: CaptionLook }) {
  const font = CAPTION_FONTS[look.font || DEFAULT_FONT] || CAPTION_FONTS[DEFAULT_FONT];
  const outline = look.outline_colour || "#000000";
  const size = (6 * (look.size ?? 100)) / 100;
  return (
    <span aria-hidden="true" className="pointer-events-none absolute left-1/2 w-[90%] -translate-x-1/2 -translate-y-1/2 text-center leading-[1.1]"
      style={{ top: `${(look.y ?? 0.72) * 100}%`, fontFamily: font.family, fontWeight: WEIGHT_CSS[look.weight || "regular"] || 400, fontSize: `${size}cqh`,
        fontStyle: look.italic ? "italic" : "normal", textDecoration: look.underline ? "underline" : "none", color: look.colour || "#ffffff",
        textTransform: (look.case || "upper") === "upper" ? "uppercase" : "none", WebkitTextStroke: `0.06em ${outline}`, paintOrder: "stroke fill",
        textShadow: `0 0.04em 0 ${outline}` }}>
      {words.map((w, i) => <span key={i}>{i ? " " : ""}<span style={w.highlight ? { color: w.highlight } : undefined}>{w.text}</span>
        {w.emoji && <span style={{ fontFamily: EMOJI_FAMILY, WebkitTextStroke: "0" }}> {w.emoji}</span>}</span>)}
    </span>
  );
}

// ---------- the look controls in the Captions tool ----------
export function CaptionLookControls({ spec, look, onLook }: { spec: CaptionLookSpec | null; look: CaptionLook; onLook: (l: CaptionLook) => void }) {
  if (!spec) return <p className="m-0 flex flex-wrap items-center gap-2 text-[13px] text-muted">Font, weight, colours, size, italic, underline, case and row <ComingSoonBadge short /></p>;
  const set = (c: Partial<CaptionLook>) => onLook({ ...look, ...c });
  const fonts = spec.fonts.filter((f) => CAPTION_FONTS[f]);           // only faces the preview can draw exactly
  const font = look.font || DEFAULT_FONT;
  const weights = spec.weights;            // a face without a file for the weight is emboldened by the renderer
  return (
    <fieldset className="panels grid gap-3" aria-label="Caption look">
      <legend>Look</legend>
      <label>Font<select value={font} onChange={(e) => set({ font: e.target.value, weight: null })}>
        {fonts.map((f) => <option key={f} value={f}>{CAPTION_FONTS[f].name}</option>)}</select></label>
      {weights.length > 0 && <label>Weight<select value={look.weight || "regular"} onChange={(e) => set({ weight: e.target.value })}>
        {weights.map((w) => <option key={w} value={w}>{tidy(w)}</option>)}</select></label>}
      <div className="flex flex-wrap items-center gap-4">
        <label className="check m-0"><input type="checkbox" checked={!!look.italic} onChange={(e) => set({ italic: e.target.checked })} /><span>Italic</span></label>
        <label className="check m-0"><input type="checkbox" checked={!!look.underline} onChange={(e) => set({ underline: e.target.checked })} /><span>Underline</span></label>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <label className="m-0 flex items-center gap-2">Letters<input type="color" className="swatch" value={look.colour || "#ffffff"} onChange={(e) => set({ colour: e.target.value })} /></label>
        <label className="m-0 flex items-center gap-2">Outline<input type="color" className="swatch" value={look.outline_colour || "#000000"} onChange={(e) => set({ outline_colour: e.target.value })} /></label>
        {(look.colour || look.outline_colour) && <button type="button" className="link small" onClick={() => set({ colour: null, outline_colour: null })}>Default colours</button>}
      </div>
      <label>Size: {look.size ?? 100}%<input type="range" className="slider" min={spec.size[0]} max={spec.size[1]} step={5} value={look.size ?? 100}
        onChange={(e) => set({ size: +e.target.value })} /></label>
      {spec.cases.length > 0 && <label>Case<select value={look.case || "upper"} onChange={(e) => set({ case: e.target.value })}>
        {spec.cases.map((c) => <option key={c} value={c}>{c === "upper" ? "UPPER CASE" : c === "as_typed" ? "As typed" : tidy(c)}</option>)}</select></label>}
      <label className="check m-0"><input type="checkbox" checked={look.y != null} onChange={(e) => set({ y: e.target.checked ? 0.72 : null })} /><span>Choose the row myself</span></label>
      {look.y != null && <label>Row: {Math.round(look.y * 100)}% from the top<input type="range" className="slider" min={spec.y[0]} max={spec.y[1]} step={0.01} value={look.y}
        onChange={(e) => set({ y: +e.target.value })} /></label>}
      <p className="muted small m-0">The caption never covers the streamer&apos;s face or the game&apos;s HUD: the render moves it off them if it would.</p>
    </fieldset>
  );
}

// Only the fields the user set: every field left out keeps the style's own (the API's rule).
export const tidyLook = (l: CaptionLook): CaptionLook | null => {
  const out = Object.fromEntries(Object.entries(l).filter(([k, v]) => v !== null && v !== undefined && !((k === "italic" || k === "underline") && v === false)
    && !(k === "case" && v === "upper")));
  return Object.keys(out).length ? out : null;
};
