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
// or Enter opens the player. On the picture: the score (its sub-scores on hover), the tick box, and your own marks.
// Right under it one row: Edit, then download. Then the name, the length and where it sits in the video, and one
// line on why it was picked.
export function ClipTile({ clip, name, shape, game, selected, selecting, onSelect, onOpen, onFeedback, layout = "grid", editHref }: {
  clip: any; name: string; shape: Shape; game: string | null; selected: boolean; selecting?: boolean; editHref?: string;
  onSelect: (id: string, on: boolean) => void; onOpen: () => void; onFeedback: (f: Feedback) => void;
  layout?: ClipLayout;
}) {
  const preview = clip.preview_url || clip.video_url;
  const length = lengthOf(clip);
  const discarded = clip.kept === false, why = whyLine(clip);
  const range = typeof clip.start_sec === "number" && typeof clip.end_sec === "number" ? `${clock(clip.start_sec)} to ${clock(clip.end_sec)}` : null;
  const edit = editHref && <Link href={editHref} className="btn small ghost flex-none" aria-label={`Edit ${name}`}><Icon name="pencil" size={15} />Edit</Link>;
  const download = clip.video_url && <a href={clip.video_url} download aria-label={`Download ${name}`} title="Download"
    className="grid h-9 w-9 flex-none place-items-center rounded-control text-fg-2 no-underline transition-colors duration-base hover:bg-control hover:text-text"><Icon name="download" size={16} /></a>;
  const facts = <>
    <span>{clock(length)}</span>
    {range && <><Dot /><span>{range}</span></>}
    {game && <><Dot /><span className="truncate">{game}</span></>}
    {clip.kind && <><Dot /><span>{kindName(clip.kind)}</span></>}
    {discarded && <><Dot /><span>Discarded</span></>}
    {!discarded && clip.edit && <><Dot /><span>Edited</span></>}
  </>;
  if (layout === "list") {
    return (
      <article id={`clip-${clip.id}`} aria-label={name} tabIndex={-1}
        className={`group/tile flex min-w-0 scroll-mt-24 items-center gap-4 rounded-16 bg-card p-3 ring-inset focus:outline-none narrow:gap-3
          ${selected ? "ring-2 ring-lime" : "ring-0"}
          ${discarded ? "opacity-50" : ""}`}>
        <input type="checkbox" checked={selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
          className="h-[18px] w-[18px] flex-none cursor-pointer accent-lime" />
        <button type="button" onClick={onOpen} aria-label={`Play ${name}`}
          className={`relative flex-none cursor-pointer overflow-hidden rounded-12 border-0 bg-control p-0 ${shape === "wide" ? "h-[72px] w-32 narrow:h-[54px] narrow:w-24" : "h-24 w-[54px]"}`}>
          {clip.thumb_url
            ? <img src={clip.thumb_url} alt="" loading="lazy" className="h-full w-full object-cover" />
            : <span className="grid h-full place-items-center text-fg-3"><Icon name="film" size={18} /></span>}
        </button>
        <RatingBadge clip={clip} size="sm" />
        <button type="button" onClick={onOpen} tabIndex={-1} title={name}
          className="grid min-w-0 flex-1 cursor-pointer gap-1 border-0 bg-transparent p-0 text-left">
          <h3 className="m-0 truncate font-sans text-[14px] font-medium leading-[1.35] text-text">{name}</h3>
          <p className="m-0 flex min-w-0 flex-wrap items-center gap-x-[6px] text-[12.5px] tabular-nums text-fg-2">{facts}</p>
          {why && <p className="m-0 truncate text-[12.5px] text-fg-2 narrow:hidden">{why}</p>}
        </button>
        <span className="flex flex-none items-center gap-1 narrow:flex-col-reverse">{download}{edit}</span>
      </article>
    );
  }
  const marked = clip.reaction || clip.bookmarked;
  return (
    <ClipCard id={`clip-${clip.id}`} shape={shape} poster={clip.thumb_url} video={preview} selected={selected} dim={discarded}
      onOpen={onOpen} openLabel={`Play ${name}`} aria-label={name}
      score={<RatingBadge clip={clip} />}
      corner={<input type="checkbox" checked={selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
        className={`h-[18px] w-[18px] cursor-pointer accent-lime transition-opacity duration-fast narrow:h-6 narrow:w-6
          ${selected || selecting ? "opacity-100" : "opacity-0 group-hover/clip:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"}`} />}
      side={<span role="group" aria-label="Rate this clip"
        className={`grid gap-1 transition-opacity duration-fast ${marked ? "opacity-100" : "opacity-0 group-hover/clip:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100"}`}>
        <Toggle icon="like" label="Like" on={clip.reaction === "like"} onClick={() => onFeedback({ reaction: clip.reaction === "like" ? null : "like" })} />
        <Toggle icon="dislike" label="Dislike" on={clip.reaction === "dislike"} onClick={() => onFeedback({ reaction: clip.reaction === "dislike" ? null : "dislike" })} />
        <Toggle icon="bookmark" label="Bookmark" on={!!clip.bookmarked} onClick={() => onFeedback({ bookmarked: !clip.bookmarked })} />
      </span>}
      bar={<>{edit}<span className="flex-1" />{download}</>}
      title={<button type="button" onClick={onOpen} tabIndex={-1} title={name} className="cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] text-inherit hover:underline">{name}</button>}
      meta={facts}
      why={why} />
  );
}
const Dot = () => <span aria-hidden="true" className="text-fg-3">·</span>;

function Toggle({ icon, label, on, onClick }: { icon: IconName; label: string; on: boolean; onClick: () => void }) {
  return <button type="button" aria-pressed={on} aria-label={label} title={label} onClick={onClick}
    className={`grid h-8 w-8 cursor-pointer place-items-center rounded-control border-0 transition-colors duration-base [backdrop-filter:blur(8px)]
      ${on ? "bg-lime text-ink" : "bg-black/60 text-white hover:bg-black/80"}`}><Icon name={icon} size={15} /></button>;
}
// A card-shaped placeholder while a run is still finding clips.
export function TileSkeleton({ shape, layout = "grid" }: { shape: Shape; layout?: ClipLayout }) {
  if (layout === "list") {
    return (
      <div aria-hidden="true" className="flex items-center gap-4 rounded-16 bg-card p-3">
        <span className="h-[18px] w-[18px] flex-none animate-pulse rounded bg-control" />
        <span className={`flex-none animate-pulse rounded-12 bg-control ${shape === "wide" ? "h-[72px] w-32" : "h-24 w-[54px]"}`} />
        <span className="h-[14px] min-w-0 flex-1 animate-pulse rounded-pill bg-control" />
        <span className="h-9 w-[76px] flex-none animate-pulse rounded-control bg-control" />
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
