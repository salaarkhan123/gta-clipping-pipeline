"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { clock } from "@/lib/api";
import { DeleteUploadControl } from "./DeleteUploadControl";
import { Dropdown, MenuItem, MenuRule } from "@/components/ui/Dropdown";
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

// What the strip along the bottom of the picture says: what is happening to the video, or when it is deleted.
function status(p: any): { text: string; tone: string } {
  if (p.active) return { text: "Making clips", tone: "text-cyan" };
  const ends = expiry(p.expires_at);
  if (ends) return { text: ends.text, tone: ends.soon ? "text-warn" : "text-fg-2" };
  return { text: p.jobs ? "No clips" : "Not started", tone: "text-fg-2" };
}

// One stored video as a list item: a 16:9 picture (its best clip's frame, cropped to fit: the API has no frame of
// the source video itself) with its length top-right and a status strip along the bottom, then its name with a
// "…" menu, then the clip count and the day it was added. Fields from GET /v1/projects.
// `onDeleted`: soft-delete via DELETE /v1/uploads/{id}; parent refreshes the list.
export function ProjectCard({ p, onDeleted }: { p: any; onDeleted?: (uploadId: string) => void }) {
  const [deleting, setDeleting] = useState(false);
  const href = `/dashboard/project/?id=${p.upload_id}`, state = status(p);
  return (
    <li className="grid min-w-0 content-start">
      <Link href={href} aria-label={`Open ${p.filename}`} className="group relative block aspect-video overflow-hidden rounded-12 bg-card text-fg-3">
        {p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" className="block h-full w-full object-cover [object-position:center_30%] transition-transform duration-slow ease-out group-hover:scale-[1.03]" />
          : <span className="grid h-full w-full place-items-center pb-6"><Icon name="film" size={28} /></span>}
        <span className="absolute right-2 top-2 rounded-pill bg-black/60 px-[9px] py-[3px] font-sans text-[12px] font-medium leading-[1.35] tabular-nums text-text [backdrop-filter:blur(8px)]">{clock(p.duration_sec)}</span>
        <span className={`absolute inset-x-0 bottom-0 flex h-6 items-center justify-center bg-black/70 font-sans text-[12px] leading-none [backdrop-filter:blur(8px)] ${state.tone}`}>{state.text}</span>
      </Link>
      <div className="mt-[10px] flex min-w-0 items-center gap-2">
        <Link href={href} title={p.filename} tabIndex={-1} className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-sans text-[15px] font-medium leading-[24px] text-text no-underline">{p.filename}</Link>
        <Dropdown label={`Actions for ${p.filename}`} align="end" panelClass="w-[190px]"
          trigger={(t) => <button {...t} type="button" aria-label={`Actions for ${p.filename}`} title="More"
            className="grid h-6 w-7 flex-none cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-fg-2 transition-colors duration-base hover:bg-control hover:text-text aria-expanded:bg-control"><Icon name="dots" size={18} /></button>}>
          {(close) => <>
            <MenuItem icon="play" href={href}>Open project</MenuItem>
            <MenuItem icon="scissors" href={`${href}&tool=clips`}>Make clips</MenuItem>
            {onDeleted && <><MenuRule /><MenuItem icon="trash" danger onSelect={() => { close(); setDeleting(true); }}>Delete</MenuItem></>}
          </>}
        </Dropdown>
      </div>
      <p className="mx-0 mb-0 mt-[3px] flex items-center gap-2 font-sans text-[13px] leading-[20px] text-fg-2">
        <span>{p.clips ? `${p.clips} clip${p.clips === 1 ? "" : "s"}` : "No clips yet"}</span>
        <span className="h-3 w-px bg-line-strong" aria-hidden="true" />
        <span>{shortDate(p.created_at)}</span>
      </p>
      {onDeleted && deleting && <div className="mt-2"><DeleteUploadControl uploadId={p.upload_id} name={p.filename} onDeleted={onDeleted} compact asking onClose={() => setDeleting(false)} /></div>}
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
export const CARD_ROW = "flex flex-wrap items-start gap-[14px] narrow:gap-[10px]";
// A picture whose shape is between the two (4:5, 1:1) sits whole in the middle; the frame's sides are filled by a
// blurred, darkened copy of the same image drawn in CSS (the frame's ::before). Put `thumbVar(url)` in the frame's
// style and BACKDROP in its classes; the picture itself needs `relative`.
export const thumbVar = (src: string) => ({ "--thumb": `url("${src.replace(/"/g, "%22")}")` }) as React.CSSProperties;
export const BACKDROP = "before:pointer-events-none before:absolute before:inset-[-16px] before:content-[''] before:[background:var(--thumb)_center/cover_no-repeat] before:blur-[14px] before:brightness-[.45]";

// Project cards in a grid. `size`: "home" is Home's recent projects (cards 243 px wide, as many as fit a row);
// "grid" is My projects (at least 188 px, sharing the row). `lead` is a tile placed before the first card.
export const PROJECT_GRID = {
  home: "grid-cols-[repeat(auto-fill,243px)] narrow:grid-cols-2",
  grid: "grid-cols-[repeat(auto-fill,minmax(188px,1fr))] narrow:grid-cols-2",
};
export const ProjectGrid = ({ projects, size = "grid", lead, onDeleted }: { projects: any[]; size?: keyof typeof PROJECT_GRID; lead?: React.ReactNode;
  onDeleted?: (uploadId: string) => void }) => (
  <ul className={`m-0 grid list-none gap-x-4 gap-y-6 p-0 narrow:gap-x-3 ${PROJECT_GRID[size]}`}>
    {lead}
    {projects.map((p) => <ProjectCard key={p.upload_id} p={p} onDeleted={onDeleted} />)}
  </ul>
);
