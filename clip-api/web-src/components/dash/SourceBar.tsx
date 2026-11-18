"use client";
// Home's one input: paste a public link (imported through POST /v1/imports) or upload a file.
// Every import needs the consent box ticked; the API logs it. A site that refuses fails with the API's own
// message, which tells the user to upload the file instead. Styles: app/app-shell.css (`.source-bar`).
import { useEffect, useRef, useState } from "react";
import { api, ApiError, videoFileProblem } from "@/lib/api";
import { Icon } from "./Icon";
import { useDash } from "./Shell";
import { ACCEPT, UploadProgress, useUpload } from "./Upload";

type Sources = { enabled: boolean; sources: { platform: string; name: string; accepts: string; note?: string }[]; bulk_max: number; consent: string };
const isLink = (v: string) => /^https?:\/\/\S+\.\S+/i.test(v.trim());
const STAGE: Record<string, string> = { importing: "Downloading", checking: "Checking the video", storing: "Saving", done: "Done" };

let asked: Promise<Sources | null> | null = null;
const loadSources = () => (asked ??= api<Sources>("/v1/imports/sources", { auth: false }).catch(() => { asked = null; return null; }));

// Follows one import until it has an upload, failed or was cancelled.
function useImportWatch(onReady: (uploadId: string) => void) {
  const { fail } = useDash();
  const [imp, setImp] = useState<any>(null);
  const done = useRef(onReady);
  done.current = onReady;
  useEffect(() => {
    if (!imp || !["QUEUED", "RUNNING"].includes(imp.status)) {
      if (imp?.status === "SUCCEEDED" && imp.upload_id) done.current(imp.upload_id);
      return;
    }
    const t = setTimeout(() => api(`/v1/imports/${imp.import_id}`).then(setImp).catch(fail), 2000);
    return () => clearTimeout(t);
  }, [imp, fail]);
  return [imp, setImp] as const;
}

// `pending` is a file picked on the public home page before signing up: it is uploaded as soon as this appears.
export function SourceBar({ onUploaded, pending }: { onUploaded: (uploadId: string) => void; pending?: File | null }) {
  const { fail, me } = useDash();
  const [text, setText] = useState(""), [agree, setAgree] = useState(false), [problem, setProblem] = useState("");
  const [sources, setSources] = useState<Sources | null>(null), [over, setOver] = useState(false), [busy, setBusy] = useState(false);
  const [bulk, setBulk] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const { up, start, cancel } = useUpload((u) => onUploaded(u.upload_id));
  const [imp, setImp] = useImportWatch(onUploaded);
  useEffect(() => { loadSources().then(setSources); }, []);
  useEffect(() => { if (pending) start(pending); }, [pending]);   // eslint-disable-line react-hooks/exhaustive-deps

  const links = !!sources?.enabled;
  const linkTyped = isLink(text);
  function take(f: File | null | undefined) {
    if (!f) return;
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start(f);
  }
  async function go(e: React.FormEvent) {
    e.preventDefault();
    setProblem("");
    if (!text.trim()) { file.current?.click(); return; }
    if (!links) { setProblem("Link import is switched off right now. Upload the file instead."); return; }
    if (!linkTyped) { setProblem("That doesn't look like a link. Paste the full address, starting with https://"); return; }
    if (!agree) { setProblem("Tick the box to confirm you own this video or have permission to clip it."); return; }
    setBusy(true);
    try { setImp(await api("/v1/imports", { body: { url: text.trim(), consent: true } })); }
    catch (err) { if (err instanceof ApiError && err.status !== 401 && err.status !== 0) setProblem(err.message); else fail(err); }
    finally { setBusy(false); }
  }

  const importing = imp && ["QUEUED", "RUNNING"].includes(imp.status);
  const names = sources?.sources.map((s) => s.name) || [];
  return (
    <div className={`source-bar ${over ? "over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!up && !importing) take(e.dataTransfer.files[0]); }}>
      <input ref={file} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      {up ? <div className="source-status"><UploadProgress up={up} onCancel={cancel} /></div>
        : importing ? <div className="source-status uploading" role="status">
            <p>Importing {imp.platform ? `from ${sources?.sources.find((s) => s.platform === imp.platform)?.name || imp.platform}` : "your link"}: {STAGE[imp.stage] || "Working on it"}</p>
            <progress max={100} value={imp.progress || 0} aria-label="Import progress" />
            <p className="muted">{imp.progress || 0}% <button className="link" onClick={() => api(`/v1/imports/${imp.import_id}/cancel`, { body: {} }).then(setImp).catch(fail)}>Cancel</button></p>
          </div>
        : <form className="source-form" onSubmit={go}>
            <div className="source-field">
              <label htmlFor="source-input" className="sr-only">{links ? "Video link" : "Video"}</label>
              <input id="source-input" value={text} onChange={(e) => setText(e.target.value)} disabled={!links} inputMode="url" autoComplete="off"
                placeholder={links ? "Paste a Twitch or Kick link, or upload a recording" : "Upload a stream recording to start"} />
              <button className="source-go" aria-label={text.trim() ? "Import this link" : "Choose a file to upload"} disabled={busy || !me.email_verified}>
                <Icon name="arrow" size={22} /></button>
            </div>
            {linkTyped && links && <label className="check source-consent"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              <span>{sources?.consent || "I own this content or have permission to clip it."} Imports are free and logged.</span></label>}
          </form>}
      {(problem || imp?.status === "FAILED") && <p className="error" role="alert">{problem || imp.error?.message || "The import failed. Upload the file instead."}</p>}
      <div className="source-row">
        <button type="button" className="source-chip" disabled={!!up || importing} onClick={() => file.current?.click()}><Icon name="upload" size={16} />Upload</button>
        <button type="button" className="source-chip" disabled={!links || !!up || importing} onClick={() => setBulk(true)}><Icon name="stack" size={16} />Bulk import</button>
        {names.length > 0 && <span className="source-chip plain" title={sources!.sources.map((s) => `${s.name}: ${s.accepts}${s.note ? ` ${s.note}` : ""}`).join("\n")}>
          <Icon name="link" size={16} />{names.slice(0, 2).join(", ")} + {names.length - 2} more</span>}
      </div>
      {bulk && sources && <BulkImport sources={sources} onClose={() => setBulk(false)} />}
    </div>
  );
}

// Several links at once (up to the API's `bulk_max`). Each one is its own import; the list shows how each is doing.
function BulkImport({ sources, onClose }: { sources: Sources; onClose: () => void }) {
  const { fail } = useDash();
  const dialog = useRef<HTMLDialogElement>(null);
  const [text, setText] = useState(""), [agree, setAgree] = useState(false), [problem, setProblem] = useState("");
  const [rows, setRows] = useState<any[] | null>(null), [busy, setBusy] = useState(false);
  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal(); }, []);
  const urls = text.split(/\s+/).map((u) => u.trim()).filter(Boolean);
  const live = rows?.some((r) => r.import && ["QUEUED", "RUNNING"].includes(r.import.status));
  useEffect(() => {
    if (!live) return;
    const t = setTimeout(() => Promise.all(rows!.map((r) => (r.import ? api(`/v1/imports/${r.import.import_id}`).then((i) => ({ ...r, import: i })) : r)))
      .then(setRows).catch(fail), 2500);
    return () => clearTimeout(t);
  }, [rows, live, fail]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setProblem("");
    if (!urls.length) { setProblem("Paste at least one link, one per line."); return; }
    if (urls.length > sources.bulk_max) { setProblem(`Paste at most ${sources.bulk_max} links at once.`); return; }
    if (!agree) { setProblem("Tick the box to confirm you own these videos or have permission to clip them."); return; }
    setBusy(true);
    try { setRows((await api("/v1/imports/bulk", { body: { urls, consent: true } })).imports); }
    catch (err) { if (err instanceof ApiError && err.status === 422) setProblem(err.message); else fail(err); }
    finally { setBusy(false); }
  }
  const state = (r: any) => r.error ? r.error.message : r.import.status === "SUCCEEDED" ? "Ready"
    : r.import.status === "FAILED" ? (r.import.error?.message || "Failed. Upload the file instead.") : r.import.status === "CANCELED" ? "Cancelled" : `${r.import.progress || 0}%`;

  return (
    <dialog ref={dialog} className="picker" aria-labelledby="bulk-title" onClose={onClose} onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}>
      <div className="picker-body">
        <div className="picker-head">
          <h2 id="bulk-title">Bulk import</h2>
          <button className="icon-btn" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" /></button>
        </div>
        {!rows ? <form className="stack-s" onSubmit={send}>
            <label>Links, one per line (up to {sources.bulk_max})
              <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder={"https://www.twitch.tv/videos/…\nhttps://kick.com/…"} /></label>
            <p className="muted small">Works with {sources.sources.map((s) => s.name).join(", ")}. Imports are free.</p>
            <label className="check"><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} /><span>{sources.consent}</span></label>
            {problem && <p className="error" role="alert">{problem}</p>}
            <div><button className="btn primary" disabled={busy}>{busy ? "Sending…" : `Import ${urls.length || ""} link${urls.length === 1 ? "" : "s"}`}</button></div>
          </form>
          : <>
            <ul className="bulk-list" aria-live="polite">
              {rows.map((r, i) => (
                <li key={i}><span className="bulk-url" title={r.url}>{r.url}</span>
                  {r.import?.status === "SUCCEEDED" && r.import.upload_id
                    ? <a className="more" href={`/dashboard/project/?id=${r.import.upload_id}`}>Open</a>
                    : <span className={r.error || r.import?.status === "FAILED" ? "bad" : "muted"}>{state(r)}</span>}</li>))}
            </ul>
            <p className="muted small">Finished imports show up in your Library. You can close this window; imports keep going.</p>
          </>}
      </div>
    </dialog>
  );
}
