"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
import { Route } from "./routes";

// The body of POST /v1/clips/export (and its quote), shaped by what the route says it takes: the render options
// at the top or under `options`, the clips as `clips` (or `clip_ids`), the edit under `edit` only when it is
// listed. Nothing the route does not list is sent.
export function exportBody(r: Route, { jobId, clipIds, options, edit }: { jobId: string; clipIds: string[]; options: Record<string, unknown>; edit?: unknown }) {
  const body: Record<string, unknown> = {};
  if (r.fields.includes("job_id")) body.job_id = jobId;
  if (r.fields.includes("clips")) body.clips = clipIds;
  else if (r.fields.includes("clip_ids")) body.clip_ids = clipIds;
  if (r.fields.includes("options")) {
    const takes = r.nested.options || [];
    body.options = takes.length ? Object.fromEntries(Object.entries(options).filter(([k]) => takes.includes(k))) : options;
  } else for (const [k, v] of Object.entries(options)) if (r.fields.includes(k) && !(k in body)) body[k] = v;
  if (edit !== undefined && r.fields.includes("edit")) body.edit = edit;
  return body;
}

// A price from a quote route: exactly what the API says the action would reserve. Nothing is reserved by asking.
export type Quote = { state: "none" } | { state: "asking" } | { state: "ok"; credits: number; note?: string } | { state: "failed"; message: string };
export const askQuote = (path: string, body: unknown): Promise<Quote> =>
  api(path, { body }).then((r: any) => typeof r?.credits_reserved === "number"
    ? { state: "ok" as const, credits: r.credits_reserved, note: typeof r.note === "string" ? r.note : undefined }
    : { state: "failed" as const, message: "The price could not be worked out." })
    .catch((e) => ({ state: "failed" as const, message: e instanceof Error ? e.message : "The price could not be worked out." }));

// Asks again a moment after the body stops changing. `path` null: there is no quote route, so no price is shown.
export function useQuote(path: string | null, body: unknown, wait = 500): Quote {
  const [q, setQ] = useState<Quote>({ state: "none" });
  const text = JSON.stringify(body ?? null);
  useEffect(() => {
    if (!path || body == null) { setQ({ state: "none" }); return; }
    let on = true;
    setQ((old) => (old.state === "ok" ? old : { state: "asking" }));
    const t = setTimeout(() => askQuote(path, JSON.parse(text)).then((r) => on && setQ(r)), wait);
    return () => { on = false; clearTimeout(t); };
  }, [path, text, wait]);   // eslint-disable-line react-hooks/exhaustive-deps
  return q;
}
export const creditWords = (n: number) => `${n} credit${n === 1 ? "" : "s"}`;

// Follows a job until it ends. Resolves with the finished job; rejects when it failed or was cancelled.
export async function followJob(jobId: string, onStep: (job: any) => void, every = 2500): Promise<any> {
  for (;;) {
    const job = await api(`/v1/jobs/${jobId}`);
    onStep(job);
    if (job.status === "SUCCEEDED") return job;
    if (job.status === "FAILED" || job.status === "CANCELED" || job.status === "CANCELLED")
      throw new Error(job.error?.message || (job.status === "FAILED" ? "The render failed. Your credits were refunded." : "The render was cancelled."));
    await new Promise((r) => setTimeout(r, every));
  }
}
