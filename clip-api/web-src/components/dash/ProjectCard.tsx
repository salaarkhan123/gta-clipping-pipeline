"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { clock } from "@/lib/api";
import { DeleteUploadControl } from "./DeleteUploadControl";
import { Icon } from "./Icon";

const DAY = 24 * 3600 * 1000;
const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

// When the stored video and its clips are deleted, in whole days (the API's `expires_at`).
function expiry(iso: string | undefined): { text: string; soon: boolean } | null {
  if (!iso) return null;
  const days = Math.ceil((Date.parse(iso) - Date.now()) / DAY);
  if (Number.isNaN(days)) return null;
  return { text: days <= 0 ? "Expires today" : `Expires in ${days} day${days === 1 ? "" : "s"}`, soon: days <= 2 };
}

const PILL = "absolute top-2 z-[1] rounded-full bg-[rgba(7,8,10,.8)] px-2 py-[2px] font-body text-[11px] font-semibold leading-[normal]";

// One stored video as a list item and card: its thumbnail (its best clip's frame) in a card of the same shape, 9:16 for a vertical
// clip and 16:9 for a wide one, with the clip count, length and expiry on it; then its name and when it was added.
// Fields from GET /v1/projects.
// `small`: the size for Home's sideways row (same picture height for both shapes).
// `onDeleted`: soft-delete via DELETE /v1/uploads/{id}; parent refreshes the list.
export function ProjectCard({ p, small, onDeleted }: { p: any; small?: boolean; onDeleted?: (uploadId: string) => void }) {
  const ends = expiry(p.expires_at);
  const shape = useShape(p.thumb_url, "wide");
  return (
    <li className={`${(small ? SMALL_WIDTH : CARD_WIDTH)[shape]} ${small ? "snap-start" : ""}`}>
    <div className="grid gap-1">
    <Link href={`/dashboard/project/?id=${p.upload_id}`} className="group grid gap-1 rounded-12 [overflow-wrap:anywhere]">
      <span style={p.thumb_url ? thumbVar(p.thumb_url) : undefined} className={`relative grid ${MEDIA[shape]} place-items-center overflow-hidden rounded-[14px] border border-solid border-transparent bg-card text-[13px] text-muted transition-[border-color] duration-200
        ease-[ease] group-hover:border-line-strong after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:top-[45%] after:bg-[linear-gradient(transparent,rgba(0,0,0,.78))] after:content-[''] ${p.thumb_url ? BACKDROP : ""}`}>
        {p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" className="relative h-full w-full object-contain" /> : <Icon name="film" size={30} />}
        {p.active && <span className={`${PILL} left-2 text-cyan`}>Working on it</span>}
        <span className={`${PILL} right-2 tabular-nums text-text`}>{clock(p.duration_sec)}</span>
        <span className="absolute bottom-2 left-[10px] z-[1] grid text-left font-body text-[12px] font-semibold leading-[1.35] text-text">
          <b>{p.clips ? `${p.clips} clip${p.clips === 1 ? "" : "s"}` : p.active ? "Making clips" : p.jobs ? "No clips" : "Not started"}</b>
          {ends && <span className={ends.soon ? "text-warn" : ""}>{ends.text}</span>}
        </span>
      </span>
      <strong title={p.filename} className="mt-[6px] overflow-hidden text-ellipsis whitespace-nowrap font-body text-[14px] font-medium leading-[1.3]">{p.filename}</strong>
      <span className="muted text-[12.5px]">Added {shortDate(p.created_at)}</span>
    </Link>
    {onDeleted && <DeleteUploadControl uploadId={p.upload_id} name={p.filename} onDeleted={onDeleted} compact={small} />}
    </div>
    </li>
  );
}

// Cards take the shape of their thumbnail: "tall" (9:16) for a vertical clip, "wide" (16:9) otherwise. The shape is
// read from the image itself (the API does not send a clip's aspect), `fallback` until it has loaded.
// Mixed shapes stay tidy: every card's picture is the same height and its width follows its shape (MEDIA and
// CARD_WIDTH), and the cards wrap in a flex row (CARD_ROW), so a row of mixed cards lines up like a film strip.
// On a phone two tall cards share a row and a wide card takes the whole row.
export type Shape = "tall" | "wide";
export function useShape(src: string | null | undefined, fallback: Shape = "tall"): Shape {
  const [shape, setShape] = useState<Shape>(fallback);
  useEffect(() => {
    if (!src) return;
    const img = new Image();
    img.onload = () => setShape(img.naturalWidth > img.naturalHeight ? "wide" : "tall");
    img.src = src;
  }, [src]);
  return shape;
}
export const MEDIA: Record<Shape, string> = { tall: "aspect-[9/16]", wide: "aspect-video" };
export const CARD_WIDTH: Record<Shape, string> = { tall: "w-[200px] flex-none narrow:w-[calc((100%-10px)/2)]", wide: "w-[632px] max-w-full flex-none narrow:w-full" };
const SMALL_WIDTH: Record<Shape, string> = { tall: "w-[180px] flex-none", wide: "w-[320px] flex-none" };
export const CARD_ROW = "flex flex-wrap items-start gap-[14px] narrow:gap-[10px]";
// A picture whose shape is between the two (4:5, 1:1) sits whole in the middle; the frame's sides are filled by a
// blurred, darkened copy of the same image drawn in CSS (the frame's ::before). Put `thumbVar(url)` in the frame's
// style and BACKDROP in its classes; the picture itself needs `relative`.
export const thumbVar = (src: string) => ({ "--thumb": `url("${src.replace(/"/g, "%22")}")` }) as React.CSSProperties;
export const BACKDROP = "before:pointer-events-none before:absolute before:inset-[-16px] before:content-[''] before:[background:var(--thumb)_center/cover_no-repeat] before:blur-[14px] before:brightness-[.45]";

// `row`: one line that scrolls sideways (Home's recent projects), cards a little smaller. Otherwise the cards wrap (Library).
export const ProjectGrid = ({ projects, row, onDeleted }: { projects: any[]; row?: boolean; onDeleted?: (uploadId: string) => void }) => (
  <ul className={`list-none ${row
    ? "flex snap-x snap-mandatory items-start gap-[14px] overflow-x-auto pb-[6px] narrow:gap-[10px]"
    : CARD_ROW}`}>
    {projects.map((p) => <ProjectCard key={p.upload_id} p={p} small={row} onDeleted={onDeleted} />)}
  </ul>
);
