"use client";
// Self-service removal of this account's link imports (POST /v1/imports/takedown, PR #239). Consent checkbox
// required; exactly one of a source URL or all_imports. Leaves admin/global takedown and the public report form
// alone. On 404 (API not shipped yet) shows the error — never invents success.
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { takedownBody } from "@/lib/imports";
import { Icon } from "./Icon";

const CONSENT = "I own these imports or have permission to remove them from my ClutchClips account";

type Mode = "url" | "all";

export function ImportTakedown({ onDone }: { onDone?: () => void }) {
  const [mode, setMode] = useState<Mode>("url");
  const [url, setUrl] = useState("");
  const [consent, setConsent] = useState(false);
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [summary, setSummary] = useState("");

  const ready = consent && (mode === "all" || !!url.trim());

  async function run() {
    if (!ask || !ready) return;
    setProblem(""); setBusy(true); setSummary("");
    try {
      const body = takedownBody(mode === "all"
        ? { consent: true, all_imports: true }
        : { consent: true, url: url.trim() });
      const r = await api("/v1/imports/takedown", { body });
      const removed = typeof r?.uploads_removed === "number" ? r.uploads_removed : 0;
      const cancelled = Array.isArray(r?.jobs_cancelled) ? r.jobs_cancelled.length : 0;
      setSummary(removed || cancelled
        ? `Removed ${removed} import${removed === 1 ? "" : "s"}${cancelled ? `; stopped ${cancelled} job${cancelled === 1 ? "" : "s"}` : ""}.`
        : "Nothing left to remove for that target on this account.");
      setAsk(false); setConsent(false);
      onDone?.();
    } catch (e) {
      setProblem(e instanceof ApiError || e instanceof Error ? e.message : "The takedown could not run.");
    } finally { setBusy(false); }
  }

  return (
    <section className="grid gap-3 rounded-16 border border-solid border-line bg-panel p-4" aria-labelledby="import-takedown-title">
      <div className="grid gap-1">
        <h2 id="import-takedown-title" className="m-0 flex items-center gap-2 text-[16px] font-semibold">
          <Icon name="shield" size={18} className="text-muted" />Remove my imported videos</h2>
        <p className="m-0 max-w-[620px] text-[13.5px] leading-[1.45] text-muted">
          Takes down link imports on <b className="font-medium text-text">this account only</b>: files and clips for that
          source, with waiting jobs cancelled and their credits returned. Uploaded files you added by hand are kept
          unless you delete them from the library. This is not the public copyright report form.
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="What to remove">
        <button type="button" className={`btn small ${mode === "url" ? "primary" : "ghost"}`} aria-pressed={mode === "url"}
          onClick={() => { setMode("url"); setAsk(false); setProblem(""); }}>One source URL</button>
        <button type="button" className={`btn small ${mode === "all" ? "primary" : "ghost"}`} aria-pressed={mode === "all"}
          onClick={() => { setMode("all"); setAsk(false); setProblem(""); }}>All my imports</button>
      </div>

      {mode === "url" && (
        <label className="grid gap-1 text-[13.5px]">Source URL
          <input type="url" inputMode="url" value={url} placeholder="https://www.twitch.tv/videos/…"
            className="min-h-[42px] rounded-12 border border-solid border-line bg-bg px-3 text-[14px]"
            onChange={(e) => { setUrl(e.target.value); setAsk(false); }} />
        </label>
      )}
      {mode === "all" && (
        <p className="m-0 text-[13.5px] text-warn">This removes every link import on your account. Hand uploads stay.</p>
      )}

      <label className="check consent m-0 text-[13.5px] text-label">
        <input type="checkbox" checked={consent} onChange={(e) => { setConsent(e.target.checked); setAsk(false); }} />
        <span>{CONSENT}</span>
      </label>

      {!ask ? (
        <div>
          <button type="button" className="btn small ghost danger" disabled={!ready}
            onClick={() => { setAsk(true); setProblem(""); setSummary(""); }}>
            Continue</button>
        </div>
      ) : (
        <div role="group" aria-label="Confirm import takedown" className="grid gap-2 rounded-12 border border-solid border-line bg-card-2 p-3">
          <p className="m-0 text-[13.5px] text-label">
            {mode === "all"
              ? "Remove all link imports on this account? Waiting jobs are refunded."
              : `Remove imports for ${url.trim()} on this account? Waiting jobs are refunded.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn small ghost danger" disabled={busy || !consent} onClick={run}>
              {busy ? "Removing…" : "Confirm removal"}</button>
            <button type="button" className="btn small ghost" disabled={busy} onClick={() => setAsk(false)}>Cancel</button>
          </div>
        </div>
      )}

      {problem && <p className="error m-0" role="alert">{problem}</p>}
      {summary && <p className="notice m-0" role="status">{summary}</p>}
    </section>
  );
}
