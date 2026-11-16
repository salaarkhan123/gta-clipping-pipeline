import Link from "next/link";
import { clock } from "@/lib/api";
import { Icon } from "./Icon";

// What a project is doing, from the fields GET /v1/projects returns (active, clips, jobs).
function status(p: any): [string, string] {
  if (p.active) return ["working", "Working on it"];
  if (p.clips > 0) return ["ready", "Clips ready"];
  return p.jobs > 0 ? ["idle", "No clips"] : ["idle", "Not started"];
}

// One stored video as a card: thumbnail (its best clip's frame), duration, name, clip count and status.
export function ProjectCard({ p }: { p: any }) {
  const [kind, label] = status(p);
  return (
    <Link href={`/dashboard/project/?id=${p.upload_id}`} className="project">
      <span className="project-thumb">
        {p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" /> : <Icon name="film" size={30} />}
        <span className={`project-status ${kind}`}>{label}</span>
        <span className="project-len">{clock(p.duration_sec)}</span>
      </span>
      <strong>{p.filename}</strong>
      <span className="muted">{p.clips} clip{p.clips === 1 ? "" : "s"} · added {new Date(p.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
    </Link>
  );
}

export const ProjectGrid = ({ projects }: { projects: any[] }) => (
  <ul className="projects">{projects.map((p) => <li key={p.upload_id}><ProjectCard p={p} /></li>)}</ul>
);
