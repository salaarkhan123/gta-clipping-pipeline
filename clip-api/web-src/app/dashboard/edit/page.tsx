"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { numbering } from "@/components/dash/ClipCard";
import { Editor } from "@/components/dash/Editor";
import { ThumbnailPanel } from "@/components/dash/PremiumThumbs";
import { useDash } from "@/components/dash/Shell";
import { api, ApiError } from "@/lib/api";
import { useClipOptions } from "@/lib/options";
import { useRoutes } from "@/lib/routes";

// The editor for one clip: /dashboard/edit/?project=<upload id>&clip=<clip id>.
export default function EditPage() {
  const { fail } = useDash();
  const [ids, setIds] = useState<{ project: string; clip: string } | null>(null);
  const [project, setProject] = useState<any>(null), [gone, setGone] = useState(false);
  const listed = useClipOptions(), known = useRoutes();

  useEffect(() => {
    const q = new URLSearchParams(window.location.search), pid = q.get("project"), cid = q.get("clip");
    if (!pid || !cid) { setGone(true); return; }
    setIds({ project: pid, clip: cid });
    api(`/v1/projects/${pid}`).then((p) => { setProject(p); if (!p.clips.some((c: any) => c.id === cid)) setGone(true); })
      .catch((e) => { if (e instanceof ApiError && e.status === 404) setGone(true); else fail(e); });
  }, [fail]);

  const numbers = useMemo(() => numbering(project?.clips || []), [project]);
  if (gone) return <><h1 className="dash-title">Clip not found</h1>
    <p className="muted">This clip isn&apos;t here any more. Videos and clips are kept for 7 days. <Link href="/dashboard/">Back to Home</Link></p></>;
  const clip = project?.clips.find((c: any) => c.id === ids?.clip);
  if (!project || !clip || !listed || !known) return <p className="muted">Loading the editor…</p>;
  const job = project.jobs.find((j: any) => j.job_id === clip.job_id);
  return (
    <div className="wide">
      <Editor project={project} clip={clip} job={job} listed={listed} known={known} number={numbers.get(clip.id)}
        onClip={(c) => setProject((p: any) => ({ ...p, clips: p.clips.map((x: any) => (x.id === c.id ? c : x)) }))} />
      <ThumbnailPanel clip={clip} />
    </div>
  );
}
