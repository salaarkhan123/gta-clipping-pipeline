"use client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { addCut, cutsInside, dropDraft, Edit, EditWord, forApi, inCut, keptLength, Line, linesOf, loadDraft, loadWords, MIN_LENGTH, removeSpan, round,
  loadEditWords, saveDraft, saveOnClip, sameEdit, sourceTime, Span, startEdit, Word } from "@/lib/edit";
import { isEditWordList, wordEditReady } from "@/lib/wordEdits";
import { CaptionLook, CaptionLookControls, CaptionOverlay, captionAt, tidyLook, WordFace, WordMenu } from "./editor/Words";
import { creditWords, exportBody, followJob, useQuote } from "@/lib/exporting";
import { layoutsFor, Listed, onlyListed } from "@/lib/options";
import { EXPORT, EXPORT_QUOTE, Routes } from "@/lib/routes";
import { hasPanels, layoutChoices, layoutName, Look, LOOK_KEYS, startLook, tidy } from "@/lib/templates";
import { nameOf } from "./ClipCard";
import { Icon, IconName, Soon } from "./Icon";
import { Custom, Section } from "./PreEdit";
import { useDash } from "./Shell";
import { QuoteLine } from "./StartRow";
import { Tabs } from "./Tabs";

// Tenths of a second: "1:02.4".
export const stamp = (s: number) => {
  const t = Math.max(0, Math.round(s * 10) / 10), m = Math.floor(t / 60), sec = (t - m * 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
};
function parseStamp(v: string): number | null {
  const parts = v.trim().split(":");
  if (!v.trim() || parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) return null;
  return parts.map(Number).reduce((t, n) => t * 60 + n, 0);
}
const AUTOSAVE_MS = 3000;
const HOOK_MAX = 80;
const POSITION_NAMES: Record<string, string> = { beginning: "At the start", end: "At the end" };
const ASPECT_NAMES: Record<string, string> = { "9:16": "9:16", "4:5": "4:5", "1:1": "1:1", "16:9": "16:9" };

// The look a clip was made with: the dashboard's starting look, then whatever its run stated.
export function lookOfJob(listed: Listed, job: any): Record<string, unknown> {
  const o = job?.options || {}, look: Record<string, unknown> = { ...startLook(listed) };
  for (const k of [...LOOK_KEYS, "hook_style", "hook_position"]) if (k in o && o[k] !== undefined) look[k] = o[k];
  return onlyListed(listed, look);
}

// The tool rail on the right of the editor. Each built tool opens its panel next to the rail; `needs` is the
// option GET /v1/options must list for it to show. The tools after them are planned and never open anything.
type Tool = "layout" | "captions" | "hook" | "edits";
const TOOLS: { id: Tool; icon: IconName; label: string; needs: string[]; sections: Section[]; title: string }[] = [
  { id: "layout", icon: "reframe", label: "Layout", needs: ["vertical", "aspect", "layout"], sections: ["resize"], title: "Shape and layout" },
  { id: "captions", icon: "captions", label: "Captions", needs: ["captions"], sections: ["subtitles", "emoji"], title: "Captions" },
  { id: "hook", icon: "hook", label: "Hook", needs: ["hook_overlay"], sections: ["hook"], title: "Hook" },
  { id: "edits", icon: "bolt", label: "Edits", needs: ["tighten"], sections: ["tighten"], title: "Auto edits" },
];
const PLANNED: [IconName, string][] = [["image", "AI B-roll"], ["music", "Music"], ["transitions", "Transitions"], ["mic", "AI voice hook"], ["send", "Publish"]];

const RAIL_ITEM = "grid w-full justify-items-center gap-1 rounded-12 border-0 bg-transparent px-1 py-2 text-center font-body text-[11.5px] font-medium leading-[1.2] mid:w-[84px] mid:flex-none";
const PILL_SELECT = "h-9 cursor-pointer rounded-full border border-solid border-line bg-card-2 py-0 pl-3 pr-8 text-[13px] font-medium narrow:h-10";
const ICON_BTN = "grid h-9 w-9 flex-none cursor-pointer place-items-center rounded-full border-0 bg-transparent text-soft enabled:hover:bg-chip-hover enabled:hover:text-text disabled:cursor-default disabled:opacity-40 narrow:h-10 narrow:w-10";

type Tab = "transcript" | "captions";
// The editor for one clip, laid out like a desktop editor: what was said on the left, the preview in the
// middle, the tool rail on the right and the timeline along the bottom. Everything it changes is kept in
// `edit`; the draft is kept in this browser until the edit is saved on the clip or rendered.
export function Editor({ project, clip, job, listed, known, number, onClip }: { project: any; clip: any; job: any; listed: Listed; known: Routes;
  number?: number; onClip: (c: any) => void }) {
  const { fail, reloadMe } = useDash();
  const first = useMemo(() => startEdit(clip, lookOfJob(listed, job)), [clip.id]);    // eslint-disable-line react-hooks/exhaustive-deps
  const [base, setBase] = useState<Edit>(first);                 // what is saved (or the clip as it was made)
  const [edit, setEdit] = useState<Edit>(first);
  const [restored, setRestored] = useState<number | null>(null), [draftAt, setDraftAt] = useState<number | null>(null);
  const [words, setWords] = useState<Word[] | null>(null), [wordsProblem, setWordsProblem] = useState("");
  const [apiWords, setApiWords] = useState<EditWord[] | null>(null);            // GET /v1/clips/{id}/words (#215)
  const [wordEditsOn, setWordEditsOn] = useState(false);                        // EditWord path ready (emoji/highlight/split)
  const [tab, setTab] = useState<Tab>("transcript");
  const [tool, setTool] = useState<Tool | null>(null);
  const [view, setView] = useState<"edit" | "file">("edit");
  const [t, setT] = useState(first.trim.start), [playing, setPlaying] = useState(false);
  const [sel, setSel] = useState<{ a: number; b: number } | null>(null);
  const [saving, setSaving] = useState(false), [saidSaved, setSaidSaved] = useState("");
  const [confirm, setConfirm] = useState(false), [render, setRender] = useState<{ job?: any; problem?: string; done?: boolean } | null>(null);
  const video = useRef<HTMLVideoElement>(null), anchor = useRef<number | null>(null);
  const latest = useRef(edit); latest.current = edit;

  // A draft from an earlier visit comes back.
  useEffect(() => {
    const d = loadDraft(clip.id);
    if (d && !sameEdit(d.edit, first)) { setEdit({ ...first, ...d.edit, options: { ...first.options, ...d.edit.options } }); setRestored(d.at); setDraftAt(d.at); }
  }, [clip.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Autosave: every few seconds the draft is written when it changed; an edit back to the saved state removes it.
  const baseRef = useRef(base); baseRef.current = base;
  useEffect(() => {
    let last = "";
    const id = setInterval(() => {
      const now = JSON.stringify(latest.current);
      if (now === last) return;
      last = now;
      if (sameEdit(latest.current, baseRef.current)) { dropDraft(clip.id); setDraftAt(null); }
      else setDraftAt(saveDraft(clip.id, latest.current));
    }, AUTOSAVE_MS);
    return () => clearInterval(id);
  }, [clip.id]);

  useEffect(() => {
    let on = true;
    setWordEditsOn(false); setApiWords(null);
    // Always try GET /words (EditWord). A live route enables emoji/highlight/split even when OpenAPI probe missed.
    const takeEditWords = (list: EditWord[]) => {
      if (!on) return;
      setApiWords(list); setWords(list); setWordEditsOn(isEditWordList(list)); setWordsProblem("");
    };
    const fallback = () => loadWords(clip).then((w) => { if (on) { setWords(w); setWordEditsOn(false); } })
      .catch((e) => { if (on) { setWords([]); setWordEditsOn(false); setWordsProblem(e.message); } });
    loadEditWords(clip.id).then((r) => takeEditWords(r.words)).catch(() => fallback());
    return () => { on = false; };
  }, [clip.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  const set = (change: Partial<Edit>) => setEdit((e) => ({ ...e, ...change }));
  const look = { ...startLook(listed), ...edit.options } as Look & Record<string, any>;
  const onLook = (change: Partial<Look>) => setEdit((e) => ({ ...e, options: { ...e.options, ...change } }));
  const setAspect = (aspect: string) => {
    const layout = layoutsFor(listed, aspect).includes(look.layout) ? look.layout : "auto";
    onLook({ aspect, layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });
  };
  const setLayout = (layout: string) => onLook({ layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });

  // ---------- playback of the edit: from the trim start, skipping cuts, stopping at the trim end ----------
  const seek = useCallback((sec: number) => {
    setView("edit");
    const v = video.current;
    if (v) v.currentTime = sec;
    setT(sec);
  }, []);
  function onTime() {
    const v = video.current;
    if (!v || view !== "edit") return;
    const now = v.currentTime, e = latest.current, cut = inCut(now, e.cuts);
    if (cut && cut[1] < e.trim.end) { v.currentTime = cut[1]; return; }
    if (now >= e.trim.end || cut) { v.pause(); v.currentTime = e.trim.start; }
    else if (now < e.trim.start - 0.25 && !v.paused) v.currentTime = e.trim.start;
    setT(v.currentTime);
  }
  function toggle() {
    const v = video.current;
    if (!v) return;
    if (v.paused) { if (view === "edit" && (v.currentTime < edit.trim.start || v.currentTime >= edit.trim.end - 0.05)) v.currentTime = edit.trim.start; v.play().catch(() => {}); }
    else v.pause();
  }

  // ---------- words, selection and cuts ----------
  const computed = useMemo(() => linesOf(words || []), [words]);
  const lines: Line[] = edit.caption_lines.length ? edit.caption_lines : computed;
  const selSpan: Span | null = sel && words?.length ? [words[Math.min(sel.a, sel.b)].start, words[Math.max(sel.a, sel.b)].end] : null;
  const selCount = sel ? Math.abs(sel.b - sel.a) + 1 : 0;
  const selAllCut = !!(sel && words && words.slice(Math.min(sel.a, sel.b), Math.max(sel.a, sel.b) + 1).every((w) => inCut((w.start + w.end) / 2, edit.cuts)));
  function pickWord(i: number, extend: boolean) {
    if (!words) return;
    if (extend && anchor.current !== null) setSel({ a: anchor.current, b: i });
    else { anchor.current = i; setSel({ a: i, b: i }); }
    seek(words[i].start);
  }
  // Cutting words also marks them `cut` in the word edit (#215): the caption and the video leave together.
  const cutSelection = () => { if (selSpan) { set({ cuts: addCut(edit.cuts, selSpan), ...(model ? { words: model.map((w) => (w.start >= selSpan[0] && w.end <= selSpan[1] ? { ...w, cut: true } : w)) } : {}) }); setSel(null); } };
  const restoreSelection = () => { if (selSpan) { set({ cuts: removeSpan(edit.cuts, selSpan), ...(model ? { words: model.map((w) => (w.start >= selSpan[0] && w.end <= selSpan[1] ? { ...w, cut: false } : w)) } : {}) }); setSel(null); } };
  // Text-based editing (#215): EditWord list once GET /words succeeded (or a saved edit already has words).
  const model: EditWord[] | null = wordEditsOn || wordEditReady(edit.words) || wordEditReady(apiWords)
    ? (edit.words ?? apiWords) : null;
  const menuOn = !!model && wordEditReady(model);
  const pickedIdx = sel ? Array.from({ length: Math.abs(sel.b - sel.a) + 1 }, (_, k) => Math.min(sel.a, sel.b) + k) : [];
  const captionLook = ((edit.options.caption_look as CaptionLook | null) || {}) as CaptionLook;

  function setLine(i: number, text: string) {
    const next = (edit.caption_lines.length ? edit.caption_lines : computed).map((l, j) => (j === i ? { ...l, text } : l));
    set({ caption_lines: next.every((l, j) => l.text === computed[j]?.text) ? [] : next });
  }

  // ---------- saving and rendering ----------
  const canSave = !!known.patchClip?.fields.includes("edit");
  // Export needs the exact price first: without the quote route there is no Export.
  const exportRoute = known.exportQuote ? known.exportRoute : null;
  // caption_look (#213) is sent once the API's schema has it, whether or not GET /v1/options lists it.
  const options = { ...onlyListed(listed, edit.options), ...(known.captionLook && edit.options.caption_look ? { caption_look: edit.options.caption_look } : {}) };
  const body = exportRoute ? exportBody(exportRoute, { jobId: clip.job_id, clipIds: [clip.id], options, edit: forApi(edit) }) : null;
  const quote = useQuote(confirm && known.exportQuote ? EXPORT_QUOTE : null, confirm ? body : null);
  const unsaved = !sameEdit(edit, base);

  async function save() {
    setSaving(true); setSaidSaved("");
    try { const c = await saveOnClip(clip.id, edit); onClip({ ...clip, ...c }); setBase(edit); dropDraft(clip.id); setDraftAt(null); setSaidSaved("Saved on the clip."); }
    catch (e) { fail(e); } finally { setSaving(false); }
  }
  async function startRender() {
    if (!body) return;
    setConfirm(false); setRender({});
    try {
      const r = await api(EXPORT, { body });
      const jobId = r?.job_id || r?.jobs?.[0]?.job_id;
      if (jobId) await followJob(jobId, (j) => setRender({ job: j }));
      const fresh = await api(`/v1/projects/${project.upload_id}`);
      const next = fresh.clips.find((c: any) => c.id === clip.id);
      if (next) onClip(next);
      setBase(edit); dropDraft(clip.id); setDraftAt(null); setView("file");
      setRender({ done: true });
      reloadMe();
    } catch (e) { setRender({ problem: e instanceof Error ? e.message : "The render failed." }); reloadMe(); }
  }

  const mapping = sourceTime(clip);
  const trimmedOut = (w: Word) => w.end <= edit.trim.start || w.start >= edit.trim.end;
  const lineNow = view === "edit" ? lines.find((l) => t >= l.start && t < l.end && !inCut((l.start + l.end) / 2, edit.cuts)) : null;
  const working = !!render && !render.done && !render.problem;
  const name = nameOf(clip, number);
  const tools = TOOLS.filter((x) => x.needs.some((k) => k in listed));
  const open = tools.find((x) => x.id === tool) || null;
  const aspect = String(look.aspect || "9:16"), [aw, ah] = aspect.split(":").map(Number);
  const status = saidSaved || (unsaved ? (draftAt ? `Draft saved in this browser at ${new Date(draftAt).toLocaleTimeString()}` : "Unsaved changes") : "No changes");

  return (
    <div className="grid min-w-0 gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Link href={`/dashboard/project/?id=${project.upload_id}`} aria-label={`Back to ${project.filename}`}
            className="grid h-9 w-9 flex-none place-items-center rounded-full text-muted hover:bg-chip hover:text-text"><Icon name="back" size={20} /></Link>
          <div className="grid min-w-0">
            <h1 title={name} className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[18px] font-semibold leading-[1.3] tracking-[-0.01em]">{name}</h1>
            <p className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12.5px] text-muted" aria-live="polite">{project.filename} · {status}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 narrow:w-full narrow:[&>*]:flex-1">
          <button type="button" className="btn small ghost" disabled={!unsaved} onClick={() => { setEdit(base); setSel(null); }}><Icon name="undo" size={16} />Undo all</button>
          <button type="button" className="btn small ghost" disabled={!canSave || saving || !unsaved} onClick={save}>{saving ? "Saving…" : "Save"}{!canSave && <Soon />}</button>
          <button type="button" className="btn small primary" disabled={!exportRoute || working} onClick={() => setConfirm(true)}><Icon name="download" size={16} />Export{!exportRoute && <Soon />}</button>
        </div>
      </header>

      {!canSave && !exportRoute && <p className="notice m-0 max-w-none">Saving edits to your account and rendering them are on their way. Until then, your edit is kept as a draft in this browser and nothing is charged.</p>}
      {restored && <p className="notice m-0 max-w-none" role="status">We brought back your unsaved edit from {new Date(restored).toLocaleString()}.{" "}
        <button className="link" onClick={() => { setEdit(base); dropDraft(clip.id); setDraftAt(null); setRestored(null); }}>Discard it</button>{" "}
        <button className="link" onClick={() => setRestored(null)}>Keep it</button></p>}
      {render && <div className={`job m-0 ${render.problem ? "failed" : render.done ? "succeeded" : "running"}`} role="status">
        <div className="job-head"><strong>Export</strong><span className="status">{render.problem ? "Failed" : render.done ? "Done: the new file is in the player" : `${render.job?.progress ?? 0}%`}</span></div>
        {working && <progress max={100} value={render.job?.progress ?? 0} aria-label="Export progress" />}
        {render.problem && <p className="error">{render.problem}</p>}
      </div>}

      <div className="flex flex-col overflow-hidden rounded-[24px] border border-solid border-line-soft [background:radial-gradient(ellipse_at_50%_0%,rgba(255,255,255,.05),transparent_60%),theme(colors.panel)]">
        <div className={`grid h-[min(680px,calc(100vh-250px))] min-h-[520px] ${open ? "grid-cols-[minmax(260px,1fr)_minmax(300px,1.1fr)_288px_88px]" : "grid-cols-[minmax(280px,1fr)_minmax(320px,1.35fr)_88px]"}
          mid:contents`}>

          {/* What was said: click a word to jump, shift-click to select, cut or restore. */}
          <section aria-label="What was said" className="flex min-h-0 flex-col gap-3 border-0 border-r border-solid border-line-soft p-5 mid:order-5 mid:max-h-[480px] mid:border-r-0 mid:border-t narrow:p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tabs seg label="Text" panel="editor-text" value={tab} onChange={setTab} tabs={[["transcript", "Transcript"], ["captions", "Caption lines"]]} />
              {tab === "transcript" && <div className="flex items-center gap-1" role="group" aria-label="Selected words">
                <span className="mr-1 text-[12.5px] text-muted" aria-live="polite">{selCount ? `${selCount} selected` : ""}</span>
                <button type="button" className="btn small ghost" disabled={!selCount || selAllCut} onClick={cutSelection}><Icon name="scissors" size={16} />Cut</button>
                <button type="button" className="btn small ghost" disabled={!selCount || !edit.cuts.length} onClick={restoreSelection}>Restore</button>
              </div>}
            </div>
            <div id="editor-text" role="tabpanel" aria-label={tab === "transcript" ? "Transcript" : "Caption lines"} className="grid min-h-0 flex-1 content-start gap-3 overflow-y-auto pr-1">
              {tab === "transcript" && <>
                {words === null ? <p className="muted">Reading the words…</p>
                  : !words.length ? <p className="muted">{wordsProblem || "This clip has no captions file, so there are no words to edit. Trim and the tools still work."}</p>
                  : <div className="flex flex-wrap gap-x-[2px] gap-y-1 text-[16px] leading-[1.55]"
                      onKeyDown={(e) => { if ((e.key === "Delete" || e.key === "Backspace") && selCount) { e.preventDefault(); if (selAllCut) restoreSelection(); else cutSelection(); } }}>
                      {words.map((w, i) => {
                        const cut = !!inCut((w.start + w.end) / 2, edit.cuts), out = trimmedOut(w);
                        const picked = !!sel && i >= Math.min(sel.a, sel.b) && i <= Math.max(sel.a, sel.b);
                        const now = view === "edit" && t >= w.start && t < w.end;
                        return <button key={i} type="button" aria-pressed={picked}
                          className={`cursor-pointer rounded-[6px] border-0 px-[3px] py-[1px] font-body text-[16px] leading-[1.55] hover:bg-chip-hover
                            ${picked ? "bg-[rgba(255,255,255,.16)] text-text" : "bg-transparent"} ${now ? "text-lime" : cut ? "text-danger" : "text-label"}
                            ${cut ? "line-through opacity-70" : ""} ${out ? "opacity-35" : ""}`}
                          aria-label={`${w.text}, ${stamp(w.start)}${cut ? ", cut" : ""}${out ? ", outside the trim" : ""}`}
                          onClick={(e) => pickWord(i, e.shiftKey)}>{model?.[i] ? <WordFace w={model[i]} /> : w.text}</button>;
                      })}
                    </div>}
                {!!words?.length && <WordMenu on={menuOn} words={model} picked={pickedIdx} onWords={(next) => set({ words: next })} onCutWithVideo={cutSelection} />}
                <p className="muted m-0 text-[12.5px]">Click a word to jump to it. Shift-click another to select everything between, then press Cut or Delete.</p>
                {!mapping.exact && (job?.options?.tighten || job?.options?.flash_forward) && !!words?.length &&
                  <p className="muted m-0 text-[12.5px]">Word times may be off by a moment: dead air was cut from this clip when it was made, and the exact parts aren&apos;t known yet.</p>}
                {edit.cuts.length > 0 && <ul className="m-0 flex list-none flex-wrap gap-2" aria-label="Cuts">
                  {edit.cuts.map((c) => <li key={c.join("-")} className="flex items-center gap-2 rounded-full border border-solid border-[rgba(255,92,122,.45)] px-3 py-1 text-[12.5px]">
                    <span className="tabular-nums">{stamp(c[0])} to {stamp(c[1])}</span>
                    <button type="button" className="link" onClick={() => set({ cuts: removeSpan(edit.cuts, c) })}>Restore</button></li>)}
                </ul>}
              </>}
              {tab === "captions" && model && <p className="notice m-0 max-w-none">Edit captions word by word in the Transcript tab: pick words, then edit, split, highlight, add an emoji or remove them. Your word edits are what the export draws.</p>}
              {tab === "captions" && !model && <>
                {!look.captions && <p className="notice m-0 max-w-none">Captions are off. Turn them on in the Captions tool; these lines are used once they&apos;re on.</p>}
                {!words?.length ? <p className="muted">No caption lines: this clip has no words.</p> : <>
                  <p className="muted m-0 text-[12.5px]">Change the words of any line. Times stay as they were said.</p>
                  <ol className="cap-lines m-0 max-h-none">
                    {lines.map((l, i) => {
                      const cut = !!inCut((l.start + l.end) / 2, edit.cuts), changed = computed[i] && l.text !== computed[i].text;
                      return <li key={i} className={`${cut ? "cut" : ""} ${changed ? "changed" : ""}`}>
                        <button type="button" className="cap-time tabular" onClick={() => seek(l.start)} aria-label={`Play from ${stamp(l.start)}`}>{stamp(l.start)}</button>
                        <input value={l.text} maxLength={120} aria-label={`Caption line ${i + 1}, ${stamp(l.start)}`} onChange={(e) => setLine(i, e.target.value)} />
                        {changed ? <button type="button" className="link small" onClick={() => setLine(i, computed[i].text)}>Undo</button> : cut ? <span className="muted small">Cut</span> : <span />}
                      </li>;
                    })}
                  </ol>
                  {edit.caption_lines.length > 0 && <button type="button" className="link small justify-self-start" onClick={() => set({ caption_lines: [] })}>Put every line back as it was said</button>}
                </>}
              </>}
            </div>
          </section>

          {/* The preview, in the clip's own shape. */}
          <section aria-label="Preview" className="flex min-h-0 min-w-0 flex-col items-center gap-3 p-5 mid:order-1 narrow:p-3">
            <div className="flex w-full flex-wrap items-center justify-center gap-2">
              {"aspect" in listed && <label className="m-0 block"><span className="sr-only">Shape</span>
                <select className={PILL_SELECT} value={aspect} onChange={(e) => setAspect(e.target.value)}>
                  {(listed.aspect?.values || [aspect]).map((a: string) => <option key={a} value={a}>{ASPECT_NAMES[a] || a}</option>)}</select></label>}
              {"layout" in listed && <label className="m-0 block"><span className="sr-only">Layout</span>
                <select className={PILL_SELECT} value={look.layout} onChange={(e) => setLayout(e.target.value)}>
                  {layoutChoices(listed, aspect, look.layout).map((l) => <option key={l} value={l}>Layout: {layoutName(l)}</option>)}</select></label>}
              <div className="seg" role="group" aria-label="What the player shows">
                <button type="button" aria-pressed={view === "edit"} onClick={() => setView("edit")}>Your edit</button>
                <button type="button" aria-pressed={view === "file"} onClick={() => { video.current?.pause(); setView("file"); }}>Current file</button>
              </div>
            </div>
            <div className="relative grid min-h-0 w-full flex-1 place-items-center mid:flex-none">
              <div style={{ aspectRatio: `${aw || 9} / ${ah || 16}`, "--w": `calc(62vh * ${aw || 9} / ${ah || 16})`, containerType: "size" } as React.CSSProperties}
                className="relative h-full max-h-full max-w-full overflow-hidden rounded-16 bg-black shadow-[0_20px_60px_rgba(0,0,0,.55)] mid:h-auto mid:w-[min(100%,var(--w))]">
                {clip.thumb_url && <img src={clip.thumb_url} alt="" aria-hidden="true" className="absolute inset-[-24px] h-[calc(100%+48px)] w-[calc(100%+48px)] object-cover blur-[18px] brightness-[.4]" />}
                <video ref={video} key={view} preload="metadata" playsInline src={view === "edit" ? project.source_url : clip.export_url || clip.video_url}
                  poster={view === "file" ? clip.thumb_url || undefined : undefined} controls={view === "file"}
                  className="relative block h-full w-full object-contain"
                  onLoadedMetadata={() => { if (view === "edit" && video.current) video.current.currentTime = t; }}
                  onTimeUpdate={onTime} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} />
                {look.captions && view === "edit" && (() => {
                  const cap = model ? captionAt(model, t, String(look.caption_style || "impact"))
                    : lineNow ? [{ start: lineNow.start, end: lineNow.end, text: lineNow.text, hidden: false, cut: false, highlight: null, emoji: null, break_before: false }] : null;
                  return cap ? <CaptionOverlay words={cap} look={captionLook} /> : null;
                })()}
                {view === "edit" && <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-[rgba(0,0,0,.6)] px-[10px] py-[3px] text-[11.5px] font-medium text-soft">Source preview</span>}
              </div>
            </div>
            <p className="muted m-0 max-w-[420px] text-center text-[12px]">{view === "edit"
              ? "Plays your source with the trim and cuts. The layout, captions and hook are drawn when you export."
              : "The clip file as it is now."}</p>
          </section>

          {/* The open tool's settings. */}
          {open && <section aria-label={open.title} className="flex min-h-0 flex-col gap-3 border-0 border-l border-solid border-line-soft bg-[rgba(255,255,255,.02)] p-4 mid:order-4 mid:border-l-0 mid:border-t">
            <div className="flex items-center justify-between gap-2">
              <h2 className="m-0 text-[15px] font-semibold">{open.title}</h2>
              <button type="button" className={ICON_BTN} aria-label={`Close ${open.title}`} onClick={() => setTool(null)}><Icon name="close" size={18} /></button>
            </div>
            <div className="grid min-h-0 content-start gap-3 overflow-y-auto pr-1 [&_.line]:p-3 [&_.lines]:gap-2 [&_.options]:grid [&_.options]:gap-3 [&_.panels]:p-3 [&_.panel-sketch]:hidden [&_select]:w-full">
              <Custom listed={listed} look={look} onLook={onLook} setAspect={setAspect} sections={open.sections} hint={open.id === "edits" ? "Applied when you export." : ""} />
              {open.id === "captions" && look.captions && <CaptionLookControls spec={known.captionLook} look={captionLook}
                onLook={(l) => onLook({ caption_look: tidyLook(l) } as any)} />}
              {open.id === "edits" && <ul className="lines m-0" aria-label="Not on an existing clip yet">{["Punch-in zoom", "Open on the best moment"].map((n) => <li key={n} className="line off"><span className="font-medium text-fg-2">{n}</span><Soon short /></li>)}</ul>}
              {open.id === "hook" && "hook_overlay" in listed && look.hook_overlay && <fieldset className="panels hook-set">
                <legend>Hook text</legend>
                <label className="grow">Text<input value={edit.hook_text ?? clip.hook ?? ""} maxLength={HOOK_MAX} placeholder="A short opening line"
                  onChange={(e) => set({ hook_text: e.target.value === (clip.hook ?? "") ? null : e.target.value })} /></label>
                {"hook_style" in listed && <label>Style<select value={String(look.hook_style ?? listed.hook_style.default ?? "")} onChange={(e) => onLook({ hook_style: e.target.value } as any)}>
                  {(listed.hook_style.values || []).map((v: string) => <option key={v} value={v}>{tidy(v)}</option>)}</select></label>}
                {"hook_position" in listed && <label>Position<select value={String(look.hook_position ?? listed.hook_position.default ?? "")} onChange={(e) => onLook({ hook_position: e.target.value } as any)}>
                  {(listed.hook_position.values || []).map((v: string) => <option key={v} value={v}>{POSITION_NAMES[v] || tidy(v)}</option>)}</select></label>}
              </fieldset>}
            </div>
          </section>}

          {/* The tool rail: the built tools open their panel; the planned ones are labelled and do nothing. */}
          <nav aria-label="Editing tools" className="flex min-h-0 flex-col gap-1 overflow-y-auto border-0 border-l border-solid border-line-soft p-2
            mid:order-3 mid:flex-row mid:overflow-x-auto mid:border-l-0 mid:border-t">
            {tools.map((x) => <button key={x.id} type="button" aria-pressed={tool === x.id} onClick={() => setTool(tool === x.id ? null : x.id)}
              className={`${RAIL_ITEM} cursor-pointer text-soft hover:bg-chip hover:text-text aria-pressed:bg-chip-hover aria-pressed:text-text`}>
              <Icon name={x.icon} size={22} /><span>{x.label}</span></button>)}
            <span className="mx-3 my-1 h-px flex-none bg-line-soft mid:mx-1 mid:my-2 mid:h-auto mid:w-px" aria-hidden="true" />
            {PLANNED.map(([icon, label]) => <span key={label} aria-disabled="true" title={`${label}: coming soon`} className={`${RAIL_ITEM} cursor-default text-dim`}>
              <Icon name={icon} size={22} /><span>{label}</span><Soon short /></span>)}
          </nav>
        </div>

        <Timeline duration={project.duration_sec} clip={clip} edit={edit} t={t} sel={selSpan} playing={playing} view={view}
          onToggle={toggle} onTrim={(trim) => { set({ trim }); seek(trim.start); }} onSeek={seek}
          onRestore={(c) => set({ cuts: removeSpan(edit.cuts, c) })} />
      </div>

      {confirm && body && <Confirm title="Export this clip" onClose={() => setConfirm(false)}>
        <p className="muted">{stamp(keptLength(edit))} long · {edit.cuts.length} cut{edit.cuts.length === 1 ? "" : "s"} · {aspect}{look.captions ? " · captions" : ""}</p>
        <p aria-live="polite"><QuoteLine quote={quote} what="This export" exact /></p>
        <div className="editor-actions">
          <button type="button" className="btn small ghost" onClick={() => setConfirm(false)}>Back</button>
          <button type="button" className="btn small primary" disabled={quote.state !== "ok"} onClick={startRender}>
            {quote.state === "ok" ? `Export for ${creditWords(quote.credits)}` : "Export"}</button>
        </div>
      </Confirm>}
    </div>
  );
}

// A small modal: the price and the button that spends it.
function Confirm({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal(); }, []);
  return (
    <dialog ref={dialog} className="picker confirm" aria-labelledby="confirm-title" onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}>
      <div className="picker-body">
        <div className="picker-head"><h2 id="confirm-title">{title}</h2>
          <button className="icon-btn" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" /></button></div>
        {children}
      </div>
    </dialog>
  );
}

// Seconds on the ruler: a step that gives about eight labels across the window.
const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
const MIN_PAD = 2;

// The timeline under the editor: play controls and zoom, a ruler, then the source around the clip with the two
// trim handles, the cuts and the playhead. Clicking the strip seeks. The handles are native sliders (arrows move
// a tenth of a second); the times can also be typed. Zoom changes how much of the source around the clip shows.
function Timeline({ duration, clip, edit, t, sel, playing, view, onToggle, onTrim, onSeek, onRestore }: { duration: number; clip: any; edit: Edit; t: number;
  sel: Span | null; playing: boolean; view: "edit" | "file"; onToggle: () => void; onTrim: (trim: { start: number; end: number }) => void;
  onSeek: (t: number) => void; onRestore: (c: Span) => void }) {
  const len = clip.end_sec - clip.start_sec;
  const [pad, setPad] = useState(Math.max(10, len * 0.5));
  const lo = Math.max(0, Math.min(clip.start_sec, edit.trim.start) - pad), hi = Math.min(duration, Math.max(clip.end_sec, edit.trim.end) + pad);
  const least = Math.min(MIN_LENGTH, len);
  const pct = (s: number) => `${((s - lo) / (hi - lo)) * 100}%`;
  const setStart = (s: number) => onTrim({ start: round(Math.max(0, Math.min(s, edit.trim.end - least))), end: edit.trim.end });
  const setEnd = (e: number) => onTrim({ start: edit.trim.start, end: round(Math.min(duration, Math.max(e, edit.trim.start + least))) });
  const whole = lo <= 0 && hi >= duration;
  const step = STEPS.find((s) => (hi - lo) / s <= 9) || 3600;
  const ticks: number[] = [];
  for (let s = Math.ceil(lo / step) * step; s <= hi; s += step) ticks.push(s);
  const inside = cutsInside(edit);
  return (
    <section aria-label="Timeline" className="grid gap-2 border-0 border-t mid:order-2 border-solid border-line-soft px-5 pb-4 pt-3 narrow:px-3">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 narrow:grid-cols-[auto_1fr]">
        <div className="flex items-center gap-1 narrow:hidden">
          {inside.length > 0 && <span className="text-[12.5px] text-muted">{inside.length} cut{inside.length === 1 ? "" : "s"}{" "}
            <button type="button" className="link" onClick={() => inside.forEach(onRestore)}>Restore all</button></span>}
        </div>
        <div className="flex items-center justify-center gap-1">
          <button type="button" className={ICON_BTN} aria-label="Go to the start of the clip" onClick={() => onSeek(edit.trim.start)}><Icon name="skipBack" size={18} /></button>
          <button type="button" className="grid h-10 w-10 cursor-pointer place-items-center rounded-full border-0 bg-text text-bg disabled:opacity-40" disabled={view !== "edit"}
            aria-label={playing ? "Pause" : "Play the edit"} onClick={onToggle}><Icon name={playing ? "pause" : "play"} size={18} /></button>
          <button type="button" className={ICON_BTN} aria-label="Go to the end of the clip" onClick={() => onSeek(Math.max(edit.trim.start, edit.trim.end - 0.5))}><Icon name="skipForward" size={18} /></button>
          <span className="ml-2 font-body text-[13px] tabular-nums text-soft">{stamp(Math.max(0, t - edit.trim.start))} <span className="text-dim">/ {stamp(keptLength(edit))}</span></span>
        </div>
        <div className="flex items-center justify-end gap-1">
          <button type="button" className={ICON_BTN} aria-label="Zoom out: show more of the video" disabled={whole} onClick={() => setPad((p) => p * 3)}><Icon name="zoomOut" size={18} /></button>
          <button type="button" className={ICON_BTN} aria-label="Zoom in" disabled={pad <= MIN_PAD} onClick={() => setPad((p) => Math.max(MIN_PAD, p / 3))}><Icon name="zoomIn" size={18} /></button>
        </div>
      </div>
      <div className="relative h-5 select-none text-[11px] tabular-nums text-dim narrow:[&>span:nth-child(even)]:hidden" aria-hidden="true">
        {ticks.map((s) => <span key={s} className="absolute top-0 -translate-x-1/2 whitespace-nowrap" style={{ left: pct(s) }}>{stamp(s).replace(/\.0$/, "")}</span>)}
      </div>
      <div className="relative h-14 cursor-pointer overflow-hidden rounded-12 border border-solid border-line bg-card-2
        [background-image:repeating-linear-gradient(90deg,transparent_0_calc(10%-1px),rgba(255,255,255,.05)_calc(10%-1px)_10%)]" onPointerDown={(e) => {
          if ((e.target as HTMLElement).tagName === "INPUT") return;
          const box = e.currentTarget.getBoundingClientRect();
          onSeek(round(lo + ((e.clientX - box.left) / box.width) * (hi - lo)));
        }}>
        <span className="pointer-events-none absolute inset-y-0 rounded-8 border border-dashed border-[rgba(255,255,255,.3)]" title="Where the clip was first cut"
          style={{ left: pct(clip.start_sec), width: `calc(${pct(clip.end_sec)} - ${pct(clip.start_sec)})` }} />
        <span className="pointer-events-none absolute inset-y-0 border-x-[3px] border-y-0 border-solid border-lime bg-[rgba(184,255,60,.16)]"
          style={{ left: pct(edit.trim.start), width: `calc(${pct(edit.trim.end)} - ${pct(edit.trim.start)})` }} />
        {inside.map((c) => <span key={c.join("-")} className="pointer-events-none absolute inset-y-0 [background:repeating-linear-gradient(45deg,rgba(255,92,122,.55)_0_6px,rgba(255,92,122,.25)_6px_12px)]"
          title={`Cut ${stamp(c[0])} to ${stamp(c[1])}`} style={{ left: pct(c[0]), width: `calc(${pct(c[1])} - ${pct(c[0])})` }} />)}
        {sel && <span className="pointer-events-none absolute inset-y-0 bg-[rgba(255,255,255,.22)]" style={{ left: pct(sel[0]), width: `calc(${pct(sel[1])} - ${pct(sel[0])})` }} />}
        <span className="pointer-events-none absolute inset-y-0 -ml-px w-[2px] bg-text shadow-[0_0_6px_rgba(255,255,255,.8)]" style={{ left: pct(Math.min(hi, Math.max(lo, t))) }} />
        <div className="range2 trim-handles" style={{ "--a": pct(edit.trim.start), "--b": pct(edit.trim.end) } as React.CSSProperties}>
          <input type="range" min={lo} max={hi} step={0.1} value={edit.trim.start} aria-label="Trim start" aria-valuetext={stamp(edit.trim.start)}
            onChange={(e) => setStart(+e.target.value)} />
          <input type="range" min={lo} max={hi} step={0.1} value={edit.trim.end} aria-label="Trim end" aria-valuetext={stamp(edit.trim.end)}
            onChange={(e) => setEnd(+e.target.value)} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <StampField label="Start" sec={edit.trim.start} onSet={setStart} />
        <StampField label="End" sec={edit.trim.end} onSet={setEnd} />
        {inside.length > 0 && <span className="hidden text-[12.5px] text-muted narrow:inline">{inside.length} cut{inside.length === 1 ? "" : "s"}{" "}
          <button type="button" className="link" onClick={() => inside.forEach(onRestore)}>Restore all</button></span>}
      </div>
    </section>
  );
}

function StampField({ label, sec, onSet }: { label: string; sec: number; onSet: (sec: number) => void }) {
  const [typed, setTyped] = useState<string | null>(null);
  const commit = () => { const n = typed === null ? null : parseStamp(typed); if (n !== null) onSet(n); setTyped(null); };
  return (
    <label className="range2-time">{label}
      <input className="time" inputMode="decimal" value={typed ?? stamp(sec)} aria-label={`Trim ${label.toLowerCase()} time, minutes:seconds`}
        onChange={(e) => setTyped(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }} />
    </label>
  );
}
