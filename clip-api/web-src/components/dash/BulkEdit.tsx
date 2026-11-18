"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { creditWords, exportBody, followJob, useQuote } from "@/lib/exporting";
import { layoutsFor, Listed, onlyListed } from "@/lib/options";
import { EXPORT, EXPORT_QUOTE, Routes } from "@/lib/routes";
import { hasPanels, Look } from "@/lib/templates";
import { lookOfJob } from "./Editor";
import { Icon } from "./Icon";
import { Custom } from "./PreEdit";
import { QuoteLine } from "./StartRow";

// Bulk edit: one look for every selected clip, rendered again in one request (POST /v1/clips/export), price first.
export function BulkEdit({ clips, jobs, listed, known, onClose, onDone }: { clips: any[]; jobs: any[]; listed: Listed; known: Routes;
  onClose: () => void; onDone: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const route = known.exportRoute!;
  const firstJob = jobs.find((j) => j.job_id === clips[0]?.job_id);
  const [look, setLook] = useState<Record<string, unknown>>(() => lookOfJob(listed, firstJob));
  const [state, setState] = useState<{ progress?: number; problem?: string; done?: boolean } | null>(null);
  const runs = [...new Set(clips.map((c) => c.job_id))];
  const oneRunOnly = route.fields.includes("job_id") && runs.length > 1;
  const body = oneRunOnly ? null : exportBody(route, { jobId: runs[0], clipIds: clips.map((c) => c.id), options: onlyListed(listed, look) });
  const quote = useQuote(known.exportQuote && body ? EXPORT_QUOTE : null, body);
  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal(); }, []);

  const onLook = (change: Partial<Look>) => setLook((x) => ({ ...x, ...change }));
  const l = look as unknown as Look;
  const setAspect = (aspect: string) => {
    const layout = layoutsFor(listed, aspect).includes(l.layout) ? l.layout : "auto";
    onLook({ aspect, layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });
  };
  async function run() {
    if (!body) return;
    setState({ progress: 0 });
    try {
      const r = await api(EXPORT, { body });
      const ids: string[] = r?.job_id ? [r.job_id] : (r?.jobs || []).map((j: any) => j.job_id).filter(Boolean);
      for (const id of ids) await followJob(id, (j) => setState({ progress: j.progress }));
      setState({ done: true });
      onDone();
    } catch (e) { setState({ problem: e instanceof Error ? e.message : "The export failed." }); onDone(); }
  }
  const working = !!state && !state.done && !state.problem;
  return (
    <dialog ref={dialog} className="picker wide" aria-labelledby="bulk-title" onClose={onClose}>
      <div className="picker-body">
        <div className="picker-head">
          <h2 id="bulk-title">Bulk edit {clips.length} clip{clips.length === 1 ? "" : "s"}</h2>
          <button className="icon-btn" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" /></button>
        </div>
        <p className="muted small">Every selected clip is rendered again with this look. Trims and cuts are made one clip at a time in its editor.</p>
        <Custom listed={listed} look={l} onLook={onLook} setAspect={setAspect} />
        <div className="bulk-foot">
        {oneRunOnly ? <p className="notice">These clips come from {runs.length} runs. Bulk edit takes clips from one run at a time: pick clips from one run.</p>
          : <p aria-live="polite">{known.exportQuote ? <QuoteLine quote={quote} what="This export" exact /> : "You only use credits for the minutes rendered."}</p>}
        {state?.problem && <p className="error" role="alert">{state.problem}</p>}
        {working && <progress max={100} value={state?.progress ?? 0} aria-label="Export progress" />}
        {state?.done && <p className="notice" role="status">Done. The new files are on the cards.</p>}
        <div className="editor-actions">
          <button type="button" className="btn small ghost" onClick={() => dialog.current?.close()}>{state?.done ? "Close" : "Cancel"}</button>
          <button type="button" className="btn small primary" disabled={!body || working || !!state?.done || (!!known.exportQuote && quote.state !== "ok")} onClick={run}>
            {working ? "Rendering…" : quote.state === "ok" ? `Export for ${creditWords(quote.credits)}` : "Export"}</button>
        </div>
        </div>
      </div>
    </dialog>
  );
}
