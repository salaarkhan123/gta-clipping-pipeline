"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { askQuote, creditWords, followJob, Quote } from "@/lib/exporting";
import { EXPORT, EXPORT_QUOTE } from "@/lib/routes";
import { useDash } from "./Shell";

// A clip that is only a preview (or has no video yet): Export asks the exact price, then renders it in full
// quality with the look its run was made with. `onDone` gets the clip as the API has it afterwards.
export function ExportFull({ clip, onDone }: { clip: any; onDone: (c: any) => void }) {
  const { fail, reloadMe } = useDash();
  const [quote, setQuote] = useState<Quote>({ state: "none" }), [progress, setProgress] = useState<number | null>(null);
  const body = { job_id: clip.job_id, clips: [clip.id] };
  async function ask() { setQuote({ state: "asking" }); setQuote(await askQuote(EXPORT_QUOTE, body)); }
  async function run() {
    setQuote({ state: "none" }); setProgress(0);
    try {
      const r = await api(EXPORT, { body });
      if (r?.job_id) await followJob(r.job_id, (j) => setProgress(j.progress ?? 0));
      const job = await api(`/v1/jobs/${clip.job_id}`);
      const next = job.clips?.find((c: any) => c.id === clip.id);
      if (next) onDone(next);
    } catch (e) { fail(e); } finally { setProgress(null); reloadMe(); }
  }
  if (progress !== null) return <progress max={100} value={progress} aria-label="Full-quality export progress" />;
  if (quote.state === "ok") return (
    <span className="clip-actions" role="group" aria-label="Export in full quality">
      <span className="muted small">{quote.credits === 0 ? "Already rendered: free." : `Full quality costs ${creditWords(quote.credits)}.`}</span>
      <button type="button" className="btn small primary" onClick={run}>{quote.credits === 0 ? "Get it" : `Export for ${creditWords(quote.credits)}`}</button>
      <button type="button" className="btn small ghost" onClick={() => setQuote({ state: "none" })}>Cancel</button>
    </span>);
  return (
    <>
      <button type="button" className="btn small primary" disabled={quote.state === "asking"} onClick={ask}
        title="This is a quick preview. Export renders it in full quality; the price is shown before anything is charged.">
        {quote.state === "asking" ? "Pricing…" : "Export"}</button>
      {quote.state === "failed" && <span className="warn small">{quote.message}</span>}
    </>
  );
}
