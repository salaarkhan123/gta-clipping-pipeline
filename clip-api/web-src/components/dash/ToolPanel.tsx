"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useDash } from "./Shell";
import { Tabs } from "./Tabs";

export type Tool = "clips" | "reframe" | "captions" | "find";
const TOOL_NAMES: Record<Tool, string> = { clips: "Clip Maker", reframe: "Reframe", captions: "Captions", find: "Video Finder" };
export const isTool = (v: string | null): v is Tool => !!v && v in TOOL_NAMES;

// What a template may fill in, and the editing switches (all on by default, like the API).
const FORM_KEYS = ["clip_length", "caption_style", "tighten", "punch_zoom", "flash_forward", "hook_overlay"];
const EDITS: [string, string][] = [["tighten", "Cut dead air and filler words"], ["punch_zoom", "Punch-in zoom on big moments"],
  ["flash_forward", "Open on the best moment"], ["hook_overlay", "On-screen hook text"]];

function parseTime(v: string): number | null {
  if (!v.trim()) return null;
  const parts = v.trim().split(":").map(Number);
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return NaN;
  return parts.reduce((t, n) => t * 60 + n, 0);
}

// The four tools for one upload. Shows the credit price before the user starts anything.
// `open` is how Home and the template gallery hand over: the tool to show first, and a template to apply once.
export function ToolPanel({ upload, onStarted, open }: { upload: any; onStarted: (job: any) => void; open?: { tool?: Tool; template?: string } }) {
  const { me, reloadMe, fail } = useDash();
  const [tool, setTool] = useState<Tool>(open?.tool || "clips");
  const [o, setO] = useState({ max_clips: 3, clip_length: 30, aspect: "9:16", caption_style: "pop", captions: true,
    censor: false, chat_region: "none", query: "", from: "", to: "",
    tighten: true, punch_zoom: true, flash_forward: true, hook_overlay: true, template: "" });
  const [templates, setTemplates] = useState<any[]>([]);
  const [starting, setStarting] = useState(false), [problem, setProblem] = useState("");
  const set = (k: string, v: any) => setO((x) => ({ ...x, [k]: v }));

  // Choosing a template fills in its settings; every one of them can still be changed before starting.
  function pickTemplate(id: string, from = templates) {
    const chosen = from.find((x) => x.id === id);
    const fill: Record<string, any> = {};
    for (const k of FORM_KEYS) if (chosen?.options && k in chosen.options) fill[k] = chosen.options[k];
    setO((x) => ({ ...x, ...fill, template: chosen ? id : "" }));
  }
  useEffect(() => {
    api("/v1/templates", { auth: false }).then((r) => {
      setTemplates(r.templates);
      if (open?.template) pickTemplate(open.template, r.templates);     // "Use template" in the gallery
    }).catch(() => {});
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const template = templates.find((x) => x.id === o.template);

  async function start() {
    setProblem("");
    // Every request states every setting it relies on, including the ones this panel has no control for, so a
    // change to the API's defaults can never change what the dashboard makes. Only names the API accepts are sent.
    const frame = { vertical: true, aspect: o.aspect, layout: "auto", facecam_region: "auto", zoom: 1, chat_region: "none" };
    const text = { caption_style: o.caption_style, censor: o.censor };
    let path = "/v1/clips", body: any;
    if (tool === "clips") {
      body = { upload_id: upload.upload_id, options: { ...frame, ...text, captions: o.captions, chat_region: o.chat_region,
        max_clips: o.max_clips, clip_length: o.clip_length, tighten: o.tighten, punch_zoom: o.punch_zoom,
        flash_forward: o.flash_forward, hook_overlay: o.hook_overlay,
        ...(template ? { template: template.id, layout: template.options?.layout ?? "auto" } : {}) } };
    } else if (tool === "find") {
      if (!o.query.trim()) { setProblem("Type what you're looking for first."); return; }
      path = "/v1/find";
      body = { upload_id: upload.upload_id, query: o.query.trim(), mode: "auto", max_results: 5, make_clips: true,
        clip_length: o.clip_length, options: { ...frame, ...text, captions: o.captions } };
    } else {
      const a = parseTime(o.from), b = parseTime(o.to);
      if (Number.isNaN(a) || Number.isNaN(b) || ((a === null) !== (b === null)) || (a !== null && b !== null && b - a < 1)) {
        setProblem("Enter both a start and an end time, like 12:30 and 13:10, or leave both empty for the whole video."); return;
      }
      path = tool === "reframe" ? "/v1/reframe" : "/v1/captions";
      // Reframe changes the shape and adds no captions; Captions keeps the source framing (vertical: false).
      const { aspect, ...unframed } = frame;
      body = { upload_id: upload.upload_id, options: tool === "reframe" ? { ...frame, ...text, captions: false, censor: false }
        : { ...unframed, ...text, vertical: false, captions: true } };
      if (a !== null) body.segments = [{ start: a, end: b }];
    }
    setStarting(true);
    try { onStarted(await api(path, { body })); await reloadMe(); } catch (e) { fail(e); } finally { setStarting(false); }
  }

  return (
    <section className="panel" id="tools" aria-label="Make something from this video">
      <Tabs label="Tool" tabs={Object.entries(TOOL_NAMES) as [Tool, string][]} value={tool} onChange={setTool} />
      {tool === "clips" && templates.length > 0 && <div className="options">
        <label className="grow">Template
          <select value={o.template} onChange={(e) => pickTemplate(e.target.value)}>
            <option value="">No template</option>
            {templates.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select></label>
        <p className="muted grow">{template ? template.description : "A template sets the options below for one kind of clip. You can still change any of them."}</p>
      </div>}
      <div className="options">
        {tool === "find" && <label className="grow">What are you looking for?
          <input value={o.query} placeholder="police chase, or something that was said" onChange={(e) => set("query", e.target.value)} /></label>}
        {tool === "clips" && <label>Clips<select value={o.max_clips} onChange={(e) => set("max_clips", +e.target.value)}>
          {[1, 2, 3, 5, 8, 10].map((n) => <option key={n}>{n}</option>)}</select></label>}
        {(tool === "clips" || tool === "find") && <label>Length<select value={o.clip_length} onChange={(e) => set("clip_length", +e.target.value)}>
          {[15, 20, 30, 40, 45, 60].map((n) => <option key={n} value={n}>{n} s</option>)}</select></label>}
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
      {tool === "clips" && <fieldset className="options edits">
        <legend>Editing</legend>
        {EDITS.map(([k, name]) => (
          <label key={k} className="check"><input type="checkbox" checked={(o as any)[k]}
            onChange={(e) => set(k, e.target.checked)} /><span>{name}</span></label>))}
        <p className="muted">The opening and the on-screen hook are added to clips the AI has rated.</p>
      </fieldset>}
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
