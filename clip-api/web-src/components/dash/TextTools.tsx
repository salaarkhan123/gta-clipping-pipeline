"use client";
// Video Transcripts and Video Summary: one video, a language, the price, then the result.
// API: GET /v1/languages, POST /v1/transcripts, POST /v1/summaries, GET /v1/transcripts/{id}(/download),
// GET /v1/summaries/{id}. Both are jobs priced like Video Finder's index (see routes_text.py): the video's minutes
// once (the upload's `credits_required`), and on a video already paid for, one credit held and given back.
import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import { API, api, ApiError, clock, getToken } from "@/lib/api";
import { Languages, useLanguages } from "@/lib/languages";
import { Icon } from "./Icon";
import { isActive, JobNote } from "./JobNote";
import { useDash } from "./Shell";

type Kind = "transcript" | "summary";
const NAME: Record<Kind, string> = { transcript: "Video Transcripts", summary: "Video Summary" };

// The upload id from ?id=, the project (for the name, price fields and jobs), and a reload.
function useProject() {
  const { fail } = useDash();
  const [id, setId] = useState<string | null>(null), [project, setProject] = useState<any>(null), [gone, setGone] = useState(false);
  const load = useCallback(async (pid: string) => {
    try { setProject(await api(`/v1/projects/${pid}`)); }
    catch (e) { if (e instanceof ApiError && e.status === 404) setGone(true); else fail(e); }
  }, [fail]);
  useEffect(() => {
    const pid = new URLSearchParams(window.location.search).get("id");
    setId(pid);
    if (pid) load(pid); else setGone(true);
  }, [load]);
  return { id, project, gone, reload: async () => { if (id) await load(id); } };
}

// The price before the button, from the API's own fields: `analyzed` and `credits_required` on the upload.
function Price({ upload }: { upload: any }) {
  return <p className="muted">{upload.analyzed
    ? "This video is already paid for. 1 credit is held while this runs and comes back when it finishes."
    : `Uses ${upload.credits_required} credit${upload.credits_required === 1 ? "" : "s"}, one per minute of video. A video is paid for once: after this, Clip Maker and Video Finder on it only use credits for the minutes they render. A failed or cancelled job gives its credits back.`}</p>;
}

function LanguageSelects({ langs, kind, source, target, onSource, onTarget }: { langs: Languages; kind: Kind; source: string; target: string;
  onSource: (v: string) => void; onTarget: (v: string) => void }) {
  const spoken = langs.languages.filter((l) => l.transcribe);
  return (
    <div className="options">
      <label>Language spoken<select value={source} onChange={(e) => onSource(e.target.value)}>
        <option value="">Detect it for me</option>
        {spoken.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>
      {(kind === "summary" || langs.translation) && <label>{kind === "summary" ? "Write the summary in" : "Translate into"}<select value={target} onChange={(e) => onTarget(e.target.value)}>
        <option value="">{kind === "summary" ? "The language spoken" : "No translation"}</option>
        {(kind === "summary" && !langs.translation ? [] : langs.languages).map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
    </div>
  );
}

async function downloadTranscript(uploadId: string, format: string) {
  const res = await fetch(`${API}/v1/transcripts/${uploadId}/download?format=${format}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, "error", "Couldn't download the transcript.");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob()); a.download = `${uploadId}.${format}`; a.click();
  URL.revokeObjectURL(a.href);
}

export function TextTool({ kind }: { kind: Kind }) {
  const { fail, reloadMe, me } = useDash();
  const langs = useLanguages();
  const { id, project, gone, reload } = useProject();
  const [result, setResult] = useState<any>(undefined);          // undefined: asking; null: none yet
  const [source, setSource] = useState(""), [target, setTarget] = useState(""), [busy, setBusy] = useState(false);
  const title = useId();

  const fetchResult = useCallback(async () => {
    if (!id) return;
    try { setResult(await api(kind === "transcript" ? `/v1/transcripts/${id}` : `/v1/summaries/${id}`)); }
    catch (e) { if (e instanceof ApiError && [404, 409].includes(e.status)) setResult(null); else fail(e); }
  }, [id, kind, fail]);
  useEffect(() => { fetchResult(); }, [fetchResult]);

  // This tool's jobs on the video: follow the running one; show the last failure.
  const jobs = (project?.jobs || []).filter((j: any) => j.tool === kind);
  const running = jobs.find(isActive), failed = !running && jobs[0]?.status === "FAILED" ? jobs[0] : null;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(reload, 3000);
    return () => { clearInterval(t); fetchResult(); reloadMe(); };       // it just ended: the result and credits changed
  }, [running?.job_id]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setBusy(true);
    try {
      await api(kind === "transcript" ? "/v1/transcripts" : "/v1/summaries",
        { body: { upload_id: id, source_lang: source || null, target_lang: target || null } });
      await Promise.all([reload(), reloadMe()]);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }
  const cancel = (jobId: string) => api(`/v1/jobs/${jobId}/cancel`, { body: {} }).then(reload).catch(fail);

  const head = <div className="back-title"><Link href="/dashboard/" aria-label="Back to Home"><Icon name="back" size={20} /></Link>
    <h1 id={title}>{NAME[kind]}</h1></div>;
  if (gone) return <div className="form-col">{head}<p className="empty-note">This video isn't here any more. Videos are kept for 7 days. <Link href="/dashboard/">Pick another one</Link></p></div>;
  if (!project || result === undefined || !langs) return <div className="form-col">{head}<p className="muted">Loading…</p></div>;
  const off = kind === "summary" && !langs.summaries;
  const wide = kind === "transcript" && result;

  return (
    <div className={`text-tool ${wide ? "wide stack" : "form-col"}`}>
      <div className="page-head-row">{head}
        <Link className="btn small ghost" href={`/dashboard/project/?id=${project.upload_id}`}>Open the project</Link></div>
      <div className="src-card">
        <span className="src-thumb" aria-hidden="true">{project.clips?.find((c: any) => c.thumb_url) ? <img src={project.clips.find((c: any) => c.thumb_url).thumb_url} alt="" /> : <Icon name="film" size={26} />}</span>
        <span className="src-text"><strong>{project.filename}</strong><span className="muted">{clock(project.duration_sec)} long{project.language ? ` · spoken: ${langs.languages.find((l) => l.code === project.language)?.name || project.language}` : ""}</span></span>
      </div>
      {running && <JobNote job={running} name={NAME[kind]} onCancel={cancel} />}
      {failed && <JobNote job={failed} name={NAME[kind]} onCancel={cancel} />}

      {result ? (kind === "transcript" ? <TranscriptView t={result} uploadId={project.upload_id} /> : <SummaryView s={result} />)
        : !running && <section className="panel" aria-labelledby={title}>
          {off ? <p className="notice">Video summaries aren&apos;t switched on yet. Transcripts work today: <Link href={`/dashboard/transcript/?id=${project.upload_id}`}>make a transcript</Link>.</p> : <>
            <p>{kind === "transcript" ? "Everything said in the video, with timestamps. Download it as TXT, SRT or VTT."
              : "A title, a short summary, tags and the moments worth a look, written from the video's transcript (made first if it has none)."}</p>
            <LanguageSelects langs={langs} kind={kind} source={source} target={target} onSource={setSource} onTarget={setTarget} />
            {!project.has_audio && <p className="error">This video has no sound, so there is nothing to transcribe.</p>}
            <div className="row start-row">
              <Price upload={project} />
              <button type="button" className="btn primary" disabled={busy || !me.email_verified || !project.has_audio} onClick={start}>
                {busy ? "Starting…" : kind === "transcript" ? "Make transcript" : "Make summary"}</button>
            </div>
          </>}
        </section>}
    </div>
  );
}

function TranscriptView({ t, uploadId }: { t: any; uploadId: string }) {
  const { fail } = useDash();
  const [q, setQ] = useState("");
  const rows: any[] = (t.segments || []).filter((s: any) => !q || s.text.toLowerCase().includes(q.toLowerCase()));
  return (
    <section className="panel" aria-label="Transcript">
      <div className="results-head">
        <p className="muted small">{t.segments?.length || 0} lines · language {t.language}{t.language_detected ? " (detected)" : ""}</p>
        <div className="row">
          <label className="sr-only" htmlFor="tr-find">Find in the transcript</label>
          <input id="tr-find" className="tr-find" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a word" />
          {["txt", "srt", "vtt"].map((f) => <button key={f} type="button" className="btn small ghost" onClick={() => downloadTranscript(uploadId, f).catch(fail)}>
            <Icon name="download" size={16} />{f.toUpperCase()}</button>)}
        </div>
      </div>
      {!rows.length ? <p className="muted">{q ? "No line has that word." : "No speech was found in this video."}</p>
        : <ol className="tr-lines">{rows.map((s, i) => <li key={i}><time>{clock(s.start)}</time><span>{s.text}{s.translation && <em>{s.translation}</em>}</span></li>)}</ol>}
    </section>
  );
}

function SummaryView({ s }: { s: any }) {
  return (
    <section className="panel summary" aria-label="Summary">
      {s.title && <h2>{s.title}</h2>}
      {s.summary && <p>{s.summary}</p>}
      {s.tags?.length > 0 && <ul className="chip-row" aria-label="Tags">{s.tags.map((t: string) => <li key={t} className="chip">#{t}</li>)}</ul>}
      {s.highlights?.length > 0 && <>
        <h3>Highlights</h3>
        <ol className="tr-lines">{s.highlights.map((h: any, i: number) => <li key={i}><time>{clock(h.start)}{typeof h.end === "number" ? `–${clock(h.end)}` : ""}</time><span>{h.text}</span></li>)}</ol>
      </>}
    </section>
  );
}
