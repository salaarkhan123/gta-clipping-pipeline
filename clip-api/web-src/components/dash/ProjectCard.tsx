import Link from "next/link";
import { clock } from "@/lib/api";
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

// One stored video as a card: a 16:9 thumbnail (its best clip's frame, letterboxed when the clip is vertical) with
// the clip count, length and expiry on it; then its name and when it was added. Fields from GET /v1/projects.
export function ProjectCard({ p }: { p: any }) {
  const ends = expiry(p.expires_at);
  return (
    <Link href={`/dashboard/project/?id=${p.upload_id}`} className="group grid gap-1 rounded-12 [overflow-wrap:anywhere]">
      <span style={p.thumb_url ? thumbVar(p.thumb_url) : undefined} className={`relative grid aspect-video place-items-center overflow-hidden rounded-12 border border-solid border-line bg-card text-[13px] text-muted transition-[border-color] duration-200
        ease-[ease] group-hover:border-lime after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:top-[45%] after:bg-[linear-gradient(transparent,rgba(0,0,0,.78))] after:content-[''] ${p.thumb_url ? BACKDROP : ""}`}>
        {p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" className="relative h-full w-full object-contain" /> : <Icon name="film" size={30} />}
        {p.active && <span className={`${PILL} left-2 text-cyan`}>Working on it</span>}
        <span className={`${PILL} right-2 tabular-nums text-text`}>{clock(p.duration_sec)}</span>
        <span className="absolute bottom-2 left-[10px] z-[1] grid text-left font-body text-[12px] font-semibold leading-[1.35] text-text">
          <b>{p.clips ? `${p.clips} clip${p.clips === 1 ? "" : "s"}` : p.active ? "Making clips" : p.jobs ? "No clips" : "Not started"}</b>
          {ends && <span className={ends.soon ? "text-warn" : ""}>{ends.text}</span>}
        </span>
      </span>
      <strong title={p.filename} className="mt-[6px] overflow-hidden text-ellipsis whitespace-nowrap font-body text-[14px] font-semibold leading-[1.3]">{p.filename}</strong>
      <span className="muted text-[12.5px]">Added {shortDate(p.created_at)}</span>
    </Link>
  );
}

// A 9:16 thumbnail (hook text burned in) in a 16:9 frame: the whole picture in the middle, and the frame's sides
// filled by a blurred, darkened copy of the same image drawn in CSS (the frame's ::before), so nothing is cropped.
// Put `thumbVar(url)` in the frame's style and BACKDROP in its classes; the picture itself needs `relative`.
export const thumbVar = (src: string) => ({ "--thumb": `url("${src.replace(/"/g, "%22")}")` }) as React.CSSProperties;
export const BACKDROP = "before:pointer-events-none before:absolute before:inset-[-16px] before:content-[''] before:[background:var(--thumb)_center/cover_no-repeat] before:blur-[14px] before:brightness-[.45]";

// `row`: one line that scrolls sideways (Home's recent projects). Otherwise a grid (Library).
export const ProjectGrid = ({ projects, row }: { projects: any[]; row?: boolean }) => (
  <ul className={`grid list-none ${row
    ? "snap-x snap-mandatory auto-cols-[minmax(176px,calc((100%-56px)/5))] grid-flow-col gap-x-[14px] overflow-x-auto pb-[6px] narrow:auto-cols-[44%] narrow:gap-x-[10px]"
    : "grid-cols-[repeat(auto-fill,minmax(176px,1fr))] gap-x-[14px] gap-y-4 narrow:grid-cols-2 narrow:gap-x-[10px] narrow:gap-y-[14px]"}`}>
    {projects.map((p) => <li key={p.upload_id} className={row ? "snap-start" : ""}><ProjectCard p={p} /></li>)}
  </ul>
);
