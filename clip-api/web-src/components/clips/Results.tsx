"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useClipOptions } from "@/lib/options";
import { useRoutes } from "@/lib/routes";
import { BulkEdit } from "@/components/dash/BulkEdit";
import { CLIP_LIST, LayoutToggle, nameOf, numbering, useClipLayout } from "@/components/dash/ClipCard";
import { Icon, IconName } from "@/components/dash/Icon";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useDash } from "@/components/dash/Shell";
import { ClipPlayer } from "./ClipPlayer";
import { ClipTile, Feedback, TileSkeleton } from "./ClipTile";
import { useGameOfTemplate, usePlanCap } from "./data";
import { JobStatus } from "./JobStatus";
import { arrange, isActive, kindsIn, Shape, shapeOf, steady, View } from "./model";
import { ResultsBar } from "./ResultsBar";

const GRID: Record<Shape, string> = {
  tall: "grid grid-cols-[repeat(auto-fill,minmax(236px,1fr))] gap-x-5 gap-y-8 narrow:grid-cols-2 narrow:gap-x-3 narrow:gap-y-6",
  square: "grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-x-5 gap-y-8 narrow:grid-cols-2 narrow:gap-x-3 narrow:gap-y-6",
  wide: "grid grid-cols-[repeat(auto-fill,minmax(380px,1fr))] gap-x-5 gap-y-8 narrow:grid-cols-1 narrow:gap-y-6",
};
const SHAPE_NAMES: Record<Shape, string> = { tall: "Vertical clips", square: "Square clips", wide: "Horizontal clips" };
const BULK_SOON: [IconName, string][] = [["send", "Bulk schedule"], ["sparkle", "Create montage"]];

// Starts the browser's own download of each file, one after another. The links answer as attachments.
async function downloadEach(urls: string[], onStep: (n: number) => void) {
  for (let i = 0; i < urls.length; i++) {
    onStep(i + 1);
    const a = document.createElement("a");
    a.href = urls[i]; a.download = ""; a.hidden = true;
    document.body.appendChild(a); a.click(); a.remove();
    if (i < urls.length - 1) await new Promise((r) => setTimeout(r, 1200));
  }
}

// The results of one video: its runs' progress, then every clip it has, appearing as each one is finished, sorted
// and filtered, in a grid of cards in the clips' own shape; a click opens the player. `project` is GET /v1/projects/{id}.
export function Results({ project, onChange, reload, onMake, jump }: {
  project: any; onChange: (update: (clips: any[]) => any[]) => void; reload: () => void; onMake: () => void; jump?: { id: string; n: number } | null;
}) {
  const { me, fail, say } = useDash();
  const known = useRoutes(), listed = useClipOptions(), games = useGameOfTemplate(), cap = usePlanCap(me?.plan);
  const [view, setView] = useState<View>({ sort: "rating", kind: null, mark: "all" });
  const [layout, setLayout] = useClipLayout();
  const [playing, setPlaying] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set()), [bulkEdit, setBulkEdit] = useState(false), [saving, setSaving] = useState(0);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const clips: any[] = project.clips || [];
  const jobs: any[] = project.jobs || [];
  const jobById = useMemo(() => new Map<string, any>(jobs.map((j) => [j.job_id, j])), [jobs]);
  const making = jobs.filter((j) => j.tool !== "find" && j.tool !== "transcript" && j.tool !== "summary");
  const running = making.filter(isActive);
  const settled = running.length === 0;
  const numbers = useMemo(() => numbering(clips), [clips]);
  const kinds = useMemo(() => kindsIn(clips), [clips]);

  const shapeFor = (c: any): Shape => { const j = jobById.get(c.job_id); return shapeOf(j?.options?.aspect, j?.options?.vertical) || "tall"; };
  const gameFor = (c: any): string | null => { const t = jobById.get(c.job_id)?.options?.template; return (t && games.get(t)) || null; };
  const nameFor = (c: any) => nameOf(c, numbers.get(c.id));

  // While clips are arriving, cards keep their places and new ones join at the end; the list is sorted again when
  // the run ends or the view changes.
  const last = useRef<{ key: string; ids: string[] } | null>(null);
  const key = JSON.stringify(view);
  const sorted = arrange(clips, view);
  const shown = steady(sorted, !settled && last.current?.key === key ? last.current.ids : null);
  useEffect(() => { last.current = { key, ids: shown.map((c) => c.id) }; });

  const groups = useMemo(() => {
    const g = new Map<Shape, any[]>();
    for (const c of shown) { const s = shapeFor(c); g.set(s, [...(g.get(s) || []), c]); }
    return [...g];
  }, [shown, jobById]);   // eslint-disable-line react-hooks/exhaustive-deps
  const order = groups.flatMap(([, cs]) => cs);
  const at = playing ? order.findIndex((c) => c.id === playing) : -1;
  useEffect(() => { if (playing && at < 0) setPlaying(null); }, [playing, at]);
  // A timeline marker was picked: show its card (the filters are cleared when it is filtered out).
  useEffect(() => {
    if (!jump) return;
    if (!shown.some((c) => c.id === jump.id)) setView((v) => ({ ...v, kind: null, mark: "all" }));
    setTimeout(() => { const el = document.getElementById(`clip-${jump.id}`); el?.scrollIntoView({ block: "center" }); el?.focus({ preventScroll: true }); }, 50);
  }, [jump]);   // eslint-disable-line react-hooks/exhaustive-deps

  const put = (n: any) => onChange((cs) => cs.map((c) => (c.id === n.id ? { ...c, ...n } : c)));
  function feedback(c: any, f: Feedback) {
    put({ ...c, ...f });
    api(`/v1/clips/${c.id}/feedback`, { body: f }).then((r) => put(r)).catch((e) => { put({ id: c.id, kept: c.kept, reaction: c.reaction, bookmarked: c.bookmarked }); fail(e); });
  }
  const cancel = (id: string) => api(`/v1/jobs/${id}/cancel`, { body: {} }).then(() => reload()).catch((e) => { fail(e); throw e; });

  const chosen = shown.filter((c) => picked.has(c.id));
  const select = (id: string, on: boolean) => setPicked((o) => { const n = new Set(o); if (on) n.add(id); else n.delete(id); return n; });
  async function exportChosen() {
    setSaving(1);
    try {
      const fresh = await api(`/v1/projects/${project.upload_id}`);
      const links = new Map<string, string>(fresh.clips.map((c: any) => [c.id, c.video_url]));
      const urls = chosen.map((c) => links.get(c.id)).filter((u): u is string => !!u);
      await downloadEach(urls, setSaving);
      say(`Started ${urls.length} download${urls.length === 1 ? "" : "s"}. If only the first one arrived, allow this site to download several files and try again.`);
    } catch (e) { fail(e); } finally { setSaving(0); }
  }

  // Failed and cancelled runs since the last one that worked (jobs come newest first).
  const lastGood = making.findIndex((j) => j.status === "SUCCEEDED");
  const problems = (lastGood < 0 ? making : making.slice(0, lastGood)).filter((j) => (j.status === "FAILED" || j.status === "LOST" || j.status === "CANCELED" || j.status === "CANCELLED") && !dismissed.has(j.job_id)).slice(0, 3);
  const runShape: Shape = shapeOf(running[0]?.options?.aspect, running[0]?.options?.vertical) || "tall";
  const madeBy = (j: any) => clips.filter((c) => c.job_id === j.job_id).length;
  const sourceSide = project.width && project.height ? Math.min(project.width, project.height) : null;

  return (
    <section id="results" aria-label="Results" className="grid grid-cols-1 gap-5">
      {(running.length > 0 || problems.length > 0) && <div className="grid gap-3">
        {running.map((j) => <JobStatus key={j.job_id} job={j} made={madeBy(j)} onCancel={cancel} />)}
        {problems.map((j) => <JobStatus key={j.job_id} job={j} made={madeBy(j)} onCancel={cancel} onDismiss={() => setDismissed((d) => new Set(d).add(j.job_id))} />)}
      </div>}

      {clips.length > 0 && <ResultsBar view={view} onView={setView} kinds={kinds} total={clips.length}>
        <LayoutToggle value={layout} onChange={setLayout} />
      </ResultsBar>}

      {clips.length > 0 && <div className="flex min-h-[52px] flex-wrap items-center justify-between gap-[10px] rounded-[14px] bg-card py-2 pl-4 pr-2">
        <label className="m-0 flex cursor-pointer items-center gap-[10px] text-[14px] font-normal text-text">
          <input type="checkbox" className="h-4 w-4 accent-lime" checked={shown.length > 0 && chosen.length === shown.length}
            ref={(el) => { if (el) el.indeterminate = chosen.length > 0 && chosen.length < shown.length; }}
            onChange={(e) => setPicked(e.target.checked ? new Set(shown.map((c) => c.id)) : new Set())} />
          <span aria-live="polite">{chosen.length ? `${chosen.length} of ${shown.length} selected` : `Select all ${shown.length}`}</span>
        </label>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Actions for the selected clips">
          {BULK_SOON.map(([icon, label]) => <span key={label} aria-disabled="true" className="inline-flex cursor-default items-center gap-[6px] px-2 text-[13px] text-fg-3 narrow:hidden"><Icon name={icon} size={15} />{label}<ComingSoonBadge short /></span>)}
          {known?.exportRoute && listed && <button type="button" className="btn small ghost" disabled={!chosen.length} onClick={() => setBulkEdit(true)}><Icon name="pencil" size={15} />Bulk edit</button>}
          <button type="button" className="btn small primary" disabled={!chosen.length || saving > 0} onClick={exportChosen}
            title="Downloads the files as they are. Nothing is rendered again and no credits are used.">
            <Icon name="download" size={15} />{saving ? `Downloading ${Math.min(saving, chosen.length)} of ${chosen.length}…` : "Download"}</button>
        </div>
      </div>}

      {!clips.length && (running.length > 0 ? (
        <div className={layout === "list" ? CLIP_LIST : GRID[runShape]}>{[0, 1, 2, 3].map((i) => <TileSkeleton key={i} shape={runShape} layout={layout} />)}</div>
      ) : (
        <EmptyState title={problems.length ? "No clips from this run" : "No clips yet"}
          action={<button type="button" className="btn small primary" onClick={onMake}><Icon name="sparkle" size={15} />{problems.length ? "Try again" : "Make clips"}</button>}>
          {problems.length ? "Try again with other settings, or pick a different part of the video." : "Find the best moments in this video. You see the exact price before anything is charged."}</EmptyState>
      ))}
      {clips.length > 0 && !shown.length && <div className="grid place-items-center gap-2 rounded-24 border border-dashed border-line-strong px-6 py-12 text-center">
        <p className="m-0 text-[14px] text-fg-2">No clips match these filters.</p>
        <button type="button" className="btn small ghost" onClick={() => setView({ ...view, kind: null, mark: "all" })}>Clear filters</button>
      </div>}

      {groups.map(([shape, cs], gi) => (
        <div key={shape} className="grid gap-3">
          {groups.length > 1 && <h3 className="m-0 text-[13px] font-medium text-fg-2">{SHAPE_NAMES[shape]} <span className="font-mono tabular-nums">{cs.length}</span></h3>}
          <div className={layout === "list" ? CLIP_LIST : GRID[shape]}>
            {cs.map((c) => <ClipTile key={c.id} clip={c} name={nameFor(c)} shape={shape} game={gameFor(c)} selected={picked.has(c.id)}
              layout={layout} onSelect={select} onOpen={() => setPlaying(c.id)} onFeedback={(f) => feedback(c, f)}
              editHref={`/dashboard/edit/?project=${encodeURIComponent(project.upload_id)}&clip=${encodeURIComponent(c.id)}`} />)}
            {gi === groups.length - 1 && running.length > 0 && [0, 1].map((i) => <TileSkeleton key={`s${i}`} shape={shape} layout={layout} />)}
          </div>
        </div>
      ))}
      {running.length > 0 && clips.length > 0 && <p className="m-0 text-[12.5px] text-fg-3" role="status">New clips join at the end as they are finished. The list is sorted again when the run ends.</p>}

      {at >= 0 && <ClipPlayer clips={order} at={at} onAt={(i) => setPlaying(order[i]?.id ?? null)} onClose={() => setPlaying(null)}
        nameOf={nameFor} shapeOf={shapeFor} gameOf={gameFor} jobOf={(c) => jobById.get(c.job_id)} uploadId={project.upload_id}
        sourceSide={sourceSide} cap={cap} resolutions={(listed?.resolution?.values as string[]) || []} known={known}
        onFeedback={feedback} onRenamed={put} onReload={reload} />}
      {bulkEdit && known?.exportRoute && listed && <BulkEdit clips={chosen} jobs={jobs} listed={listed} known={known}
        onClose={() => setBulkEdit(false)} onDone={reload} />}
    </section>
  );
}
