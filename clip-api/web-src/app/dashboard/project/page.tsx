"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BulkEdit } from "@/components/dash/BulkEdit";
import { CLIP_GRID, ClipCard, ClipFilter, ClipSort, ClipToolbar, numbering, useSteadyOrder } from "@/components/dash/ClipCard";
import { FindPanel } from "@/components/dash/FindPanel";
import { Icon, IconName, Soon } from "@/components/dash/Icon";
import { isActive, JobNote } from "@/components/dash/JobNote";
import { useDash } from "@/components/dash/Shell";
import { BackTitle, PAGE_HEAD, SECTION_HEAD, STRIP } from "@/components/dash/ui";
import { Timeline } from "@/components/dash/Timeline";
import { isTool, Tool, ToolPanel } from "@/components/dash/ToolPanel";
import { api, ApiError, clock } from "@/lib/api";
import { useClipOptions } from "@/lib/options";
import { useRoutes } from "@/lib/routes";

const TOOL_OF_JOB: Record<string, string> = { clips: "Clip Maker", render: "Reframe / Captions", find: "Video Finder" };
const BULK_SOON: [IconName, string][] = [["send", "Bulk schedule"], ["sparkle", "Create montage"]];
type View = "clips" | "find";
const TAB = "relative inline-flex min-h-[38px] cursor-pointer items-center gap-2 rounded-full border-0 bg-transparent px-4 py-2 font-body text-[14px] font-medium leading-[normal] text-muted hover:text-text "
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
    return o ? { ...c, video_url: o.video_url, thumb_url: o.thumb_url || c.thumb_url, captions_url: o.captions_url || c.captions_url } : c;
  }) };
}

// Starts the browser's own download of each file, one after another. The links answer as attachments, so
// nothing is rendered again and the page stays where it is.
async function downloadEach(urls: string[], onStep: (n: number) => void) {
  for (let i = 0; i < urls.length; i++) {
    onStep(i + 1);
    const a = document.createElement("a");
    a.href = urls[i]; a.download = ""; a.hidden = true;
    document.body.appendChild(a); a.click(); a.remove();
    if (i < urls.length - 1) await new Promise((r) => setTimeout(r, 1200));
  }
}

// One project: the source video and where its clips came from, the tools, what is running, and every clip made from it.
export default function Project() {
  const { fail, reloadMe, say } = useDash();
  const [id, setId] = useState<string | null>(null);
  const [open, setOpen] = useState<{ tool?: Tool; template?: string }>({});   // handed over by Home or the template gallery
  const [project, setProject] = useState<any>(null), [gone, setGone] = useState(false);
  const [finds, setFinds] = useState<Record<string, any>>({});
  const [view, setView] = useState<View>("clips");
  const [sort, setSort] = useState<ClipSort>("score"), [filter, setFilter] = useState<ClipFilter>("all");
  const [picked, setPicked] = useState<Set<string>>(new Set()), [exporting, setExporting] = useState(0);
  const [lit, setLit] = useState<{ id: string } | null>(null);                // the clip a timeline marker jumped to
  // Two views, like the tool's own flow: the settings form (one centred column), then the results grid.
  // null until the project loads: a project with nothing made yet opens on the form.
  const [making, setMaking] = useState<boolean | null>(null);
  const all = useRef<HTMLInputElement>(null);
  const known = useRoutes(), listed = useClipOptions(), [bulkEdit, setBulkEdit] = useState(false);

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

  const anyActive = !!project?.jobs.some(isActive);
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

  // Arriving with a tool chosen: bring it into view, once.
  const loaded = !!project;
  useEffect(() => {
    if (!loaded) return;
    setMaking(open.tool ? open.tool !== "find" : !project.clips.length && !project.jobs.some(isActive));
    if (open.tool === "find") document.getElementById("results")?.scrollIntoView({ block: "start" });
  }, [loaded]);   // eslint-disable-line react-hooks/exhaustive-deps
  // A timeline marker was picked: show its card (it is in the list by now), then let the highlight fade.
  useEffect(() => {
    if (!lit) return;
    const card = document.getElementById(`clip-${lit.id}`);
    card?.scrollIntoView({ block: "center" });
    card?.focus({ preventScroll: true });
    const t = setTimeout(() => setLit(null), 2600);
    return () => clearTimeout(t);
  }, [lit]);

  const clips: any[] = project?.clips || [];
  const numbers = useMemo(() => numbering(clips), [clips]);
  const shown = useSteadyOrder(clips, sort, filter, !anyActive);
  // The selection is kept by clip id, so it survives every refresh; a clip that is gone leaves it.
  const chosen = shown.filter((c) => picked.has(c.id));
  useEffect(() => { if (all.current) all.current.indeterminate = chosen.length > 0 && chosen.length < shown.length; });

  if (gone) return <><h1 className="dash-title">Project not found</h1>
    <p className="muted">This video isn't here any more. Videos are kept for 7 days. <Link href="/dashboard/">Back to Home</Link></p></>;
  if (!project || making === null) return <p className="muted">Loading…</p>;
  const title = <div className="grid min-w-0 gap-[2px]"><BackTitle title={project.filename} /><p className="muted m-0 pl-[46px] text-[13px] tabular-nums">{clock(project.duration_sec)} · {clips.length} clip{clips.length === 1 ? "" : "s"} · kept until {new Date(project.expires_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</p></div>;
  const started = () => { setMaking(false); setView("clips"); load(project.upload_id); };

  const cancel = (jobId: string) => api(`/v1/jobs/${jobId}/cancel`, { body: {} }).then(() => load(project.upload_id)).catch(fail);
  const notes = project.jobs.filter((j: any) => j.tool !== "find" && (isActive(j) || j.status === "FAILED")).slice(0, 6);
  const findJobs = project.jobs.filter((j: any) => j.tool === "find" && (isActive(j) || j.status === "FAILED" || finds[j.job_id])).slice(0, 6);
  function jump(clip: any) {
    setView("clips");
    if (!shown.some((c) => c.id === clip.id)) setFilter("all");      // the marker's clip is filtered out: show everything
    setLit({ id: clip.id });
  }
  const select = (clipId: string, on: boolean) => setPicked((old) => { const next = new Set(old); if (on) next.add(clipId); else next.delete(clipId); return next; });
  const selectAll = (on: boolean) => setPicked(on ? new Set(shown.map((c) => c.id)) : new Set());
  // Bulk export: the files that already exist, with links signed just now. Nothing is rendered and nothing is charged.
  async function exportChosen() {
    const ids = chosen.map((c) => c.id);
    setExporting(1);
    try {
      const fresh = await api(`/v1/projects/${project.upload_id}`);
      const links = new Map<string, string>(fresh.clips.map((c: any) => [c.id, c.video_url]));
      const urls = ids.map((x) => links.get(x)).filter((u): u is string => !!u);
      await downloadEach(urls, setExporting);
      say(`Started ${urls.length} download${urls.length === 1 ? "" : "s"}. If only the first one arrived, your browser is asking whether this site may download several files: allow it and export again.`);
    } catch (e) { fail(e); } finally { setExporting(0); }
  }

  if (making) return (
    <div className="form-col">
      <div className={PAGE_HEAD}>{title}
        {(clips.length > 0 || anyActive) && <button type="button" className="btn small ghost" onClick={() => setMaking(false)}>
          {clips.length ? `Back to the clips (${clips.length})` : "Back to the results"}</button>}</div>
      <ToolPanel upload={project} open={open} onStarted={started} />
    </div>
  );

  return (
    <div className="wide stack">
      <div className={PAGE_HEAD}>{title}
        <button type="button" className="btn small primary" onClick={() => setMaking(true)}><Icon name="plus" size={16} />Make more</button></div>
      <details className="source-peek">
        <summary>Source video and where each clip came from</summary>
        <section className="source">
          <video controls preload="metadata" src={project.source_url}
            style={project.width && project.height ? { aspectRatio: `${project.width} / ${project.height}` } : undefined} />
          <Timeline duration={project.duration_sec} clips={clips} numbers={numbers} onPick={jump} />
          <p className="muted">{clock(project.duration_sec)} · {project.width}×{project.height} · kept until {new Date(project.expires_at).toLocaleDateString()}.
            {" "}If the preview doesn't play, your browser can't show this file type; clips still work.</p>
        </section>
      </details>
      {notes.length > 0 && <section aria-label="Jobs">
        {notes.map((j: any) => <JobNote key={j.job_id} job={j} name={TOOL_OF_JOB[j.tool] || j.tool} onCancel={cancel} />)}
      </section>}
      <section id="results" aria-label="Results" className="stack-s">
        <div className={SECTION_HEAD}>
          <h2 className="m-0 text-[16px]">{view === "clips" ? "All clips" : "Find moments"}</h2>
          {view === "clips" && clips.length > 0 && <ClipToolbar sort={sort} filter={filter} sorts={["score", "time"]} onSort={setSort} onFilter={setFilter} />}
        </div>
        {view === "clips" && clips.length > 0 && <div className={`${STRIP} flex min-h-[52px] flex-wrap items-center justify-between gap-[10px] py-2 pl-[14px] pr-[10px] [&_.btn.small]:rounded-8 [&_.btn.small]:px-3 [&_.btn.small]:py-[7px]`}>
          <span className="select-left">
            <label className="check pick-all"><input ref={all} type="checkbox" checked={shown.length > 0 && chosen.length === shown.length} disabled={!shown.length}
              onChange={(e) => selectAll(e.target.checked)} />
              <span className="inline-flex items-center gap-2 text-[14px] text-lime" aria-live="polite">{chosen.length ? `${chosen.length} of ${shown.length} selected` : "Select all"}</span></label>
            {chosen.length > 0 && <button type="button" className="link small" onClick={() => selectAll(false)}>Clear selection</button>}
          </span>
          <div className="bulk min-h-0 narrow:w-full" role="group" aria-label="Actions for the selected clips">
            {known?.exportRoute && listed
              ? <button type="button" className="btn small ghost" disabled={!chosen.length} onClick={() => setBulkEdit(true)}><Icon name="pencil" size={16} />Bulk edit</button>
              : <button type="button" className="btn small ghost" disabled><Icon name="pencil" size={16} />Bulk edit <Soon /></button>}
            {BULK_SOON.map(([icon, label]) => <button key={label} type="button" className="btn small ghost" disabled title={`${label}: coming soon`}><Icon name={icon} size={16} />{label} <Soon /></button>)}
            <button type="button" className="btn small primary" disabled={!chosen.length || exporting > 0}
              title={chosen.length ? "Downloads the files as they are. Nothing is rendered again and no credits are used." : "Tick clips to export them together."}
              onClick={exportChosen}><Icon name="download" size={16} />{exporting ? `Downloading ${Math.min(exporting, chosen.length)} of ${chosen.length}…` : "Bulk export"}</button>
          </div>
        </div>}
        <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Results">
          <button type="button" role="tab" className={TAB} aria-selected={view === "clips"} aria-controls="results-panel" onClick={() => setView("clips")}>
            Clips {clips.length > 0 && <span className="tabular-nums text-muted">{shown.length}</span>}</button>
          <button type="button" role="tab" className={TAB} aria-selected={view === "find"} aria-controls="results-panel" onClick={() => setView("find")}><Icon name="plus" size={16} />Find moments</button>
        </div>
        <div id="results-panel" role="tabpanel" aria-label={view === "clips" ? "Clips" : "Find moments"} className="results">
          {view === "find" ? <FindPanel upload={project} jobs={findJobs} finds={finds} onStarted={() => load(project.upload_id)} onCancel={cancel} /> : <>
            {!clips.length && <p className="empty-note">{anyActive ? "Your clips will show up here as they're ready." : "No clips yet."}{" "}
              {!anyActive && <button type="button" className="link" onClick={() => setMaking(true)}>Make some</button>}</p>}
            {clips.length > 0 && !shown.length && <p className="muted">No clips match this filter.</p>}
            {anyActive && clips.length > 0 && <p className="muted small" role="status">More clips are on the way. New ones join at the end; the list is sorted again when the run finishes.</p>}
            <div className={CLIP_GRID}>
              {shown.map((c: any) => (
                <ClipCard key={c.id} clip={c} uploadId={project.upload_id} lit={lit?.id === c.id} number={numbers.get(c.id)} selected={picked.has(c.id)} onSelect={select}
                  onChange={(n) => setProject((p: any) => ({ ...p, clips: p.clips.map((x: any) => (x.id === n.id ? n : x)) }))} />))}
            </div>
          </>}
        </div>
      </section>
      {bulkEdit && known?.exportRoute && listed && <BulkEdit clips={chosen} jobs={project.jobs} listed={listed} known={known}
        onClose={() => setBulkEdit(false)} onDone={() => load(project.upload_id)} />}
    </div>
  );
}
