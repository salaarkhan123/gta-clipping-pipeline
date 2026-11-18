"use client";
import { useState } from "react";
import { creditWords } from "@/lib/exporting";
import { Icon } from "@/components/dash/Icon";
import { isActive, outcomeOf, stageName } from "./model";

const TOOL_NAMES: Record<string, string> = { clips: "Finding your best moments", render: "Reframe and captions", export: "Exporting" };

// One run of this video: while it works, its stage, progress, the clips it has made so far and a way to stop it;
// once it fails or is cancelled, why, and the credits that went back. Every number is the API's (job_json).
export function JobStatus({ job, made, onCancel, onDismiss }: { job: any; made: number; onCancel: (id: string) => Promise<void>; onDismiss?: () => void }) {
  const [asking, setAsking] = useState(false), [stopping, setStopping] = useState(false);
  const o = outcomeOf(job);
  const name = TOOL_NAMES[job.tool] || "Working on your video";

  if (o.kind === "failed" || o.kind === "cancelled") return (
    <div role="status" className={`flex flex-wrap items-start gap-3 rounded-16 border border-solid p-4 ${o.kind === "failed" ? "border-[rgba(255,92,122,.3)] bg-[rgba(255,92,122,.06)]" : "border-line bg-card"}`}>
      <span className={`mt-[2px] grid h-7 w-7 flex-none place-items-center rounded-full ${o.kind === "failed" ? "bg-[rgba(255,92,122,.16)] text-danger" : "bg-chip text-muted"}`} aria-hidden="true">
        <Icon name={o.kind === "failed" ? "info" : "close"} size={15} /></span>
      <div className="grid min-w-0 flex-1 gap-1">
        <strong className="text-[14px] font-semibold">{o.kind === "failed" ? `${name}: this run failed` : `${name}: cancelled`}</strong>
        {o.kind === "failed" && o.message && <p className="m-0 text-[13px] text-soft">{o.message}</p>}
        <p className="m-0 text-[13px] text-fg-2">
          {o.refunded !== null ? (o.refunded > 0 ? `${creditWords(o.refunded)} refunded to your balance.` : "Nothing was charged.") : "Any credits it held go back to your balance."}
          {made > 0 && ` The ${made} clip${made === 1 ? "" : "s"} it finished ${made === 1 ? "is" : "are"} below.`}
        </p>
      </div>
      {onDismiss && <button type="button" className="btn small ghost" onClick={onDismiss}>Dismiss</button>}
    </div>
  );
  if (o.kind !== "running") return null;

  const pct = Math.max(0, Math.min(100, Math.round(job.progress ?? 0)));
  return (
    <div className="grid gap-3 rounded-16 border border-solid border-line bg-card p-4" aria-label={name}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="relative grid h-8 w-8 flex-none place-items-center" aria-hidden="true">
            <span className="absolute inset-0 animate-spin rounded-full border-2 border-solid border-[rgba(255,255,255,.12)] border-t-lime" />
            <Icon name="sparkle" size={14} className="text-lime" />
          </span>
          <div className="grid min-w-0">
            <strong className="text-[14px] font-semibold">{name}</strong>
            <span className="text-[13px] text-fg-2" aria-live="polite">
              {stopping ? "Stopping after the current step…" : stageName(job)}
              {made > 0 && ` · ${made} clip${made === 1 ? "" : "s"} ready so far`}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[13px] tabular-nums text-soft">{pct}%</span>
          {!asking && !stopping && isActive(job) && <button type="button" className="btn small ghost" onClick={() => setAsking(true)}>Cancel</button>}
          {asking && <span className="flex flex-wrap items-center gap-2" role="group" aria-label="Cancel this run?">
            <span className="text-[13px] text-soft">Stop this run? Its credits are refunded.</span>
            <button type="button" className="btn small ghost danger" onClick={() => { setAsking(false); setStopping(true); onCancel(job.job_id).catch(() => setStopping(false)); }}>Stop</button>
            <button type="button" className="btn small ghost" onClick={() => setAsking(false)}>Keep going</button>
          </span>}
        </div>
      </div>
      <div className="h-[6px] overflow-hidden rounded-pill bg-[rgba(255,255,255,.08)]" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={`${name} progress`}>
        <span className="block h-full rounded-pill bg-lime transition-[width] duration-700 ease-out" style={{ width: `${Math.max(2, pct)}%` }} />
      </div>
      {typeof job.credits_reserved === "number" && <p className="m-0 text-[12px] text-fg-3">{creditWords(job.credits_reserved)} reserved for this run. A failed or cancelled run is refunded.</p>}
    </div>
  );
}
