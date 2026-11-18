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

// One stored video as a card: thumbnail (its best clip's frame) with the clip count, length and expiry on it;
// then its name and when it was added. Fields from GET /v1/projects.
export function ProjectCard({ p }: { p: any }) {
  const ends = expiry(p.expires_at);
  return (
    <Link href={`/dashboard/project/?id=${p.upload_id}`} className="project">
      <span className="project-thumb">
        {p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" /> : <Icon name="film" size={30} />}
        {p.active && <span className="project-status working">Working on it</span>}
        <span className="project-len">{clock(p.duration_sec)}</span>
        <span className="project-meta">
          <b>{p.clips ? `${p.clips} clip${p.clips === 1 ? "" : "s"}` : p.active ? "Making clips" : p.jobs ? "No clips" : "Not started"}</b>
          {ends && <span className={ends.soon ? "soon" : ""}>{ends.text}</span>}
        </span>
      </span>
      <strong title={p.filename}>{p.filename}</strong>
      <span className="muted">Added {shortDate(p.created_at)}</span>
    </Link>
  );
}

// `row`: one line that scrolls sideways (Home's recent projects). Otherwise a grid (Library).
export const ProjectGrid = ({ projects, row }: { projects: any[]; row?: boolean }) => (
  <ul className={`projects ${row ? "row-scroll" : ""}`}>{projects.map((p) => <li key={p.upload_id}><ProjectCard p={p} /></li>)}</ul>
);
