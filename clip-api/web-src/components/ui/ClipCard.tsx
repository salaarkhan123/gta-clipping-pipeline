"use client";
import { useRef, useState } from "react";
import { Icon } from "@/components/dash/Icon";

// One clip: a large picture with the score bottom-left and nothing else on it, then the title, one line of
// facts and one line saying why it was picked. Pointing at it plays the preview.
// `score` is a <Score>; `corner` (top-left) is for a selection box and `side` (top-right) for the viewer's own
// marks; `bar` is the row right under the picture (the way in to the editor, download); `actions` sit under the text.
export type ClipShape = "tall" | "square" | "wide";
const SHAPE: Record<ClipShape, string> = { tall: "aspect-[9/16]", square: "aspect-[4/5]", wide: "aspect-video" };

export function ClipCard({ shape = "tall", poster, video, webm, title, meta, why, score, corner, side, bar, actions, onOpen, openLabel, selected, dim, autoPlay, id, "aria-label": label }: {
  shape?: ClipShape; poster?: string | null; video?: string | null; webm?: string | null;
  title?: React.ReactNode; meta?: React.ReactNode; why?: React.ReactNode; score?: React.ReactNode; corner?: React.ReactNode; side?: React.ReactNode; bar?: React.ReactNode; actions?: React.ReactNode;
  onOpen?: () => void; openLabel?: string; selected?: boolean; dim?: boolean; autoPlay?: boolean; id?: string; "aria-label"?: string;
}) {
  const [hover, setHover] = useState(false);
  const ref = useRef<HTMLVideoElement>(null);
  const live = !!video && (autoPlay || hover);
  return (
    <article id={id} aria-label={label} tabIndex={-1} className={`group/clip grid min-w-0 scroll-mt-24 content-start gap-3 focus:outline-none ${dim ? "opacity-50" : ""}`}>
      <div className={`relative ${SHAPE[shape]} rounded-16 bg-control transition-[box-shadow,transform] duration-base ease-out
        ${selected ? "shadow-[0_0_0_2px_theme(colors.lime)]" : "group-hover/clip:shadow-[0_0_0_1px_rgba(255,255,255,.22)]"}`}
        onPointerEnter={(e) => { if (e.pointerType === "mouse") setHover(true); }} onPointerLeave={() => setHover(false)}>
        {/* Only the picture is clipped to the rounded box: the score's sub-score panel opens past the card's edges. */}
        <div className="absolute inset-0 overflow-hidden rounded-16">
        {poster ? <img src={poster} alt="" loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover" />
          : <span className="absolute inset-0 grid place-items-center text-fg-3"><Icon name="film" size={28} /></span>}
        {live && <video ref={ref} muted autoPlay loop playsInline preload="auto" aria-hidden="true" className="absolute inset-0 h-full w-full object-cover">
          {webm && <source src={webm} type="video/webm" />}<source src={video!} type="video/mp4" /></video>}
        {onOpen && <button type="button" onClick={onOpen} aria-label={openLabel}
          className="absolute inset-0 z-[1] block cursor-pointer border-0 bg-transparent p-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-lime" />}
        </div>
        {score && <div className="absolute bottom-2 left-2 z-[2] focus-within:z-30 hover:z-30">{score}</div>}
        {corner && <div className="absolute left-2 top-2 z-[2]">{corner}</div>}
        {side && <div className="absolute right-2 top-2 z-[2]">{side}</div>}
      </div>
      {bar && <div className="flex min-w-0 items-center gap-1">{bar}</div>}
      {(title || meta || why) && <div className="grid min-w-0 gap-1 px-[2px]">
        {title && <h3 className="m-0 line-clamp-2 font-sans text-[14px] font-medium leading-[1.35] text-text">{title}</h3>}
        {meta && <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-[6px] text-[12.5px] tabular-nums text-fg-2">{meta}</p>}
        {why && <p className="m-0 line-clamp-2 text-[12.5px] leading-[1.4] text-fg-2">{why}</p>}
      </div>}
      {actions && <div className="flex flex-wrap items-center gap-2 px-[2px]">{actions}</div>}
    </article>
  );
}
