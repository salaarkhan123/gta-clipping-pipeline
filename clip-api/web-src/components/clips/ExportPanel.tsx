"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { creditWords, exportBody, followJob } from "@/lib/exporting";
import { EXPORT, EXPORT_QUOTE, Routes } from "@/lib/routes";
import { useDash } from "@/components/dash/Shell";
import { resolutionChoices, resolutionName, SIDE } from "./model";

type Reply = { credits: number; note: string | null; free: boolean; existing: string | null };
type Ask = { state: "asking" } | { state: "ok"; r: Reply } | { state: "failed"; message: string };

// Export one clip at a chosen resolution. The price is the server's quote for exactly this body
// (POST /v1/clips/export/quote), shown before anything is charged; a clip already rendered with these settings comes
// back free (`existing`). Resolutions are the ones GET /v1/options lists; those above the plan's cap are shown but
// cannot be picked.
export function ExportPanel({ clip, job, sourceSide, cap, resolutions, known, onDone }: {
  clip: any; job: any | undefined; sourceSide: number | null; cap: number | null; resolutions: string[]; known: Routes; onDone: () => void;
}) {
  const { me, fail, reloadMe } = useDash();
  const choices = useMemo(() => resolutionChoices(resolutions, cap, sourceSide), [resolutions, cap, sourceSide]);
  const first = () => {
    const own = job?.options?.resolution;
    const ok = choices.filter((c) => c.allowed);
    return (ok.find((c) => c.value === own) || ok.find((c) => c.value === "1080") || ok[ok.length - 1])?.value || null;
  };
  const [res, setRes] = useState<string | null>(first);
  useEffect(() => { if (res === null || !choices.some((c) => c.value === res && c.allowed)) setRes(first()); }, [choices]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [ask, setAsk] = useState<Ask>({ state: "asking" });
  const [progress, setProgress] = useState<number | null>(null), [ready, setReady] = useState<string | null>(null);

  const body = (r: typeof known.exportRoute) => r && res ? exportBody(r, { jobId: clip.job_id, clipIds: [clip.id], options: { resolution: res } }) : null;
  const quoteBody = JSON.stringify(body(known.exportQuote));
  useEffect(() => {
    const b = JSON.parse(quoteBody);
    if (!b) return;
    let on = true;
    setAsk({ state: "asking" }); setReady(null);
    const t = setTimeout(() => api(EXPORT_QUOTE, { body: b }).then((q: any) => {
      if (!on) return;
      if (typeof q?.credits_reserved !== "number") return setAsk({ state: "failed", message: "The price could not be worked out." });
      const mine = (q.existing || []).find((e: any) => e.clip_id === clip.id);
      setAsk({ state: "ok", r: { credits: q.credits_reserved, note: typeof q.note === "string" ? q.note : null,
        free: q.credits_reserved === 0, existing: mine?.video_url || null } });
    }).catch((e) => on && setAsk({ state: "failed", message: e instanceof Error ? e.message : "The price could not be worked out." })), 250);
    return () => { on = false; clearTimeout(t); };
  }, [quoteBody, clip.id]);

  async function run() {
    const b = body(known.exportRoute);
    if (!b) return;
    setProgress(0);
    try {
      const r = await api(EXPORT, { body: b });
      const now = (r?.existing || []).find((e: any) => e.clip_id === clip.id)?.video_url;
      if (r?.job_id) await followJob(r.job_id, (j) => setProgress(j.progress ?? 0));
      const fresh = await api(`/v1/jobs/${clip.job_id}`);
      const c = fresh.clips?.find((x: any) => x.id === clip.id);
      setReady(now || c?.export_url || c?.video_url || null);
      onDone();
    } catch (e) { fail(e); } finally { setProgress(null); reloadMe(); }
  }

  if (!choices.length) return null;
  const short = ask.state === "ok" && typeof me?.credits === "number" && me.credits < ask.r.credits;
  return (
    <section aria-label="Export" className="grid gap-3 rounded-16 border border-solid border-line bg-[rgba(255,255,255,.02)] p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="m-0 text-[14px] font-semibold">Export</h3>
        {clip.export_res && <span className="text-[12px] text-fg-2">Last export: {resolutionName(String(clip.export_res))}</span>}
      </div>
      <div role="radiogroup" aria-label="Resolution" className="flex flex-wrap gap-[6px]">
        {choices.map((c) => (
          <button key={c.value} type="button" role="radio" aria-checked={res === c.value} disabled={!c.allowed || progress !== null}
            title={!c.allowed ? "Your plan exports up to " + (cap ? `${cap}p` : "a lower resolution") : c.overSource ? "Above your video's own resolution: it comes out at the source's size" : undefined}
            onClick={() => setRes(c.value)}
            className={`min-h-[34px] cursor-pointer rounded-pill border border-solid px-3 font-sans text-[12.5px] font-medium disabled:cursor-not-allowed
              ${res === c.value ? "border-btn bg-btn text-btn-ink" : "border-line-strong bg-transparent text-text enabled:hover:bg-[rgba(255,255,255,.06)]"} ${!c.allowed ? "opacity-40" : ""}`}>
            {resolutionName(c.value)}
          </button>))}
      </div>
      {choices.some((c) => !c.allowed) && <p className="m-0 text-[12px] text-fg-2">Higher resolutions come with a bigger plan. <Link href="/dashboard/pricing/" className="text-text underline">See plans</Link></p>}
      {res && sourceSide !== null && SIDE[res] > sourceSide && <p className="m-0 text-[12px] text-fg-2">Your video is {sourceSide}p, so this export comes out at {sourceSide}p.</p>}

      {progress !== null ? (
        <div className="grid gap-2" role="status">
          <span className="text-[13px] text-soft">Rendering… {Math.round(progress)}%</span>
          <div className="h-[5px] overflow-hidden rounded-pill bg-[rgba(255,255,255,.08)]"><span className="block h-full bg-lime transition-[width] duration-500" style={{ width: `${Math.max(3, progress)}%` }} /></div>
        </div>
      ) : ready ? (
        <a className="btn small primary justify-self-start" href={ready} download>Download the export</a>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="m-0 text-[13px]" aria-live="polite">
            {ask.state === "asking" && <span className="text-fg-2">Getting the exact price…</span>}
            {ask.state === "failed" && <span className="text-warn">{ask.message}</span>}
            {ask.state === "ok" && (ask.r.free
              ? <span className="text-soft">Free: already rendered with these settings.</span>
              : <span><b className="font-semibold text-text">{creditWords(ask.r.credits)}</b> <span className="text-fg-2">· exact price, refunded if the render fails</span></span>)}
          </p>
          {ask.state === "ok" && ask.r.free && ask.r.existing
            ? <a className="btn small primary" href={ask.r.existing} download>Download</a>
            : <button type="button" className="btn small primary" disabled={ask.state !== "ok" || short || !known.exportRoute} onClick={run}>
                {ask.state === "ok" ? (ask.r.free ? "Get it" : `Export for ${creditWords(ask.r.credits)}`) : "Export"}</button>}
        </div>
      )}
      {short && progress === null && <p className="m-0 text-[12px] text-warn">You have {creditWords(me.credits)}. <Link href="/dashboard/pricing/" className="text-text underline">Get more credits</Link></p>}
    </section>
  );
}
