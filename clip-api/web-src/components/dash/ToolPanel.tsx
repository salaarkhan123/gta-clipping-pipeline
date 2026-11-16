"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useDash } from "./Shell";

type Tool = "clips" | "reframe" | "captions" | "find";
const TOOL_NAMES: Record<Tool, string> = { clips: "Clip Maker", reframe: "Reframe", captions: "Captions", find: "Video Finder" };

function parseTime(v: string): number | null {
  if (!v.trim()) return null;
  const parts = v.trim().split(":").map(Number);
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return NaN;
  return parts.reduce((t, n) => t * 60 + n, 0);
}

// The four tools for one upload. Shows the credit price before the user starts anything.
export function ToolPanel({ upload, onStarted }: { upload: any; onStarted: (job: any) => void }) {
  const { me, reloadMe, fail } = useDash();
  const [tool, setTool] = useState<Tool>("clips");
  const [o, setO] = useState({ max_clips: 3, clip_length: 30, aspect: "9:16", caption_style: "pop", captions: true,
    censor: false, chat_region: "none", query: "", from: "", to: "" });
  const [starting, setStarting] = useState(false), [problem, setProblem] = useState("");
  const set = (k: string, v: any) => setO((x) => ({ ...x, [k]: v }));

  async function start() {
    setProblem("");
    const layout = { aspect: o.aspect, caption_style: o.caption_style, censor: o.censor };
    let path = "/v1/clips", body: any;
    if (tool === "clips") {
      body = { upload_id: upload.upload_id, options: { ...layout, captions: o.captions, chat_region: o.chat_region,
        max_clips: o.max_clips, clip_length: o.clip_length } };
    } else if (tool === "find") {
      if (!o.query.trim()) { setProblem("Type what you're looking for first."); return; }
      path = "/v1/find";
      body = { upload_id: upload.upload_id, query: o.query.trim(), clip_length: o.clip_length, options: { ...layout, captions: o.captions } };
    } else {
      const a = parseTime(o.from), b = parseTime(o.to);
      if (Number.isNaN(a) || Number.isNaN(b) || ((a === null) !== (b === null)) || (a !== null && b !== null && b - a < 1)) {
        setProblem("Enter both a start and an end time, like 12:30 and 13:10, or leave both empty for the whole video."); return;
      }
      path = tool === "reframe" ? "/v1/reframe" : "/v1/captions";
      body = { upload_id: upload.upload_id, options: tool === "reframe" ? { ...layout, captions: false, censor: false }
        : { caption_style: o.caption_style, censor: o.censor, vertical: false } };
      if (a !== null) body.segments = [{ start: a, end: b }];
    }
    setStarting(true);
    try { onStarted(await api(path, { body })); await reloadMe(); } catch (e) { fail(e); } finally { setStarting(false); }
  }

  return (
    <section className="panel" aria-label="Make something from this video">
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
        {tool !== "reframe" && (tool === "captions" || o.captions) && <label className="check"><input type="checkbox"
          checked={o.censor} onChange={(e) => set("censor", e.target.checked)} /><span>Censor swears</span></label>}
      </div>
      {problem && <p className="error" role="alert">{problem}</p>}
      <div className="row">
        <button className="btn primary" disabled={starting || !me.email_verified} onClick={start}>
          {starting ? "Starting…" : tool === "clips" ? "Make clips" : tool === "find" ? "Find it" : tool === "reframe" ? "Reframe" : "Add captions"}</button>
        <p className="muted">{upload.analyzed
          ? "This video is already paid for. You only use credits for the minutes rendered."
          : tool === "clips" || tool === "find" ? `Uses ${upload.credits_required} credit${upload.credits_required === 1 ? "" : "s"} (one per minute of video).`
          : `Uses one credit per minute rendered, up to ${upload.credits_required}.`}</p>
      </div>
    </section>
  );
}
