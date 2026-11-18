"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { numbering } from "@/components/dash/ClipCard";
import { FindPanel } from "@/components/dash/FindPanel";
import { Icon } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { BackTitle } from "@/components/dash/ui";
import { Timeline } from "@/components/dash/Timeline";
import { MakeView } from "@/components/dash/setup/MakeView";
import { isTool, Tool } from "@/components/dash/ToolPanel";
import { isActive } from "@/components/clips/model";
import { Results } from "@/components/clips/Results";
import { api, ApiError, clock } from "@/lib/api";

type View = "clips" | "find";
const TAB = "relative inline-flex min-h-[36px] cursor-pointer items-center gap-2 rounded-pill border-0 bg-transparent px-4 font-sans text-[14px] font-medium text-fg-2 hover:text-text "
  + "aria-selected:bg-chip-hover aria-selected:text-text";

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
    return o ? { ...c, video_url: o.video_url, preview_url: o.preview_url || c.preview_url, thumb_url: o.thumb_url || c.thumb_url, captions_url: o.captions_url || c.captions_url } : c;
  }) };
}

// One project (one uploaded video, GET /v1/projects/{upload_id}): the runs working on it and every clip made from it,
// the source video with where each clip came from, and the job-setup screen (MakeView) to make more.
export default function Project() {
  const { fail, reloadMe } = useDash();
  const router = useRouter();
  const [id, setId] = useState<string | null>(null);
  const [open, setOpen] = useState<{ tool?: Tool; template?: string }>({});   // handed over by Home or the template gallery
  const [project, setProject] = useState<any>(null), [gone, setGone] = useState(false);
  const [finds, setFinds] = useState<Record<string, any>>({});
  const [view, setView] = useState<View>("clips");
  const [jump, setJump] = useState<{ id: string; n: number } | null>(null);
  // null until the project loads: a project with nothing made yet opens on the setup screen.
  const [making, setMaking] = useState<boolean | null>(null);

  const load = useCallback(async (pid: string) => {
    try { const next = await api(`/v1/projects/${pid}`); setProject((old: any) => keepLinks(old, next)); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setGone(true); else fail(e); }
  }, [fail]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search), pid = q.get("id"), tool = q.get("tool");
    setId(pid);
    setOpen({ tool: isTool(tool) ? tool : undefined, template: q.get("template") || undefined });
    if (tool === "find") setView("find");
    if (pid) load(pid); else setGone(true);
  }, [load]);

  // Clips are stored one by one while a run works, so polling shows each as soon as it is finished.
  const anyActive = !!project?.jobs.some(isActive);
  useEffect(() => {
    if (!id || !anyActive) return;
    const t = setInterval(() => load(id), 3000);
    return () => { clearInterval(t); reloadMe(); };          // a run just ended: credits may have changed
  }, [id, anyActive, load, reloadMe]);

  // Video Finder results are not clips: fetch them for finished find jobs.
  useEffect(() => {
    for (const j of project?.jobs || [])
      if (j.tool === "find" && j.status === "SUCCEEDED" && !finds[j.job_id])
        api(`/v1/jobs/${j.job_id}`).then((d) => setFinds((x) => ({ ...x, [j.job_id]: d.result }))).catch(() => {});
  }, [project]);   // eslint-disable-line react-hooks/exhaustive-deps

  const loaded = !!project;
  useEffect(() => {
    if (!loaded) return;
    setMaking(open.tool ? open.tool !== "find" : !project.clips.length && !project.jobs.some(isActive));
  }, [loaded]);   // eslint-disable-line react-hooks/exhaustive-deps

  const clips: any[] = project?.clips || [];
  const numbers = useMemo(() => numbering(clips), [clips]);

  if (gone) return (
    <div className="mx-auto grid max-w-[520px] place-items-center gap-3 py-20 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-full bg-chip text-fg-2" aria-hidden="true"><Icon name="film" size={22} /></span>
      <h1 className="m-0 text-[22px] font-semibold">Project not found</h1>
      <p className="m-0 text-[14px] text-fg-2">This video isn't here any more. Videos and their clips are kept for 7 days.</p>
      <Link href="/dashboard/" className="btn small primary">Back to Home</Link>
    </div>
  );
  if (!project || making === null) return <p className="text-[14px] text-fg-2" role="status">Loading…</p>;
  const reload = () => load(project.upload_id);
  const started = () => { setMaking(false); setView("clips"); reload(); };
  const cancel = (jobId: string) => api(`/v1/jobs/${jobId}/cancel`, { body: {} }).then(reload).catch(fail);
  const findJobs = project.jobs.filter((j: any) => j.tool === "find" && (isActive(j) || j.status === "FAILED" || finds[j.job_id])).slice(0, 6);

  if (making) return (
    <div className="wide">
      <MakeView upload={project} tool={open.tool} template={open.template} onStarted={started}
        onBack={() => (clips.length > 0 || anyActive ? setMaking(false) : router.push("/dashboard/"))}
        back={(clips.length > 0 || anyActive) && <button type="button" className="btn small ghost" onClick={() => setMaking(false)}>
          {clips.length ? `Back to the clips (${clips.length})` : "Back to the results"}</button>} />
    </div>
  );

  const until = new Date(project.expires_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return (
    <div className="mx-auto grid w-full max-w-wide gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <BackTitle title={project.filename} />
          <p className="m-0 pl-[46px] text-[13px] tabular-nums text-fg-2">
            {clock(project.duration_sec)} · {clips.length} clip{clips.length === 1 ? "" : "s"} · kept until {until}</p>
        </div>
        <button type="button" className="btn small primary" onClick={() => setMaking(true)}><Icon name="plus" size={16} />Make more</button>
      </header>

      <details className="group rounded-16 border border-solid border-line-soft bg-card [&_summary::-webkit-details-marker]:hidden">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-[13.5px] font-medium text-soft hover:text-text">
          <Icon name="chevron" size={16} className="-rotate-90 transition-transform group-open:rotate-0" />Source video and where each clip came from</summary>
        <div className="grid gap-3 px-4 pb-4">
          <video controls preload="metadata" src={project.source_url} className="max-h-[420px] w-full rounded-12 bg-black"
            style={project.width && project.height ? { aspectRatio: `${project.width} / ${project.height}` } : undefined} />
          <Timeline duration={project.duration_sec} clips={clips} numbers={numbers} onPick={(c) => { setView("clips"); setJump({ id: c.id, n: Date.now() }); }} />
          <p className="m-0 text-[12.5px] text-fg-2">{clock(project.duration_sec)} · {project.width}×{project.height}. If the preview doesn't play, your browser can't show this file type; the clips still work.</p>
        </div>
      </details>

      <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Results">
        <button type="button" role="tab" className={TAB} aria-selected={view === "clips"} onClick={() => setView("clips")}>
          Clips {clips.length > 0 && <span className="font-mono text-[12px] tabular-nums text-fg-2">{clips.length}</span>}</button>
        <button type="button" role="tab" className={TAB} aria-selected={view === "find"} onClick={() => setView("find")}><Icon name="search" size={15} />Find moments</button>
      </div>
      <div role="tabpanel" aria-label={view === "clips" ? "Clips" : "Find moments"}>
        {view === "find"
          ? <FindPanel upload={project} jobs={findJobs} finds={finds} onStarted={reload} onCancel={cancel} />
          : <Results project={project} reload={reload} onMake={() => setMaking(true)} jump={jump}
              onChange={(update) => setProject((p: any) => ({ ...p, clips: update(p.clips) }))} />}
      </div>
    </div>
  );
}
