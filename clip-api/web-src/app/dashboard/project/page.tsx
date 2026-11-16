"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { arrange, ClipCard, ClipFilter, ClipSort, ClipToolbar } from "@/components/dash/ClipCard";
import { useDash } from "@/components/dash/Shell";
import { Timeline } from "@/components/dash/Timeline";
import { isTool, Tool, ToolPanel } from "@/components/dash/ToolPanel";
import { api, ApiError, clock } from "@/lib/api";

const TOOL_OF_JOB: Record<string, string> = { clips: "Clip Maker", render: "Reframe / Captions", find: "Video Finder" };
const STAGES: Record<string, string> = {
  starting: "Starting", downloading: "Getting your video", probing: "Reading the video", chat_motion: "Watching chat",
  audio: "Listening for reactions", transcribing: "Transcribing speech", indexing_frames: "Looking through the frames",
  searching: "Searching", rendering: "Rendering clips", writing_titles: "Writing titles", uploading: "Saving clips", done: "Done",
};
const active = (j: any) => j.status === "QUEUED" || j.status === "RUNNING";

// Every read signs new links for the same files. A refresh keeps the links already on the page, so polling a
// running job does not restart the source video or a clip that is playing. Links are valid for an hour, so
// after half an hour the new ones are taken.
const LINK_LIFE_MS = 30 * 60 * 1000;
function keepLinks(old: any, next: any) {
  const now = Date.now();
  if (!old || old.upload_id !== next.upload_id || now - old.linksAt > LINK_LIFE_MS) return { ...next, linksAt: now };
  const had = new Map<string, any>(old.clips.map((c: any) => [c.id, c]));
  return { ...next, linksAt: old.linksAt, source_url: old.source_url, clips: next.clips.map((c: any) => {
    const o = had.get(c.id);
    return o ? { ...c, video_url: o.video_url, thumb_url: o.thumb_url || c.thumb_url, captions_url: o.captions_url || c.captions_url } : c;
  }) };
}

// One project: the source video and where its clips came from, the tools, what is running, and every clip made from it.
export default function Project() {
  const { fail, reloadMe } = useDash();
  const [id, setId] = useState<string | null>(null);
  const [open, setOpen] = useState<{ tool?: Tool; template?: string }>({});   // handed over by Home or the template gallery
  const [project, setProject] = useState<any>(null), [gone, setGone] = useState(false);
  const [finds, setFinds] = useState<Record<string, any>>({});
  const [sort, setSort] = useState<ClipSort>("score"), [filter, setFilter] = useState<ClipFilter>("all");
  const [lit, setLit] = useState<{ id: string } | null>(null);                // the clip a timeline marker jumped to

  const load = useCallback(async (pid: string) => {
    try { const next = await api(`/v1/projects/${pid}`); setProject((old: any) => keepLinks(old, next)); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setGone(true); else fail(e); }
  }, [fail]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search), pid = q.get("id"), tool = q.get("tool");
    setId(pid);
    setOpen({ tool: isTool(tool) ? tool : undefined, template: q.get("template") || undefined });
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

  // Arriving with a tool chosen: bring the tool panel into view, once.
  const loaded = !!project;
  useEffect(() => { if (loaded && open.tool) document.getElementById("tools")?.scrollIntoView({ block: "start" }); }, [loaded]);   // eslint-disable-line react-hooks/exhaustive-deps
  // A timeline marker was picked: show its card (it is in the list by now), then let the highlight fade.
  useEffect(() => {
    if (!lit) return;
    const card = document.getElementById(`clip-${lit.id}`);
    card?.scrollIntoView({ block: "center" });
    card?.focus({ preventScroll: true });
    const t = setTimeout(() => setLit(null), 2600);
    return () => clearTimeout(t);
  }, [lit]);

  if (gone) return <><h1 className="dash-title">Project not found</h1>
    <p className="muted">This video isn't here any more. Videos are kept for 7 days. <Link href="/dashboard/">Back to Home</Link></p></>;
  if (!project) return <p className="muted">Loading…</p>;

  const cancel = (jobId: string) => api(`/v1/jobs/${jobId}/cancel`, { body: {} }).then(() => load(project.upload_id)).catch(fail);
  const shown = arrange(project.clips, sort, filter);
  const notes = project.jobs.filter((j: any) => active(j) || j.status === "FAILED" || finds[j.job_id]).slice(0, 6);
  function jump(clip: any) {
    if (!shown.some((c) => c.id === clip.id)) setFilter("all");      // the marker's clip is filtered out: show everything
    setLit({ id: clip.id });
  }

  return (
    <>
      <p className="crumb"><Link href="/dashboard/">Home</Link> / {project.filename}</p>
      <h1 className="dash-title">{project.filename}</h1>
      <section className="source">
        <video controls preload="metadata" src={project.source_url}
          style={project.width && project.height ? { aspectRatio: `${project.width} / ${project.height}` } : undefined} />
        <Timeline duration={project.duration_sec} clips={project.clips} onPick={jump} />
        <p className="muted">{clock(project.duration_sec)} · {project.width}×{project.height} · kept until {new Date(project.expires_at).toLocaleDateString()}.
          {" "}If the preview doesn't play, your browser can't show this file type; clips still work.</p>
      </section>
      <ToolPanel upload={project} open={open} onStarted={() => load(project.upload_id)} />
      {notes.length > 0 && <section aria-label="Jobs">
        {notes.map((j: any) => (
          <article key={j.job_id} className={`job ${j.status.toLowerCase()}`}>
            <div className="job-head">
              <strong>{TOOL_OF_JOB[j.tool] || j.tool}</strong>
              <span className="status">{active(j) ? `${STAGES[j.stage] || "Queued"} ${j.progress}%`
                : j.status === "FAILED" ? "Failed, credits refunded" : "Done"}</span>
            </div>
            {active(j) && <><progress max={100} value={j.progress} aria-label={`${TOOL_OF_JOB[j.tool] || j.tool} progress`} />
              <button className="link" onClick={() => cancel(j.job_id)}>Cancel</button></>}
            {j.status === "FAILED" && j.error && <p className="error">{j.error.message}</p>}
            {finds[j.job_id]?.matches && <div className="job-body">{finds[j.job_id].matches.length
              ? <ul className="matches">{finds[j.job_id].matches.map((m: any, i: number) => (
                  <li key={i}><b>{clock(m.start)}</b> {m.kind === "visual" ? "On screen" : "Said"}: {m.text}</li>))}</ul>
              : <p className="muted">No matches for “{finds[j.job_id].query}”. Try different words.</p>}</div>}
          </article>))}
      </section>}
      <section>
        <div className="clips-head">
          <h2>Clips</h2>
          {project.clips.length > 0 && <ClipToolbar sort={sort} filter={filter} sorts={["score", "time"]} onSort={setSort} onFilter={setFilter} />}
        </div>
        {!project.clips.length && <p className="muted">{anyActive ? "Your clips will show up here when they're ready." : "No clips yet. Pick a tool above to make some."}</p>}
        {project.clips.length > 0 && !shown.length && <p className="muted">No clips match this filter.</p>}
        <div className="clips">
          {shown.map((c: any) => (
            <ClipCard key={c.id} clip={c} lit={lit?.id === c.id}
              onChange={(n) => setProject((p: any) => ({ ...p, clips: p.clips.map((x: any) => (x.id === n.id ? n : x)) }))} />))}
        </div>
      </section>
    </>
  );
}
