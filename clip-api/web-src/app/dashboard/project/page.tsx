"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ClipCard } from "@/components/dash/ClipCard";
import { useDash } from "@/components/dash/Shell";
import { ToolPanel } from "@/components/dash/ToolPanel";
import { api, ApiError, clock } from "@/lib/api";

const TOOL_OF_JOB: Record<string, string> = { clips: "Clip Maker", render: "Reframe / Captions", find: "Video Finder" };
const STAGES: Record<string, string> = {
  starting: "Starting", downloading: "Getting your video", probing: "Reading the video", chat_motion: "Watching chat",
  audio: "Listening for reactions", transcribing: "Transcribing speech", indexing_frames: "Looking through the frames",
  searching: "Searching", rendering: "Rendering clips", writing_titles: "Writing titles", uploading: "Saving clips", done: "Done",
};
const active = (j: any) => j.status === "QUEUED" || j.status === "RUNNING";

// One project: the source video, the tools, what is running, and every clip made from it.
export default function Project() {
  const { fail, reloadMe } = useDash();
  const [id, setId] = useState<string | null>(null);
  const [project, setProject] = useState<any>(null), [gone, setGone] = useState(false);
  const [finds, setFinds] = useState<Record<string, any>>({});

  const load = useCallback(async (pid: string) => {
    try { setProject(await api(`/v1/projects/${pid}`)); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setGone(true); else fail(e); }
  }, [fail]);

  useEffect(() => {
    const pid = new URLSearchParams(window.location.search).get("id");
    setId(pid);
    if (pid) load(pid); else setGone(true);
  }, [load]);

  const anyActive = !!project?.jobs.some(active);
  useEffect(() => {
    if (!id || !anyActive) return;
    const t = setInterval(() => load(id), 3000);
    return () => { clearInterval(t); reloadMe(); };          // a job just ended: credits may have changed
  }, [id, anyActive, load, reloadMe]);

  // Video Finder results are not clips: fetch them for finished find jobs.
  useEffect(() => {
    for (const j of project?.jobs || [])
      if (j.tool === "find" && j.status === "SUCCEEDED" && !finds[j.job_id])
        api(`/v1/jobs/${j.job_id}`).then((d) => setFinds((x) => ({ ...x, [j.job_id]: d.result }))).catch(() => {});
  }, [project]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (gone) return <><h1 className="dash-title">Project not found</h1>
    <p className="muted">This video isn't here any more. Videos are kept for 7 days. <Link href="/dashboard/">Back to projects</Link></p></>;
  if (!project) return <p className="muted">Loading…</p>;

  const cancel = (jobId: string) => api(`/v1/jobs/${jobId}/cancel`, { body: {} }).then(() => load(project.upload_id)).catch(fail);
  const notes = project.jobs.filter((j: any) => active(j) || j.status === "FAILED" || finds[j.job_id]).slice(0, 6);

  return (
    <>
      <p className="crumb"><Link href="/dashboard/">Projects</Link> / {project.filename}</p>
      <h1 className="dash-title">{project.filename}</h1>
      <section className="source">
        <video controls preload="metadata" src={project.source_url} />
        <p className="muted">{clock(project.duration_sec)} · {project.width}×{project.height} · kept until {new Date(project.expires_at).toLocaleDateString()}.
          {" "}If the preview doesn't play, your browser can't show this file type; clips still work.</p>
      </section>
      <ToolPanel upload={project} onStarted={() => load(project.upload_id)} />
      {notes.length > 0 && <section aria-label="Jobs">
        {notes.map((j: any) => (
          <article key={j.job_id} className={`job ${j.status.toLowerCase()}`}>
            <div className="job-head">
              <strong>{TOOL_OF_JOB[j.tool] || j.tool}</strong>
              <span className="status">{active(j) ? `${STAGES[j.stage] || "Queued"} ${j.progress}%`
                : j.status === "FAILED" ? "Failed, credits refunded" : "Done"}</span>
            </div>
            {active(j) && <><progress max={100} value={j.progress} /><button className="link" onClick={() => cancel(j.job_id)}>Cancel</button></>}
            {j.status === "FAILED" && j.error && <p className="error">{j.error.message}</p>}
            {finds[j.job_id]?.matches && <div className="job-body">{finds[j.job_id].matches.length
              ? <ul className="matches">{finds[j.job_id].matches.map((m: any, i: number) => (
                  <li key={i}><b>{clock(m.start)}</b> {m.kind === "visual" ? "On screen" : "Said"}: {m.text}</li>))}</ul>
              : <p className="muted">No matches for “{finds[j.job_id].query}”. Try different words.</p>}</div>}
          </article>))}
      </section>}
      <section>
        <h2>Clips</h2>
        {!project.clips.length && <p className="muted">{anyActive ? "Your clips will show up here when they're ready." : "No clips yet. Pick a tool above to make some."}</p>}
        <div className="clips">
          {project.clips.map((c: any) => (
            <ClipCard key={c.id} clip={c}
              onChange={(n) => setProject((p: any) => ({ ...p, clips: p.clips.map((x: any) => (x.id === n.id ? n : x)) }))} />))}
        </div>
      </section>
    </>
  );
}
