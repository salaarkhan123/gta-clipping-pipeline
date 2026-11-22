"use client";
// Sticky composer on the gaming style gallery: raw footage + our template as style reference + optional
// brand-adapt note. Submit opens the existing Clip Maker handoff. Claude / ChatGPT connectors are shown
// disabled — ClutchClips has no chat-LLM connectors yet.
import Link from "next/link";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon } from "./Icon";

export type StyleRef = { id: string; name: string };

const SLOT = "flex min-h-[52px] min-w-0 flex-1 items-center gap-3 rounded-16 border border-solid border-line bg-panel px-4 py-3 text-left font-sans text-[14px] text-text transition-colors hover:border-line-strong hover:bg-chip-hover disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:border-line disabled:hover:bg-panel";
const PILL = "inline-flex items-center gap-2 rounded-full border border-solid border-line-soft bg-transparent px-3 py-[7px] font-sans text-[13px] text-fg-3";

export function StyleComposer({ style, note, onNote, onFootage, onClip, onClearStyle, canSubmit }: {
  style: StyleRef | null;
  note: string;
  onNote: (v: string) => void;
  onFootage: () => void;
  onClip: () => void;
  onClearStyle: () => void;
  canSubmit: boolean;
}) {
  return (
    <div className="sticky bottom-3 z-30 mx-auto w-full max-w-[760px] rounded-[22px] border border-solid border-line bg-raised/95 p-3 shadow-pop [backdrop-filter:blur(12px)]">
      <div className="flex flex-wrap gap-2">
        <button type="button" className={SLOT} onClick={onFootage}>
          <span className="grid h-9 w-9 flex-none place-items-center rounded-12 bg-chip-hover text-lime"><Icon name="film" size={18} /></span>
          <span className="min-w-0"><span className="block font-medium">Add raw footage</span>
            <span className="block text-[12.5px] text-muted">Upload or pick a VOD you own</span></span>
        </button>
        <div className={`${SLOT} cursor-default hover:border-line hover:bg-panel`} aria-live="polite">
          <span className="grid h-9 w-9 flex-none place-items-center rounded-12 bg-chip-hover text-lime"><Icon name="template" size={18} /></span>
          <span className="min-w-0 flex-1">
            {style ? <>
              <span className="block font-medium">Style: {style.name}</span>
              <span className="block text-[12.5px] text-muted">ClutchClips game template · not a creator look</span>
            </> : <>
              <span className="block font-medium">Add a style reference</span>
              <span className="block text-[12.5px] text-muted">Pick Recreate on a card above</span>
            </>}
          </span>
          {style && <button type="button" className="icon-btn h-8 w-8 flex-none border-0" aria-label="Clear style" onClick={onClearStyle}><Icon name="close" size={16} /></button>}
        </div>
      </div>
      <label htmlFor="style-adapt" className="sr-only">Optional brand adapt note</label>
      <textarea id="style-adapt" rows={2} value={note} maxLength={300} onChange={(e) => onNote(e.target.value)}
        placeholder="(Optional) Adapt this look to your brand, e.g. ‘keep the layout, use my Brand Kit colors and a bold sans-serif’"
        className="mt-2 w-full resize-none rounded-16 border border-solid border-line bg-bg px-4 py-3 font-sans text-[14px] text-text placeholder:text-fg-3 focus:border-line-strong focus:outline-none" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" className="btn primary gap-2" disabled={!canSubmit} onClick={onClip}>
          <Icon name="scissors" size={16} />Clip with this style</button>
        <Link href="/dashboard/brand-kit/" className="btn small ghost gap-2"><Icon name="palette" size={15} />Brand kit</Link>
        <span className="ml-auto flex flex-wrap items-center gap-2" title="Chat connectors are not built. Editing stays inside ClutchClips.">
          <span className={PILL} aria-disabled="true"><Icon name="sparkle" size={14} />Edit in Claude<ComingSoonBadge short /></span>
          <span className={PILL} aria-disabled="true"><Icon name="sparkle" size={14} />ChatGPT plugin<ComingSoonBadge short /></span>
        </span>
      </div>
      <p className="m-0 mt-2 text-[12px] text-muted">Clips run in ClutchClips Clip Maker. Claude and ChatGPT connectors are not available — no chat agent is called from this page.</p>
    </div>
  );
}
