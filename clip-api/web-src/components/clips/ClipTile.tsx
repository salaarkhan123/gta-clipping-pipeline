"use client";
import Link from "next/link";
import { clock } from "@/lib/api";
import { Icon, IconName } from "@/components/dash/Icon";
import type { ClipLayout } from "@/lib/clip-layout";
import { RatingBadge } from "./Rating";
import { ClipCard } from "@/components/ui/ClipCard";
import { ASPECT_CLASS, kindName, lengthOf, Shape, whyLine } from "./model";

export type Feedback = { kept?: boolean | null; reaction?: "like" | "dislike" | null; bookmarked?: boolean };

// One clip in the results grid, in its own shape (9:16, 4:5 or 16:9). Pointing at it plays a muted preview; a click
// or Enter opens the player. Only the score sits on the picture (its sub-scores on hover); under it the name, length,
// game and kind, one line on why it was picked, then Edit clip and your own marks.
export function ClipTile({ clip, name, shape, game, selected, onSelect, onOpen, onFeedback, layout = "grid", editHref }: {
  clip: any; name: string; shape: Shape; game: string | null; selected: boolean; editHref?: string;
  onSelect: (id: string, on: boolean) => void; onOpen: () => void; onFeedback: (f: Feedback) => void;
  layout?: ClipLayout;
}) {
  const preview = clip.preview_url || clip.video_url;
  const length = lengthOf(clip);
  const discarded = clip.kept === false, why = whyLine(clip);
  if (layout === "list") {
    return (
      <article id={`clip-${clip.id}`} aria-label={name} tabIndex={-1}
        className={`group/tile flex min-w-0 scroll-mt-24 items-center gap-3 rounded-12 bg-card px-2 py-2 ring-inset focus:outline-none
          ${selected ? "ring-2 ring-lime" : "ring-0 hover:bg-control"}
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
        <RatingBadge clip={clip} size="sm" />
      </article>
    );
  }
  // The card: a large picture with only the score on it; under it the name, the facts, why it was picked, and
  // one clear way into the editor beside your own marks.
  return (
    <ClipCard id={`clip-${clip.id}`} shape={shape} poster={clip.thumb_url} video={preview} selected={selected} dim={discarded}
      onOpen={onOpen} openLabel={`Play ${name}`} aria-label={name}
      score={<RatingBadge clip={clip} />}
      corner={<input type="checkbox" checked={selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
        className={`h-[18px] w-[18px] cursor-pointer accent-lime transition-opacity duration-fast narrow:h-6 narrow:w-6
          ${selected ? "opacity-100" : "opacity-0 group-hover/clip:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"}`} />}
      title={<button type="button" onClick={onOpen} tabIndex={-1} title={name} className="cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] text-inherit hover:underline">{name}</button>}
      meta={<>
        <span>{clock(length)}</span>
        {game && <><Dot /><span className="truncate">{game}</span></>}
        {clip.kind && <><Dot /><span>{kindName(clip.kind)}</span></>}
        {discarded && <><Dot /><span>Discarded</span></>}
        {!discarded && clip.edit && <><Dot /><span>Edited</span></>}
      </>}
      why={why}
      actions={<>
        {editHref && <Link href={editHref} className="btn small ghost mr-auto"><Icon name="pencil" size={15} />Edit clip</Link>}
        <span className="flex items-center gap-1" role="group" aria-label="Rate this clip">
          <Toggle icon="like" label="Like" on={clip.reaction === "like"} onClick={() => onFeedback({ reaction: clip.reaction === "like" ? null : "like" })} />
          <Toggle icon="dislike" label="Dislike" on={clip.reaction === "dislike"} onClick={() => onFeedback({ reaction: clip.reaction === "dislike" ? null : "dislike" })} />
          <Toggle icon="bookmark" label="Bookmark" on={!!clip.bookmarked} onClick={() => onFeedback({ bookmarked: !clip.bookmarked })} />
        </span>
      </>} />
  );
}

const Dot = () => <span aria-hidden="true" className="text-fg-3">·</span>;

function Toggle({ icon, label, on, onClick }: { icon: IconName; label: string; on: boolean; onClick: () => void }) {
  return <button type="button" aria-pressed={on} aria-label={label} title={label} onClick={onClick}
    className={`grid h-9 w-9 cursor-pointer place-items-center rounded-control border-0 transition-colors duration-base
      ${on ? "bg-lime text-ink" : "bg-transparent text-fg-2 hover:bg-control hover:text-text"}`}><Icon name={icon} size={16} /></button>;
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
