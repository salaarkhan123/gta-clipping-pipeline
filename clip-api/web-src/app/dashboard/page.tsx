"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Logo, Stars } from "@/components/Chrome";
import { DropZone } from "@/components/DropZone";
import { API, api, ApiError, clock, getToken, setToken, takePendingFile, uploadFile } from "@/lib/api";

type Tool = "clips" | "reframe" | "captions" | "find";
const TOOL_NAMES: Record<Tool, string> = { clips: "Clip Maker", reframe: "Reframe", captions: "Captions", find: "Video Finder" };
const TOOL_OF_JOB: Record<string, string> = { clips: "Clip Maker", render: "Reframe / Captions", find: "Video Finder" };
const STAGES: Record<string, string> = {
  starting: "Starting", downloading: "Getting your video", probing: "Reading the video", chat_motion: "Watching chat",
  audio: "Listening for reactions", transcribing: "Transcribing speech", indexing_frames: "Looking through the frames",
  searching: "Searching", rendering: "Rendering clips", writing_titles: "Writing titles", uploading: "Saving clips", done: "Done",
};
const active = (j: any) => j.status === "QUEUED" || j.status === "RUNNING";

function parseTime(v: string): number | null {
  if (!v.trim()) return null;
  const parts = v.trim().split(":").map(Number);
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return NaN;
  return parts.reduce((t, n) => t * 60 + n, 0);
}

export default function Dashboard() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [uploads, setUploads] = useState<any[]>([]), [jobs, setJobs] = useState<any[]>([]);
  const [details, setDetails] = useState<Record<string, any>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [uploadId, setUploadId] = useState(""), [tool, setTool] = useState<Tool>("clips");
  const [up, setUp] = useState<{ name: string; pct: number } | null>(null);
  const [o, setO] = useState({ max_clips: 3, clip_length: 30, aspect: "9:16", caption_style: "pop", captions: true,
    chat_region: "none", query: "", from: "", to: "" });
  const [error, setError] = useState<{ text: string; upgrade?: boolean } | null>(null), [notice, setNotice] = useState("");
  const [starting, setStarting] = useState(false);
  const abort = useRef<(() => void) | null>(null);
  const seen = useRef<Record<string, string>>({});

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { router.push("/login/"); return; }
    setError({ text: e instanceof Error ? e.message : "Something went wrong.", upgrade: e instanceof ApiError && e.code === "insufficient_credits" });
  };

  const loadJob = useCallback(async (id: string) => {
    try { const d = await api(`/v1/jobs/${id}`); setDetails((x) => ({ ...x, [id]: d })); } catch {}
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [m, u, j] = await Promise.all([api("/v1/me"), api("/v1/uploads"), api("/v1/jobs")]);
      setMe(m); setUploads(u.uploads); setJobs(j.jobs);
      setUploadId((cur) => cur || u.uploads[0]?.upload_id || "");
      for (const job of j.jobs as any[]) {            // a job that just finished: fetch its clips and show them
        const was = seen.current[job.job_id];
        if (was && was !== job.status && !active(job)) { loadJob(job.job_id); if (job.status === "SUCCEEDED") setOpen(job.job_id); }
        seen.current[job.job_id] = job.status;
      }
    } catch (e) { fail(e); }
  }, [loadJob]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function startUpload(file: File) {
    setError(null);
    setUp({ name: file.name, pct: 0 });
    const { promise, abort: a } = uploadFile(file, (f) => setUp({ name: file.name, pct: Math.round(f * 100) }));
    abort.current = a;
    try {
      const u = await promise;
      setUploads((list) => [u, ...list]); setUploadId(u.upload_id);
    } catch (e) { if (!(e instanceof ApiError && e.code === "aborted")) fail(e); }
    finally { setUp(null); abort.current = null; }
  }

  useEffect(() => {
    if (!getToken()) { router.push("/login/"); return; }
    if (new URLSearchParams(window.location.search).get("purchase") === "success")
      setNotice("Payment received. New credits show up here within a minute.");
    refresh();
    const f = takePendingFile();
    if (f) startUpload(f);
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const anyActive = jobs.some(active);
  useEffect(() => {
    if (!anyActive && !notice) return;
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [anyActive, notice, refresh]);

  const upload = uploads.find((u) => u.upload_id === uploadId);

  async function start() {
    if (!upload) return;
    setError(null);
    const layout = { aspect: o.aspect, caption_style: o.caption_style };
    let path = "/v1/clips", body: any;
    if (tool === "clips") {
      body = { upload_id: upload.upload_id, options: { ...layout, captions: o.captions, chat_region: o.chat_region,
        max_clips: o.max_clips, clip_length: o.clip_length } };
    } else if (tool === "find") {
      if (!o.query.trim()) { setError({ text: "Type what you're looking for first." }); return; }
      path = "/v1/find";
      body = { upload_id: upload.upload_id, query: o.query.trim(), clip_length: o.clip_length, options: { ...layout, captions: o.captions } };
    } else {
      const a = parseTime(o.from), b = parseTime(o.to);
      if (Number.isNaN(a) || Number.isNaN(b) || ((a === null) !== (b === null)) || (a !== null && b !== null && b - a < 1)) {
        setError({ text: "Enter both a start and an end time, like 12:30 and 13:10, or leave both empty for the whole video." }); return;
      }
      path = tool === "reframe" ? "/v1/reframe" : "/v1/captions";
      body = { upload_id: upload.upload_id, options: tool === "reframe" ? { ...layout, captions: false } : { caption_style: o.caption_style, vertical: false } };
      if (a !== null) body.segments = [{ start: a, end: b }];
    }
    setStarting(true);
    try {
      const job = await api(path, { body });
      seen.current[job.job_id] = job.status;
      setJobs((list) => [job, ...list]);
      const m = await api("/v1/me"); setMe(m);
    } catch (e) { fail(e); } finally { setStarting(false); }
  }

  async function toggle(id: string) {
    if (open === id) { setOpen(null); return; }
    setOpen(id);
    if (!details[id]) loadJob(id);
  }

  async function act(fn: () => Promise<any>) { try { await fn(); await refresh(); } catch (e) { fail(e); } }

  async function subtitles(clipId: string, format: string) {
    try {
      const res = await fetch(`${API}/v1/clips/${clipId}/subtitles?format=${format}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) throw new ApiError(res.status, "error", "Couldn't get the subtitles for this clip.");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob()); a.download = `${clipId}.${format}`; a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { fail(e); }
  }

  async function keep(jobId: string, clip: any, kept: boolean) {
    try {
      await api(`/v1/clips/${clip.id}/feedback`, { body: { kept } });
      setDetails((x) => ({ ...x, [jobId]: { ...x[jobId], clips: x[jobId].clips.map((c: any) => (c.id === clip.id ? { ...c, kept } : c)) } }));
    } catch (e) { fail(e); }
  }

  if (!me) return <main className="dash"><p className="muted">Loading…</p></main>;
  const set = (k: string, v: any) => setO((x) => ({ ...x, [k]: v }));

  return (
    <>
      <header className="nav dash-nav">
        <Logo />
        <nav>
          <span className="credits"><b>{me.credits.toLocaleString()}</b> credits</span>
          <Link href="/pricing/" className="btn small primary">{me.plan === "free" ? "Upgrade" : "Add credits"}</Link>
          <Account me={me} onError={fail} />
        </nav>
      </header>
      <main className="dash">
        {!me.email_verified && <p className="notice">Confirm your email to start making clips. We sent a link to {me.email}.{" "}
          <button className="link" onClick={() => act(() => api("/v1/auth/resend-verification", { body: {} }))}>Send it again</button></p>}
        {notice && <p className="notice" role="status">{notice} <button className="link" onClick={() => setNotice("")}>Dismiss</button></p>}
        {error && <p className="error" role="alert">{error.text} {error.upgrade && <Link href="/pricing/">Get more credits</Link>}{" "}
          <button className="link" onClick={() => setError(null)}>Dismiss</button></p>}

        <section className="panel">
          {up ? (
            <div className="uploading">
              <p>Uploading {up.name}</p>
              <progress max={100} value={up.pct} />
              <p className="muted">{up.pct}% <button className="link" onClick={() => abort.current?.()}>Cancel</button></p>
            </div>
          ) : !uploads.length ? <DropZone onFile={startUpload} /> : (
            <>
              <div className="row">
                <label className="grow">Video
                  <select value={uploadId} onChange={(e) => setUploadId(e.target.value)}>
                    {uploads.map((u) => <option key={u.upload_id} value={u.upload_id}>{u.filename} ({clock(u.duration_sec)})</option>)}
                  </select></label>
                <DropZone onFile={startUpload} compact />
              </div>
              <div className="tabs" role="tablist">
                {(Object.keys(TOOL_NAMES) as Tool[]).map((t) => (
                  <button key={t} role="tab" aria-selected={tool === t} className={tool === t ? "on" : ""} onClick={() => setTool(t)}>{TOOL_NAMES[t]}</button>))}
              </div>
              <div className="options">
                {tool === "find" && <label className="grow">What are you looking for?
                  <input value={o.query} placeholder="police chase, or something that was said" onChange={(e) => set("query", e.target.value)} /></label>}
                {tool === "clips" && <label>Clips<select value={o.max_clips} onChange={(e) => set("max_clips", +e.target.value)}>
                  {[1, 2, 3, 5, 8, 10].map((n) => <option key={n}>{n}</option>)}</select></label>}
                {(tool === "clips" || tool === "find") && <label>Length<select value={o.clip_length} onChange={(e) => set("clip_length", +e.target.value)}>
                  {[15, 30, 45, 60].map((n) => <option key={n} value={n}>{n} s</option>)}</select></label>}
                {(tool === "reframe" || tool === "captions") && <>
                  <label>From<input className="time" value={o.from} placeholder="0:00" onChange={(e) => set("from", e.target.value)} /></label>
                  <label>To<input className="time" value={o.to} placeholder="end" onChange={(e) => set("to", e.target.value)} /></label></>}
                {tool !== "captions" && <label>Shape<select value={o.aspect} onChange={(e) => set("aspect", e.target.value)}>
                  <option value="9:16">9:16 vertical</option><option value="4:5">4:5 portrait</option>
                  <option value="1:1">1:1 square</option><option value="16:9">16:9 wide</option></select></label>}
                {tool !== "reframe" && <label>Caption style<select value={o.caption_style} onChange={(e) => set("caption_style", e.target.value)}>
                  {["pop", "bold", "neon", "boxed", "clean"].map((s) => <option key={s}>{s}</option>)}</select></label>}
                {tool === "clips" && <label>Chat on screen<select value={o.chat_region} onChange={(e) => set("chat_region", e.target.value)}>
                  <option value="none">Not shown</option><option value="top-right">Top right</option><option value="top-left">Top left</option>
                  <option value="top-center">Top centre</option><option value="bottom-right">Bottom right</option><option value="bottom-left">Bottom left</option></select></label>}
                {(tool === "clips" || tool === "find") && <label className="check"><input type="checkbox" checked={o.captions}
                  onChange={(e) => set("captions", e.target.checked)} /><span>Captions</span></label>}
              </div>
              <div className="row">
                <button className="btn primary" disabled={starting || !upload || !me.email_verified} onClick={start}>
                  {starting ? "Starting…" : tool === "clips" ? "Make clips" : tool === "find" ? "Find it" : tool === "reframe" ? "Reframe" : "Add captions"}</button>
                {upload && <p className="muted">{upload.analyzed
                  ? "This video is already paid for. You only use credits for the minutes rendered."
                  : tool === "clips" || tool === "find" ? `Uses ${upload.credits_required} credit${upload.credits_required === 1 ? "" : "s"} (one per minute of video).`
                  : `Uses one credit per minute rendered, up to ${upload.credits_required}.`}</p>}
              </div>
            </>
          )}
        </section>

        <section>
          <h2>Your jobs</h2>
          {!jobs.length && <p className="muted">Nothing yet. Upload a video and your clips will show up here.</p>}
          {jobs.map((j) => {
            const d = details[j.job_id];
            return (
              <article key={j.job_id} className={`job ${j.status.toLowerCase()}`}>
                <button className="job-head" aria-expanded={open === j.job_id} onClick={() => toggle(j.job_id)}>
                  <strong>{TOOL_OF_JOB[j.tool] || j.tool}</strong>
                  <span className="muted">{uploads.find((u) => u.upload_id === j.upload_id)?.filename || "video"}</span>
                  <span className="status">{active(j) ? `${STAGES[j.stage] || "Queued"} ${j.progress}%`
                    : j.status === "SUCCEEDED" ? `Done, ${j.credits_charged} credit${j.credits_charged === 1 ? "" : "s"}`
                    : j.status === "FAILED" ? "Failed, credits refunded" : "Cancelled"}</span>
                </button>
                {active(j) && <><progress max={100} value={j.progress} />
                  <button className="link" onClick={() => act(() => api(`/v1/jobs/${j.job_id}/cancel`, { body: {} }))}>Cancel</button></>}
                {open === j.job_id && !active(j) && (
                  <div className="job-body">
                    {j.error && <p className="error">{j.error.message}</p>}
                    {!d && <p className="muted">Loading clips…</p>}
                    {d?.result?.matches && (d.result.matches.length
                      ? <ul className="matches">{d.result.matches.map((m: any, i: number) => (
                          <li key={i}><b>{clock(m.start)}</b> {m.kind === "visual" ? "On screen" : "Said"}: {m.text}</li>))}</ul>
                      : <p className="muted">No matches for “{d.result.query}”. Try different words.</p>)}
                    {d && j.status === "SUCCEEDED" && !d.clips.length && !d.result?.matches && <p className="muted">These clips have been deleted (files are kept for 7 days).</p>}
                    <div className="clips">
                      {d?.clips?.map((c: any) => (
                        <figure key={c.id} className={`clip ${c.kept === false ? "dropped" : ""}`}>
                          <video controls preload="none" poster={c.thumb_url || undefined} src={c.video_url} />
                          <figcaption>
                            <strong>{c.title || `Clip ${c.index}`}</strong>
                            {c.virality && <Stars score={c.virality.score} />}
                            <span className="muted">{clock(c.start_sec)} to {clock(c.end_sec)}</span>
                            {c.description && <p>{c.description}</p>}
                            {c.hashtags?.length > 0 && <p className="tags">{c.hashtags.map((t: string) => `#${t}`).join(" ")}</p>}
                            <div className="clip-actions">
                              <a className="btn small primary" href={c.video_url} download>Download</a>
                              {c.captions_url && <button className="btn small ghost" onClick={() => subtitles(c.id, "srt")}>Subtitles</button>}
                              <button className="btn small ghost" aria-pressed={c.kept === true} onClick={() => keep(j.job_id, c, true)}>Keep</button>
                              <button className="btn small ghost" aria-pressed={c.kept === false} onClick={() => keep(j.job_id, c, false)}>Discard</button>
                            </div>
                          </figcaption>
                        </figure>))}
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </section>
      </main>
    </>
  );
}

function Account({ me, onError }: { me: any; onError: (e: unknown) => void }) {
  const router = useRouter();
  const [keys, setKeys] = useState<any[] | null>(null), [fresh, setFresh] = useState("");
  const load = () => api("/v1/keys").then((r) => setKeys(r.keys)).catch(onError);
  return (
    <details className="account" onToggle={(e) => (e.target as HTMLDetailsElement).open && !keys && load()}>
      <summary>Account</summary>
      <div className="account-menu">
        <p><b>{me.email}</b><br /><span className="muted">{me.plan[0].toUpperCase() + me.plan.slice(1)} plan</span></p>
        {me.plan !== "free" && <button className="link" onClick={() => api("/v1/billing/portal", { body: {} })
          .then((r) => { window.location.href = r.portal_url; }).catch(onError)}>Manage billing</button>}
        <h3>API keys</h3>
        {fresh && <p className="notice">Copy this key now. It won't be shown again.<br /><code>{fresh}</code></p>}
        {keys?.map((k) => (<p key={k.id} className="key"><code>{k.prefix}…</code> {k.name}
          <button className="link" onClick={() => api(`/v1/keys/${k.id}`, { method: "DELETE" }).then(load).catch(onError)}>Revoke</button></p>))}
        <button className="link" onClick={() => api("/v1/keys", { body: { name: "dashboard" } }).then((r) => { setFresh(r.key); load(); }).catch(onError)}>Create a key</button>
        <button className="link" onClick={() => { setToken(null); router.push("/"); }}>Log out</button>
      </div>
    </details>
  );
}
