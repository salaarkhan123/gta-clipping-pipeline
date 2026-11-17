"use client";
import { useState } from "react";
import { api, clock } from "@/lib/api";
import { inside, useClipOptions } from "@/lib/options";
import { tidy } from "@/lib/templates";
import { JobNote } from "./JobNote";
import { AspectSelect } from "./PreEdit";
import { useDash } from "./Shell";
import { StartRow } from "./StartRow";
import { captionStyles, firstStyle, framing } from "./ToolPanel";

// Find moments: Video Finder for this one video. Type what was said or shown; each search lists where it was
// found and cuts a clip of each match into the Clips tab.
export function FindPanel({ upload, jobs, finds, onStarted, onCancel }: { upload: any; jobs: any[]; finds: Record<string, any>;
  onStarted: (job: any) => void; onCancel: (jobId: string) => void }) {
  const { reloadMe, fail } = useDash();
  const listed = useClipOptions();
  const [o, setO] = useState<{ query: string; clip_length: number; aspect: string; caption_style: string | null; captions: boolean; censor: boolean }>(
    { query: "", clip_length: 30, aspect: "9:16", caption_style: null, captions: true, censor: false });
  const [starting, setStarting] = useState(false), [problem, setProblem] = useState("");
  const set = (k: string, v: any) => setO((x) => ({ ...x, [k]: v }));
  if (!listed) return <p className="muted">Loading the options…</p>;
  const style = o.caption_style || firstStyle(listed);

  async function start() {
    if (!o.query.trim()) { setProblem("Type what you're looking for first."); return; }
    setProblem("");
    setStarting(true);
    try {
      onStarted(await api("/v1/find", { body: { upload_id: upload.upload_id, query: o.query.trim(), mode: "auto", max_results: 5, make_clips: true,
        clip_length: o.clip_length, options: { ...framing(listed!, o.aspect), caption_style: style, censor: o.censor, captions: o.captions } } }));
      await reloadMe();
    } catch (e) { fail(e); } finally { setStarting(false); }
  }

  return (
    <div className="stack-m">
      <form className="panel" onSubmit={(e) => { e.preventDefault(); start(); }}>
        <div className="options">
          <label className="grow">What are you looking for?
            <input value={o.query} maxLength={200} placeholder="police chase, or something that was said" onChange={(e) => set("query", e.target.value)} /></label>
          <label>Clip length<select value={o.clip_length} onChange={(e) => set("clip_length", +e.target.value)}>
            {inside(listed.clip_length, [15, 20, 30, 40, 45, 60]).map((n) => <option key={n} value={n}>{n} seconds</option>)}</select></label>
          <AspectSelect listed={listed} value={o.aspect} onChange={(v) => set("aspect", v)} />
          <label>Caption style<select value={style} onChange={(e) => set("caption_style", e.target.value)}>
            {captionStyles(listed).map((s) => <option key={s} value={s}>{tidy(s)}</option>)}</select></label>
          <label className="check"><input type="checkbox" checked={o.captions} onChange={(e) => set("captions", e.target.checked)} /><span>Captions</span></label>
          {o.captions && <label className="check"><input type="checkbox" checked={o.censor} onChange={(e) => set("censor", e.target.checked)} /><span>Censor swears</span></label>}
        </div>
        {problem && <p className="error" role="alert">{problem}</p>}
        <StartRow upload={upload} label="Find it" busy={starting} perMinute />
      </form>
      {!jobs.length ? <p className="muted">Nothing searched yet. Matches show up here, and a clip of each one lands in the Clips tab.</p>
        : jobs.map((j) => (
          <JobNote key={j.job_id} job={j} name={typeof j.options?.query === "string" ? `Video Finder: “${j.options.query}”` : "Video Finder"} onCancel={onCancel}>
            {finds[j.job_id]?.matches && (finds[j.job_id].matches.length
              ? <ul className="matches">{finds[j.job_id].matches.map((m: any, i: number) => (
                  <li key={i}><b>{clock(m.start)}</b> {m.kind === "visual" ? "On screen" : "Said"}: {m.text}</li>))}</ul>
              : <p className="muted">No matches for “{finds[j.job_id].query}”. Try different words.</p>)}
          </JobNote>))}
    </div>
  );
}
