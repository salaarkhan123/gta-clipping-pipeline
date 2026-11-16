"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { DropZone } from "@/components/DropZone";
import { useDash } from "@/components/dash/Shell";
import { api, ApiError, clock, takePendingFile, uploadFile } from "@/lib/api";

// Projects: every stored video, newest first. Uploading one opens its project.
export default function Projects() {
  const router = useRouter();
  const { fail } = useDash();
  const [projects, setProjects] = useState<any[] | null>(null);
  const [up, setUp] = useState<{ name: string; pct: number } | null>(null);
  const abort = useRef<(() => void) | null>(null);

  const load = useCallback(() => api("/v1/projects").then((r) => setProjects(r.projects)).catch(fail), [fail]);

  async function startUpload(file: File) {
    setUp({ name: file.name, pct: 0 });
    const { promise, abort: a } = uploadFile(file, (f) => setUp({ name: file.name, pct: Math.round(f * 100) }));
    abort.current = a;
    try { const u = await promise; router.push(`/dashboard/project/?id=${u.upload_id}`); }
    catch (e) { if (!(e instanceof ApiError && e.code === "aborted")) fail(e); setUp(null); }
    finally { abort.current = null; }
  }

  useEffect(() => { load(); const f = takePendingFile(); if (f) startUpload(f); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const anyActive = !!projects?.some((p) => p.active);
  useEffect(() => { if (!anyActive) return; const id = setInterval(load, 4000); return () => clearInterval(id); }, [anyActive, load]);

  return (
    <>
      <h1 className="dash-title">Projects</h1>
      <section className="panel">
        {up ? (
          <div className="uploading">
            <p>Uploading {up.name}</p>
            <progress max={100} value={up.pct} />
            <p className="muted">{up.pct}% <button className="link" onClick={() => abort.current?.()}>Cancel</button></p>
          </div>
        ) : <DropZone onFile={startUpload} compact={!!projects?.length} />}
      </section>
      {projects === null ? <p className="muted">Loading your projects…</p>
        : !projects.length ? <p className="muted">No projects yet. Upload a stream recording and its clips will show up here.</p>
        : <ul className="projects">
            {projects.map((p) => (
              <li key={p.upload_id}>
                <Link href={`/dashboard/project/?id=${p.upload_id}`} className="project">
                  <span className="project-thumb" aria-hidden="true">{p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" /> : <span>No clips yet</span>}</span>
                  <strong>{p.filename}</strong>
                  <span className="muted">{clock(p.duration_sec)} · {p.active ? "Working on it…" : `${p.clips} clip${p.clips === 1 ? "" : "s"}`}</span>
                </Link>
              </li>))}
          </ul>}
      {!!projects?.length && <p className="muted small">Videos and clips are kept for 7 days.</p>}
    </>
  );
}
