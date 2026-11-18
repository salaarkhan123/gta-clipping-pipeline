"use client";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError, clock } from "@/lib/api";
import { Icon } from "./Icon";
import { Tabs } from "./Tabs";

// Link import: a public video link becomes a project. Every import needs the user's word that they own the video
// or may clip it (sent as `consent: true`); the API logs it and refuses what it cannot fetch, and its words are
// shown exactly as they come.
export type Sources = { enabled: boolean; sources: { platform: string; name: string; accepts: string; example?: string; note?: string }[];
  bulk_max: number; max_bytes: number; max_duration_sec: number };
const CONSENT = "I own this video or have permission to clip it";
const STAGES: Record<string, string> = { importing: "Downloading", checking: "Checking the file", storing: "Saving", done: "Done" };
const active = (i: any) => i?.status === "QUEUED" || i?.status === "RUNNING";
const gb = (n: number) => `${Math.round(n / 1024 ** 3)} GB`;

// undefined while asking; null when this API has no link import (the box is not shown).
let asked: Promise<Sources | null> | null = null;
export function useImportSources(): Sources | null | undefined {
  const [s, setS] = useState<Sources | null | undefined>(undefined);
  useEffect(() => {
    let on = true;
    if (!asked) {
      asked = api<Sources>("/v1/imports/sources", { auth: false }).then((r) => (Array.isArray(r?.sources) ? r : null))
        .catch((e) => { if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null; asked = null; return null; });
    }
    asked.then((r) => on && setS(r));
    return () => { on = false; };
  }, []);
  return s;
}

// The box. `onReady` gets the new upload when a single import finishes (Home opens the project). `recent` adds the
// list of the account's last imports.
export function ImportBox({ sources, onReady, recent, compact }: { sources: Sources; onReady: (upload: any) => void; recent?: boolean; compact?: boolean }) {
  const ids = useId();
  const [mode, setMode] = useState<"one" | "many">("one");
  const [url, setUrl] = useState(""), [urls, setUrls] = useState(""), [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false), [problem, setProblem] = useState("");
  const [single, setSingle] = useState<any>(null);                                  // the import being followed
  const [batch, setBatch] = useState<{ url: string; import: any; error: any }[] | null>(null);
  const [reload, setReload] = useState(0);
  const lines = urls.split("\n").map((l) => l.trim()).filter(Boolean);
  const tooMany = lines.length > sources.bulk_max;
  const off = !sources.enabled;

  async function importOne() {
    setProblem(""); setBusy(true);
    try { setSingle(await api("/v1/imports", { body: { url: url.trim(), consent: true } })); setReload((n) => n + 1); }
    catch (e) { setProblem(e instanceof Error ? e.message : "The import could not start."); }
    finally { setBusy(false); }
  }
  async function importMany() {
    setProblem(""); setBusy(true);
    try { const r = await api("/v1/imports/bulk", { body: { urls: lines, consent: true } }); setBatch(r.imports); setReload((n) => n + 1); }
    catch (e) { setProblem(e instanceof Error ? e.message : "The imports could not start."); }
    finally { setBusy(false); }
  }

  const ready = consent && !busy && !off && (mode === "one" ? !!url.trim() : lines.length > 0 && !tooMany);
  return (
    <div className={`import ${compact ? "compact" : ""}`}>
      <div className="import-head">
        <h2 className="import-title"><Icon name="link" />Import from a link</h2>
        <Tabs label="Import" panel={`${ids}panel`} value={mode} onChange={(m) => { setMode(m); setProblem(""); }}
          tabs={[["one", "One link"], ["many", `Several links (up to ${sources.bulk_max})`]]} />
      </div>
      <form id={`${ids}panel`} role="tabpanel" aria-label={mode === "one" ? "One link" : "Several links"} className="import-form"
        onSubmit={(e) => { e.preventDefault(); if (ready) (mode === "one" ? importOne() : importMany()); }}>
        {mode === "one"
          ? <label className="grow">Video link
              <input type="url" inputMode="url" value={url} placeholder="https://www.twitch.tv/videos/…" disabled={off}
                onChange={(e) => setUrl(e.target.value)} /></label>
          : <label className="grow">Video links, one per line
              <textarea rows={4} value={urls} placeholder={"https://www.twitch.tv/videos/…\nhttps://kick.com/…"} disabled={off}
                aria-describedby={`${ids}count`} onChange={(e) => setUrls(e.target.value)} />
              <span id={`${ids}count`} className={`small ${tooMany ? "warn" : "muted"}`}>{lines.length} of {sources.bulk_max} links{tooMany ? `: remove ${lines.length - sources.bulk_max} to import` : ""}</span></label>}
        <label className="check consent"><input type="checkbox" checked={consent} required disabled={off} onChange={(e) => setConsent(e.target.checked)} />
          <span>{CONSENT}</span></label>
        <div className="import-go">
          <button className="btn primary" disabled={!ready}><Icon name="link" />{busy ? "Starting…" : mode === "one" ? "Import" : `Import ${lines.length || ""} link${lines.length === 1 ? "" : "s"}`.replace("  ", " ")}</button>
          <span className="muted small">Free. Public videos only: nothing that needs a login.</span>
        </div>
        {off && <p className="notice">Link import is switched off for now. Upload the file instead.</p>}
        {problem && <p className="error" role="alert">{problem}</p>}
      </form>

      {mode === "one" && single && <ImportCard key={single.import_id} item={single} onReady={onReady} />}
      {mode === "many" && batch && <ul className="import-batch" aria-label="Links sent">
        {batch.map((b, i) => <li key={`${i}-${b.url}`}>
          {b.import ? <ImportCard item={b.import} />
            : <div className="import-card refused"><p className="import-url" title={b.url}>{b.url}</p><p className="error">{b.error?.message || "Refused."}</p></div>}
        </li>)}
      </ul>}

      <details className="import-sources">
        <summary>What you can import</summary>
        <ul>
          {sources.sources.map((s) => <li key={s.platform}><b>{s.name}</b> <span className="muted">{s.accepts}{s.note ? ` ${s.note}` : ""}</span></li>)}
        </ul>
        <p className="muted small">Up to {gb(sources.max_bytes)} and {clock(sources.max_duration_sec)} per video, {sources.bulk_max} links at a time.
          The link has to open in a signed-out browser. If a site refuses, upload the file instead.</p>
      </details>
      {recent && <RecentImports reload={reload} />}
    </div>
  );
}

// One import: where it is, a cancel button while it runs, the API's own words when it fails. Follows the import
// until it ends; `onReady` is called once with the upload.
function ImportCard({ item, onReady }: { item: any; onReady?: (upload: any) => void }) {
  const [it, setIt] = useState(item), [cancelling, setCancelling] = useState(false), [problem, setProblem] = useState("");
  const told = useRef(false);
  useEffect(() => {
    if (!active(it)) return;
    const t = setTimeout(() => api(`/v1/imports/${it.import_id}`).then(setIt).catch((e) => setProblem(e instanceof Error ? e.message : "")), 2000);
    return () => clearTimeout(t);
  }, [it]);
  useEffect(() => {
    if (it.upload_id && onReady && !told.current) { told.current = true; onReady(it.upload || { upload_id: it.upload_id }); }
  }, [it, onReady]);
  const cancel = () => { setCancelling(true); api(`/v1/imports/${it.import_id}/cancel`, { body: {} }).then(setIt).catch((e) => setProblem(e.message)).finally(() => setCancelling(false)); };
  const status = active(it) ? `${it.status === "QUEUED" ? "Waiting to start" : STAGES[it.stage] || "Importing"} ${it.progress || 0}%`
    : it.status === "SUCCEEDED" ? (it.upload_id ? "Imported" : "Imported, no longer stored") : it.status === "FAILED" ? "Failed" : "Cancelled";
  return (
    <article className={`import-card ${String(it.status).toLowerCase()}`} aria-label={`Import of ${it.url}`}>
      <div className="import-card-head">
        <p className="import-url" title={it.url}>{it.url}</p>
        <span className="status" role="status">{status}</span>
      </div>
      {active(it) && <progress max={100} value={it.progress || 0} aria-label="Import progress" />}
      {active(it) && <p className="import-foot"><button type="button" className="link" disabled={cancelling} onClick={cancel}>{cancelling ? "Cancelling…" : "Cancel"}</button>
        {it.reused && <span className="muted small">Already imported: using the stored copy.</span>}</p>}
      {it.status === "FAILED" && it.error?.message && <p className="error">{it.error.message}</p>}
      {it.upload_id && <p><Link className="btn small primary" href={`/dashboard/project/?id=${it.upload_id}`}>Open project</Link></p>}
      {problem && <p className="error" role="alert">{problem}</p>}
    </article>
  );
}

function RecentImports({ reload }: { reload: number }) {
  const [list, setList] = useState<any[] | null>(null);
  useEffect(() => { api("/v1/imports?limit=5").then((r) => setList(r.imports)).catch(() => setList(null)); }, [reload]);
  const anyActive = !!list?.some(active);
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(() => api("/v1/imports?limit=5").then((r) => setList(r.imports)).catch(() => {}), 4000);
    return () => clearInterval(t);
  }, [anyActive]);
  if (!list?.length) return null;
  return (
    <div className="import-recent">
      <h3>Recent imports</h3>
      <ul>
        {list.map((i) => <li key={i.import_id}>
          <span className="import-url" title={i.url}>{i.url}</span>
          <span className={`muted small st-${String(i.status).toLowerCase()}`}>{active(i) ? `${STAGES[i.stage] || "Waiting"} ${i.progress || 0}%`
            : i.status === "SUCCEEDED" ? "Imported" : i.status === "FAILED" ? "Failed" : "Cancelled"}</span>
          {i.upload_id ? <Link className="more" href={`/dashboard/project/?id=${i.upload_id}`}>Open</Link>
            : i.status === "FAILED" && i.error?.message ? <span className="small import-why" title={i.error.message}>{i.error.message}</span> : <span />}
        </li>)}
      </ul>
    </div>
  );
}
