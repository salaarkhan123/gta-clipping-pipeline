"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Listed, useClipOptions } from "@/lib/options";
import { tidy } from "@/lib/templates";
import { JobForm } from "./JobForm";
import { AspectSelect } from "./PreEdit";
import { useDash } from "./Shell";
import { StartRow } from "./StartRow";
import { Tabs } from "./Tabs";

// The tools in this panel. Video Finder ("find") lives in the project's Find moments tab.
export type Tool = "clips" | "reframe" | "captions" | "find";
type Here = Exclude<Tool, "find">;
const TOOL_NAMES: Record<Here, string> = { clips: "Clip Maker", reframe: "Reframe", captions: "Captions" };
export const isTool = (v: string | null): v is Tool => v === "find" || (!!v && v in TOOL_NAMES);

// Framing every request states, for the settings these tools have no control for. Reframe, Captions and Video
// Finder take the same framing options as Clip Maker, so the export size is sent wherever Clip Maker lists it.
export const framing = (listed: Listed, aspect: string) => ({ vertical: true, aspect, layout: "auto", facecam_region: "auto", zoom: 1, chat_region: "none",
  ...("resolution" in listed ? { resolution: "1080" } : {}) });
export const captionStyles = (listed: Listed): string[] => listed.caption_style?.values || ["pop"];
export const firstStyle = (listed: Listed) => ["impact", "pop"].find((s) => captionStyles(listed).includes(s)) || captionStyles(listed)[0];

function parseTime(v: string): number | null {
  if (!v.trim()) return null;
  const parts = v.trim().split(":").map(Number);
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return NaN;
  return parts.reduce((t, n) => t * 60 + n, 0);
}

// The tools for one upload. Each shows its credit price before the button that starts it.
// `open` is how Home and the template gallery hand over: the tool to show first, and a template to apply once.
export function ToolPanel({ upload, onStarted, open }: { upload: any; onStarted: (job: any) => void; open?: { tool?: Tool; template?: string } }) {
  const listed = useClipOptions();
  const [tool, setTool] = useState<Here>(open?.tool && open.tool !== "find" ? open.tool : "clips");
  return (
    <section className="panel" id="tools" aria-label="Make something from this video">
      <Tabs label="Tool" panel="tool-panel" tabs={Object.entries(TOOL_NAMES) as [Here, string][]} value={tool} onChange={setTool} />
      <div id="tool-panel" role="tabpanel" aria-label={TOOL_NAMES[tool]} className="stack-m">
        {!listed ? <p className="muted">Loading the options…</p>
          : tool === "clips" ? <JobForm upload={upload} listed={listed} onStarted={onStarted} template={open?.template} />
          : <RenderForm key={tool} tool={tool} upload={upload} listed={listed} onStarted={onStarted} />}
      </div>
    </section>
  );
}

// Reframe and Captions: one part of the video (or all of it), rendered once.
export function RenderForm({ tool, upload, listed, onStarted }: { tool: "reframe" | "captions"; upload: any; listed: Listed; onStarted: (job: any) => void }) {
  const { reloadMe, fail } = useDash();
  const [o, setO] = useState({ aspect: "9:16", caption_style: firstStyle(listed), censor: false, from: "", to: "" });
  const [starting, setStarting] = useState(false), [problem, setProblem] = useState("");
  const set = (k: string, v: any) => setO((x) => ({ ...x, [k]: v }));

  async function start() {
    setProblem("");
    const a = parseTime(o.from), b = parseTime(o.to);
    if (Number.isNaN(a) || Number.isNaN(b) || ((a === null) !== (b === null)) || (a !== null && b !== null && b - a < 1)) {
      setProblem("Enter both a start and an end time, like 12:30 and 13:10, or leave both empty for the whole video."); return;
    }
    // Reframe changes the shape and adds no captions; Captions keeps the source framing (vertical: false).
    const { aspect, ...unframed } = framing(listed, o.aspect);
    const body: any = { upload_id: upload.upload_id, options: tool === "reframe"
      ? { ...unframed, aspect, caption_style: o.caption_style, captions: false, censor: false }
      : { ...unframed, caption_style: o.caption_style, censor: o.censor, vertical: false, captions: true } };
    if (a !== null) body.segments = [{ start: a, end: b }];
    setStarting(true);
    try { onStarted(await api(tool === "reframe" ? "/v1/reframe" : "/v1/captions", { body })); await reloadMe(); } catch (e) { fail(e); } finally { setStarting(false); }
  }

  return (
    <>
      <div className="options">
        <label>From<input className="time" value={o.from} placeholder="0:00" onChange={(e) => set("from", e.target.value)} /></label>
        <label>To<input className="time" value={o.to} placeholder="end" onChange={(e) => set("to", e.target.value)} /></label>
        {tool === "reframe" && <AspectSelect listed={listed} value={o.aspect} onChange={(v) => set("aspect", v)} />}
        {tool === "captions" && <>
          <label>Caption style<select value={o.caption_style} onChange={(e) => set("caption_style", e.target.value)}>
            {captionStyles(listed).map((s) => <option key={s} value={s}>{tidy(s)}</option>)}</select></label>
          <label className="check"><input type="checkbox" checked={o.censor} onChange={(e) => set("censor", e.target.checked)} /><span>Censor swears</span></label></>}
      </div>
      {problem && <p className="error" role="alert">{problem}</p>}
      <StartRow upload={upload} label={tool === "reframe" ? "Reframe" : "Add captions"} busy={starting} onStart={start} />
    </>
  );
}
