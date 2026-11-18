"use client";
// A pasted link: pick what to make from it, see the price, tick consent, then one button imports the video and
// starts the tool on it. Steps on the page follow the import; the project (or tool) page follows the job.
// Data: POST /v1/imports/preview when this API has it (found in /openapi.json, never probed), GET /v1/options,
// GET /v1/languages, the template routes, POST /v1/imports, then the tool's own route. Styles: app-shell.css `.chooser`.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, clock, videoFileProblem } from "@/lib/api";
import { useLanguages } from "@/lib/languages";
import { allows, inside, Listed, onlyListed, useClipOptions } from "@/lib/options";
import { route } from "@/lib/routes";
import { AS_IT_IS, extrasFrom, loadCustom, loadTemplates, Look, lookFrom, Saved, startLook, tidy } from "@/lib/templates";
import { isBuilt, ToolEntry, TOOLS } from "@/lib/tools";
import { Icon } from "./Icon";
import { AspectSelect, Picked, PreEdit, Templates } from "./PreEdit";
import { useDash } from "./Shell";
import { captionStyles, firstStyle, framing } from "./ToolPanel";
import { ACCEPT, UploadProgress, useUpload } from "./Upload";

type Kind = "clips" | "find" | "captions" | "reframe" | "transcripts" | "summary";
type Preview = { url?: string; platform?: string; supported?: boolean; title?: string; channel?: string; duration_sec?: number;
  thumbnail_url?: string; kind?: string; refusal?: string | { code?: string; message?: string } | null };
const CONSENT = "I own this video or have permission to clip it";
const AUTO = "0-90";
const BUCKETS: Record<string, string> = { "0-90": "Auto (under 90 s)", "0-30": "Under 30 seconds", "30-60": "30 to 60 seconds", "60-90": "60 to 90 seconds",
  "90-180": "1½ to 3 minutes", "180-300": "3 to 5 minutes" };
const shortest = (b: string) => +b.split("-")[0] || 0;
const GO: Record<Kind, string> = { clips: "Import and find the clips", find: "Import and search", captions: "Import and add captions",
  reframe: "Import and reframe", transcripts: "Import and transcribe", summary: "Import and summarise" };
const PLATFORM: Record<string, string> = { twitch: "Twitch", kick: "Kick", youtube: "YouTube", gdrive: "Google Drive", dropbox: "Dropbox", direct: "Direct link" };
const perMinute = (k: Kind) => k !== "captions" && k !== "reframe";
const minutes = (sec: number) => Math.max(1, Math.ceil(sec / 60));            // the API's rule: one credit per started minute
const kindOf = (t: ToolEntry): Kind | null => (t.tool || (t.id === "transcripts" ? "transcripts" : t.id === "summary" ? "summary" : t.id === "templates" ? "clips" : null)) as Kind | null;
const refusalText = (r: Preview["refusal"]) => (typeof r === "string" ? r : r?.message || "");
const hostOf = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

export function LinkChooser() {
  const router = useRouter();
  const { fail, me, reloadMe } = useDash();
  const listed = useClipOptions(), langs = useLanguages();
  const on = langs ? { summaries: langs.summaries, translation: langs.translation } : null;
  const [url, setUrl] = useState(""), [kind, setKind] = useState<Kind>("clips"), [consent, setConsent] = useState(false);
  const [preview, setPreview] = useState<Preview | null | undefined>(undefined);       // undefined: asking; null: no preview route or it failed
  const [step, setStep] = useState<{ text: string; pct?: number } | null>(null), [problem, setProblem] = useState("");
  const [confirm, setConfirm] = useState<{ upload: any } | null>(null);              // the exact price, when it is more than shown
  // Options per tool.
  const [o, setO] = useState({ source_lang: "", duration: AUTO, query: "", clip_length: 30, aspect: "9:16", caption_style: "", target_lang: "" });
  const set = (c: Partial<typeof o>) => setO((x) => ({ ...x, ...c }));
  const [pre, setPre] = useState(true), [look, setLook] = useState<Look | null>(null), [picked, setPicked] = useState<Picked>(null);
  const [templates, setTemplates] = useState<Templates>({ presets: [], games: [] }), [saved, setSaved] = useState<Saved[] | null>(null);
  const file = useRef<HTMLInputElement>(null);
  // "Upload the file instead": the uploaded video opens on the chosen tool's own form, where its price is shown.
  const { up, start: upload, cancel } = useUpload((u) => router.push(kind === "transcripts" ? `/dashboard/transcript/?id=${u.upload_id}`
    : kind === "summary" ? `/dashboard/summary/?id=${u.upload_id}` : `/dashboard/project/?id=${u.upload_id}&tool=${kind}`));

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const u = q.get("url") || "";
    setUrl(u);
    const t = TOOLS.find((x) => x.id === q.get("tool"));
    if (t && kindOf(t)) setKind(kindOf(t)!);
    route("post", "/v1/imports/preview").then((r) => r
      ? api<Preview>("/v1/imports/preview", { body: { url: u } }).then(setPreview).catch((e) => setPreview({ supported: false, refusal: e instanceof Error ? e.message : "" }))
      : setPreview(null));
    loadTemplates().then(setTemplates).catch(() => {});
    loadCustom().then(setSaved).catch(fail);
  }, [fail]);
  useEffect(() => {
    if (!listed) return;
    setLook((x) => x || startLook(listed));
    // The API's own defaults: its default template (none today) and its default clip length.
    const d = listed.duration?.default;
    if (typeof d === "string" && allows(listed, "duration", d)) set({ duration: d });
    set({ caption_style: firstStyle(listed) });
  }, [listed]);

  const duration = typeof preview?.duration_sec === "number" && preview.duration_sec > 0 ? preview.duration_sec : null;
  const refused = !!preview && (preview.supported === false || !!refusalText(preview.refusal));
  const chosen = picked?.kind === "template" ? [...templates.presets, ...templates.games].find((t) => t.id === picked.id) : undefined;
  const estimate = duration ? minutes(duration) : null;

  function pick(k: "template" | "saved", item: any | null) {           // the job form's own rule for applying a template
    if (!listed) return;
    if (!item) { setPicked(null); return; }
    setPicked({ kind: k, id: String(item.id) });
    setLook((x) => ({ ...x!, ...lookFrom(item, listed, x!.aspect) }));
    if (k === "template" && typeof item.duration === "string" && allows(listed, "duration", item.duration) && (!duration || shortest(item.duration) <= duration))
      set({ duration: item.duration });
  }

  // The tool's request on an upload, built the way its own form builds it.
  function request(uploadId: string): [string, unknown] {
    const L = listed!;
    const lang = { source_lang: o.source_lang || null };
    if (kind === "clips") {
      const options: Record<string, unknown> = { facecam_region: "auto", zoom: 1, resolution: "1080", chat_region: "none", ...look,
        ...(pre ? {} : AS_IT_IS), template: pre && chosen ? chosen.id : null, ...(pre && chosen ? extrasFrom(chosen, L) : {}), prompt: null, range: null, ...lang };
      if ("duration" in L) options.duration = o.duration; else options.clip_length = 30;
      if ("limit" in L) options.limit = null; else options.max_clips = 3;
      return ["/v1/clips", { upload_id: uploadId, options: onlyListed(L, options) }];
    }
    if (kind === "find") return ["/v1/find", { upload_id: uploadId, query: o.query.trim(), mode: "auto", max_results: 5, make_clips: true, clip_length: o.clip_length,
      options: { ...framing(L, "9:16"), caption_style: firstStyle(L), censor: false, captions: true } }];
    if (kind === "captions" || kind === "reframe") {
      const { aspect, ...unframed } = framing(L, o.aspect);
      return [`/v1/${kind}`, { upload_id: uploadId, options: kind === "reframe"
        ? { ...unframed, aspect, caption_style: o.caption_style, captions: false, censor: false }
        : { ...unframed, caption_style: o.caption_style, censor: false, vertical: false, captions: true } }];
    }
    return [kind === "transcripts" ? "/v1/transcripts" : "/v1/summaries", { upload_id: uploadId, ...lang, target_lang: o.target_lang || null }];
  }
  const after = (uploadId: string) => (kind === "transcripts" ? `/dashboard/transcript/?id=${uploadId}` : kind === "summary" ? `/dashboard/summary/?id=${uploadId}`
    : `/dashboard/project/?id=${uploadId}${kind === "find" ? "&tool=find" : ""}`);

  const runTool = useCallback(async (u: any) => {
    setStep({ text: "Starting…" });
    const [path, body] = request(u.upload_id);
    try { await api(path, { body }); await reloadMe(); router.push(after(u.upload_id)); }
    catch (e) { setStep(null); fail(e); }
  }, [kind, o, look, pre, chosen, listed]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Import, then: the job starts at once when its price is no more than the one shown; otherwise the exact price is asked first.
  async function go(more = false) {
    setProblem("");
    if (kind === "find" && !o.query.trim() && !more) { setProblem("Type what you're looking for first."); return; }
    setStep({ text: "Starting the import…", pct: 0 });
    let imp: any;
    try { imp = await api("/v1/imports", { body: { url, consent: true } }); }
    catch (e) { setStep(null); if (e instanceof ApiError && e.status === 422) setProblem(e.message); else fail(e); return; }
    while (imp.status === "QUEUED" || imp.status === "RUNNING") {
      setStep({ text: imp.status === "QUEUED" ? "Waiting to start the import" : imp.stage === "checking" ? "Checking the video" : imp.stage === "storing" ? "Saving the video" : "Downloading the video", pct: imp.progress || 0 });
      await new Promise((r) => setTimeout(r, 2000));
      try { imp = await api(`/v1/imports/${imp.import_id}`); } catch (e) { setStep(null); fail(e); return; }
    }
    if (imp.status !== "SUCCEEDED" || !imp.upload_id) {
      setStep(null);
      setProblem(imp.error?.message || (imp.status === "FAILED" ? "The import failed. Upload the file instead." : "The import was cancelled."));
      return;
    }
    const u = imp.upload || (await api(`/v1/projects/${imp.upload_id}`));
    if (more) { router.push(`/dashboard/project/?id=${u.upload_id}&tool=${kind === "find" ? "find" : "clips"}${chosen ? `&template=${encodeURIComponent(chosen.id)}` : ""}`); return; }
    if (estimate === null || (!u.analyzed && u.credits_required > estimate)) { setStep(null); setConfirm({ upload: u }); return; }
    await runTool(u);
  }

  const head = <div className="back-title"><Link href="/dashboard/" aria-label="Back to Home"><Icon name="back" size={20} /></Link><h1>What should we make from this video?</h1></div>;
  if (!url) return <div className="form-col">{head}<p className="empty-note">No link to work with. <Link href="/dashboard/">Paste one on Home</Link>.</p></div>;
  const chips = TOOLS.filter((t) => t.id !== "editor");
  const busy = !!step;
  const ready = consent && !busy && !refused && !!listed && me.email_verified && (kind !== "find" || !!o.query.trim());
  const priceText = estimate === null
    ? "One credit per minute of video. The video's length is known once it is in; you see the exact price before anything is charged."
    : perMinute(kind)
      ? `Uses ${estimate} credit${estimate === 1 ? "" : "s"} (one per minute of video). The import is free; a failed or cancelled job gives its credits back.`
      : `Uses one credit per minute rendered, up to ${estimate}. The import is free.`;

  return (
    <div className="chooser">
      <header className="chooser-head">{head}</header>
      <ul className="chooser-tools" aria-label="What to make">
        {chips.map((t) => {
          const k = kindOf(t), ok = isBuilt(t, on) && !!k;
          const sel = ok && k === kind && (t.id === "templates" ? false : true);
          return <li key={t.id}>{ok
            ? <button type="button" className="tool-chip" aria-pressed={sel} disabled={busy} onClick={() => { setKind(k!); if (t.id === "templates") document.getElementById("chooser-templates")?.scrollIntoView({ block: "start" }); }}>
                <Icon name={t.icon} size={18} />{t.name}</button>
            : <span className="tool-chip soon" aria-disabled="true"><Icon name={t.icon} size={18} />{t.name}<small className="soon-tag">Soon</small></span>}</li>;
        })}
      </ul>

      <p className="link-pill" title={url}><Icon name="link" size={16} /><span>{url}</span></p>
      <article className="preview-card">
        {preview === undefined ? <p className="muted">Looking at the link…</p> : <>
          {preview?.thumbnail_url && <span className="preview-thumb"><img src={preview.thumbnail_url} alt="" />
            {duration && <span className="project-len">{clock(duration)}</span>}</span>}
          <strong>{preview?.title || hostOf(url)}</strong>
          <span className="muted small">{[preview?.kind && tidy(preview.kind), PLATFORM[preview?.platform || ""] || preview?.platform, preview?.channel, !preview?.thumbnail_url && duration ? clock(duration) : null]
            .filter(Boolean).join(" · ") || "The video's details show once it is imported."}</span>
        </>}
      </article>
      {refused && <div className="error refusal" role="alert">
        <p>{refusalText(preview!.refusal) || "This link can't be imported."}</p>
        <input ref={file} type="file" accept={ACCEPT} hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) { const bad = videoFileProblem(f); if (bad) setProblem(bad); else upload(f); } }} />
        {up ? <UploadProgress up={up} onCancel={cancel} /> : <button type="button" className="btn small primary" onClick={() => file.current?.click()}><Icon name="upload" size={16} />Upload the file instead</button>}
      </div>}

      {!refused && listed && langs && look && <section className="panel chooser-options" aria-label="Options">
        {(kind === "clips" || kind === "transcripts" || kind === "summary") && <div className="opt-rows">
          <label>Language spoken<select value={o.source_lang} disabled={busy} onChange={(e) => set({ source_lang: e.target.value })}>
            {listed.source_lang?.nullable !== false && <option value="">Detect it for me</option>}
            {(listed.source_lang?.values || langs.languages.filter((l) => l.transcribe).map((l) => l.code)).map((c: string) =>
              <option key={c} value={c}>{langs.languages.find((l) => l.code === c)?.name || c}</option>)}</select></label>
          {kind === "clips" && "duration" in listed && <label>Clip length<select value={o.duration} disabled={busy} onChange={(e) => set({ duration: e.target.value })}>
            {[AUTO, ...(listed.duration.values || []).filter((b: string) => b !== AUTO)].filter((b) => allows(listed, "duration", b)).map((b) => (
              <option key={b} value={b} disabled={!!duration && shortest(b) > duration}>{BUCKETS[b] || b}</option>))}</select></label>}
          {kind === "summary" && langs.translation && <label>Write the summary in<select value={o.target_lang} disabled={busy} onChange={(e) => set({ target_lang: e.target.value })}>
            <option value="">The language spoken</option>{langs.languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
        </div>}
        {kind === "find" && <div className="opt-rows">
          <label>What are you looking for?<input value={o.query} maxLength={200} disabled={busy} placeholder="a police chase, or something that was said" onChange={(e) => set({ query: e.target.value })} /></label>
          <label>Clip length<select value={o.clip_length} disabled={busy} onChange={(e) => set({ clip_length: +e.target.value })}>
            {inside(listed.clip_length, [15, 20, 30, 40, 45, 60]).map((n) => <option key={n} value={n}>{n} seconds</option>)}</select></label>
        </div>}
        {kind === "reframe" && <div className="opt-rows"><AspectSelect listed={listed} value={o.aspect} onChange={(v) => set({ aspect: v })} /></div>}
        {kind === "captions" && <div className="opt-rows"><label>Caption style<select value={o.caption_style} disabled={busy} onChange={(e) => set({ caption_style: e.target.value })}>
          {captionStyles(listed).map((s) => <option key={s} value={s}>{tidy(s)}</option>)}</select></label></div>}
        {(kind === "clips" || kind === "find") && <button type="button" className="link small more-opts" disabled={!consent || busy} onClick={() => go(true)}
          title={consent ? "Imports the video, then opens the full settings (nothing is charged until you start)" : "Tick the box below first"}>
          More options: import first, then open the full settings</button>}
      </section>}

      {!refused && kind === "clips" && listed && look && <section id="chooser-templates" className="chooser-templates" aria-label="Template">
        <PreEdit listed={listed} on={pre} onToggle={setPre} look={look} onLook={(c) => setLook((x) => ({ ...x!, ...c }))}
          picked={picked} onPick={pick} templates={templates} saved={saved} onSavedChange={() => loadCustom().then(setSaved).catch(fail)} />
      </section>}

      {!refused && <div className="chooser-go">
        {confirm ? <>
          <p className="muted">The video is in: {clock(confirm.upload.duration_sec)} long. {perMinute(kind)
            ? `This uses ${confirm.upload.credits_required} credit${confirm.upload.credits_required === 1 ? "" : "s"} (one per minute of video).`
            : `This uses one credit per minute rendered, up to ${confirm.upload.credits_required}.`}</p>
          <div className="row"><button type="button" className="btn primary" onClick={() => runTool(confirm.upload)}>Start</button>
            <Link className="btn ghost" href={`/dashboard/project/?id=${confirm.upload.upload_id}`}>Not now, open the project</Link></div>
        </> : <>
          <label className="check consent"><input type="checkbox" checked={consent} disabled={busy} onChange={(e) => setConsent(e.target.checked)} /><span>{CONSENT}</span></label>
          {problem && <p className="error" role="alert">{problem}</p>}
          {step ? <div className="uploading" role="status"><p>{step.text}{typeof step.pct === "number" ? ` ${step.pct}%` : ""}</p>
              {typeof step.pct === "number" && <progress max={100} value={step.pct} aria-label="Import progress" />}</div>
            : <div className="row start-row"><p className="muted">{priceText}</p>
              <button type="button" className="btn primary" disabled={!ready} onClick={() => go()}>{GO[kind]}</button></div>}
        </>}
      </div>}
    </div>
  );
}
