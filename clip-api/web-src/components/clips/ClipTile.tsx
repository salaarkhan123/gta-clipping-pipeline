"use client";
import { useRef, useState } from "react";
import { clock } from "@/lib/api";
import { Icon, IconName } from "@/components/dash/Icon";
import type { ClipLayout } from "@/lib/clip-layout";
import { RatingBadge } from "./Rating";
import { ASPECT_CLASS, kindName, lengthOf, Shape } from "./model";

const CHIP = "pointer-events-none rounded-pill bg-[rgba(0,0,0,.62)] px-2 py-[3px] font-sans text-[11px] font-medium leading-[1.3] text-text [backdrop-filter:blur(6px)]";

export type Feedback = { kept?: boolean | null; reaction?: "like" | "dislike" | null; bookmarked?: boolean };

// One clip in the results grid, in its own shape (9:16, 4:5 or 16:9). Pointing at it plays a muted preview; a click
// or Enter opens the player. The AI rating sits on the picture with its sub-scores on hover; under it the title,
// length, game and kind. Like, dislike and bookmark are on the picture (always shown on touch screens).
export function ClipTile({ clip, name, shape, game, selected, onSelect, onOpen, onFeedback, layout = "grid" }: {
  clip: any; name: string; shape: Shape; game: string | null; selected: boolean;
  onSelect: (id: string, on: boolean) => void; onOpen: () => void; onFeedback: (f: Feedback) => void;
  layout?: ClipLayout;
}) {
  const [hover, setHover] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const preview = clip.preview_url || clip.video_url;
  const length = lengthOf(clip);
  const discarded = clip.kept === false;
  if (layout === "list") {
    return (
      <article id={`clip-${clip.id}`} aria-label={name} tabIndex={-1}
        className={`group/tile flex min-w-0 scroll-mt-24 items-center gap-3 rounded-12 bg-card px-2 py-2 ring-1 ring-inset focus:outline-none
          ${selected ? "ring-2 ring-lime" : "ring-[rgba(255,255,255,.06)] hover:ring-[rgba(255,255,255,.14)]"}
          ${discarded ? "opacity-50" : ""}`}>
        <input type="checkbox" checked={selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
          className="h-5 w-5 flex-none cursor-pointer accent-lime" />
        <button type="button" onClick={onOpen} aria-label={`Play ${name}`}
          className="relative h-14 w-10 flex-none cursor-pointer overflow-hidden rounded-8 border-0 bg-card-2 p-0">
          {clip.thumb_url
            ? <img src={clip.thumb_url} alt="" loading="lazy" className="h-full w-full object-cover" />
            : <span className="grid h-full place-items-center text-dim"><Icon name="film" size={18} /></span>}
        </button>
        <button type="button" onClick={onOpen} aria-label={`Play ${name}`}
          className="grid min-w-0 flex-1 cursor-pointer gap-[2px] border-0 bg-transparent p-0 text-left">
          <h3 title={name} className="m-0 truncate font-sans text-[14px] font-semibold leading-[1.32] tracking-[-0.01em] text-text">{name}</h3>
          <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-[6px] text-[12.5px] text-fg-2">
            {game && <span className="truncate">{game}</span>}
            {game && clip.kind && <Dot />}
            {clip.kind && <span>{kindName(clip.kind)}</span>}
          </p>
        </button>
        <span className="flex-none tabular-nums text-[12.5px] text-fg-2">{clock(length)}</span>
        <RatingBadge clip={clip} />
      </article>
    );
  }
  return (
    <article id={`clip-${clip.id}`} aria-label={name} tabIndex={-1}
      className={`group/tile grid min-w-0 scroll-mt-24 content-start gap-[10px] focus:outline-none ${discarded ? "opacity-50" : ""}`}>
      <div className="relative">
        <div className={`relative ${ASPECT_CLASS[shape]} overflow-hidden rounded-16 bg-card-2 shadow-card transition-shadow duration-200
          ${selected ? "ring-2 ring-lime" : "group-hover/tile:shadow-[inset_0_0_0_1px_rgba(255,255,255,.22)]"}`}
          onPointerEnter={(e) => { if (e.pointerType === "mouse") setHover(true); }} onPointerLeave={() => setHover(false)}>
          {clip.thumb_url
            ? <img src={clip.thumb_url} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" />
            : <span className="absolute inset-0 grid place-items-center text-dim"><Icon name="film" size={30} /></span>}
          {hover && preview && <video ref={video} src={preview} muted autoPlay loop playsInline preload="auto" aria-hidden="true"
            className="absolute inset-0 h-full w-full object-cover" />}
          <button type="button" onClick={onOpen} aria-label={`Play ${name}`}
            className="absolute inset-0 z-[1] block cursor-pointer border-0 bg-transparent p-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-lime">
            <span className="pointer-events-none absolute inset-x-0 bottom-0 h-[38%] bg-[linear-gradient(transparent,rgba(0,0,0,.72))]" aria-hidden="true" />
            <span className={`pointer-events-none absolute left-1/2 top-1/2 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[rgba(255,255,255,.92)] text-btn-ink
              transition-[opacity,transform] duration-150 ${hover ? "scale-100 opacity-100" : "scale-90 opacity-0"}`} aria-hidden="true"><Icon name="play" size={20} /></span>
          </button>
          <span className={`${CHIP} absolute right-2 top-2 z-[2] tabular-nums`}>{clock(length)}</span>
          {discarded && <span className={`${CHIP} absolute bottom-2 right-2 z-[2]`}>Discarded</span>}
          {!discarded && clip.edit && <span className={`${CHIP} absolute bottom-2 right-2 z-[2]`}>Edited</span>}
          <div className="absolute right-2 top-10 z-[2] grid gap-[6px] opacity-0 transition-opacity duration-150 group-hover/tile:opacity-100 group-focus-within/tile:opacity-100
            has-[[aria-pressed=true]]:opacity-100 [@media(hover:none)]:opacity-100" role="group" aria-label="Rate this clip">
            <Toggle icon="like" label="Like" on={clip.reaction === "like"} onClick={() => onFeedback({ reaction: clip.reaction === "like" ? null : "like" })} />
            <Toggle icon="dislike" label="Dislike" on={clip.reaction === "dislike"} onClick={() => onFeedback({ reaction: clip.reaction === "dislike" ? null : "dislike" })} />
            <Toggle icon="bookmark" label="Bookmark" on={!!clip.bookmarked} onClick={() => onFeedback({ bookmarked: !clip.bookmarked })} />
          </div>
        </div>
        <input type="checkbox" checked={selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
          className={`absolute left-2 top-2 z-[3] h-[18px] w-[18px] cursor-pointer accent-lime transition-opacity duration-150 narrow:h-6 narrow:w-6
            ${selected ? "opacity-100" : "opacity-0 group-hover/tile:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"}`} />
        <div className="absolute bottom-2 left-2 z-[3]"><RatingBadge clip={clip} /></div>
      </div>
      <div className="grid min-w-0 gap-[3px] px-[2px]">
        <h3 title={name} className="m-0 line-clamp-2 font-sans text-[14px] font-semibold leading-[1.32] tracking-[-0.01em] text-text">
          <button type="button" onClick={onOpen} tabIndex={-1} className="cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] text-inherit hover:underline">{name}</button></h3>
        <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-[6px] text-[12.5px] text-fg-2">
          <span className="tabular-nums">{clock(length)}</span>
          {game && <><Dot /><span className="truncate">{game}</span></>}
          {clip.kind && <><Dot /><span>{kindName(clip.kind)}</span></>}
        </p>
      </div>
    </article>
  );
}

const Dot = () => <span aria-hidden="true" className="text-fg-3">·</span>;

function Toggle({ icon, label, on, onClick }: { icon: IconName; label: string; on: boolean; onClick: () => void }) {
  return <button type="button" aria-pressed={on} aria-label={label} title={label} onClick={onClick}
    className={`grid h-8 w-8 cursor-pointer place-items-center rounded-full border-0 [backdrop-filter:blur(6px)] narrow:h-9 narrow:w-9
      ${on ? "bg-lime text-ink" : "bg-[rgba(0,0,0,.62)] text-text hover:bg-[rgba(0,0,0,.85)]"}`}><Icon name={icon} size={16} /></button>;
}

// A card-shaped placeholder while a run is still finding clips.
export function TileSkeleton({ shape, layout = "grid" }: { shape: Shape; layout?: ClipLayout }) {
  if (layout === "list") {
    return (
      <div aria-hidden="true" className="flex items-center gap-3 rounded-12 bg-card px-2 py-2">
        <span className="h-5 w-5 flex-none animate-pulse rounded bg-card-2" />
        <span className="h-14 w-10 flex-none animate-pulse rounded-8 bg-card-2" />
        <span className="h-[14px] min-w-0 flex-1 animate-pulse rounded-pill bg-card-2" />
        <span className="h-[12px] w-10 flex-none animate-pulse rounded-pill bg-card-2" />
      </div>
    );
  }
  return (
    <div aria-hidden="true" className="grid content-start gap-[10px]">
      <div className={`${ASPECT_CLASS[shape]} animate-pulse rounded-16 bg-card`} />
      <div className="grid gap-[6px] px-[2px]"><span className="h-[12px] w-4/5 animate-pulse rounded-pill bg-card" /><span className="h-[10px] w-2/5 animate-pulse rounded-pill bg-card" /></div>
    </div>
  );
}
