"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { addCut, cutsInside, dropDraft, Edit, forApi, inCut, keptLength, Line, linesOf, loadDraft, loadWords, MIN_LENGTH, removeSpan, round,
  saveDraft, saveOnClip, sameEdit, sourceTime, Span, startEdit, Word } from "@/lib/edit";
import { creditWords, exportBody, followJob, useQuote } from "@/lib/exporting";
import { layoutsFor, Listed, onlyListed } from "@/lib/options";
import { EXPORT, EXPORT_QUOTE, Routes } from "@/lib/routes";
import { hasPanels, Look, LOOK_KEYS, startLook, tidy } from "@/lib/templates";
import { nameOf } from "./ClipCard";
import { Icon, Soon } from "./Icon";
import { Custom } from "./PreEdit";
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

// The look a clip was made with: the dashboard's starting look, then whatever its run stated.
export function lookOfJob(listed: Listed, job: any): Record<string, unknown> {
  const o = job?.options || {}, look: Record<string, unknown> = { ...startLook(listed) };
  for (const k of [...LOOK_KEYS, "hook_style", "hook_position"]) if (k in o && o[k] !== undefined) look[k] = o[k];
  return onlyListed(listed, look);
}

type Tab = "transcript" | "captions" | "look";
// The editor for one clip. Everything it changes is kept in `edit`; the draft is kept in this browser until the
// edit is saved on the clip or rendered.
export function Editor({ project, clip, job, listed, known, number, onClip }: { project: any; clip: any; job: any; listed: Listed; known: Routes;
  number?: number; onClip: (c: any) => void }) {
  const { fail, reloadMe } = useDash();
  const first = useMemo(() => startEdit(clip, lookOfJob(listed, job)), [clip.id]);    // eslint-disable-line react-hooks/exhaustive-deps
  const [base, setBase] = useState<Edit>(first);                 // what is saved (or the clip as it was made)
  const [edit, setEdit] = useState<Edit>(first);
  const [restored, setRestored] = useState<number | null>(null), [draftAt, setDraftAt] = useState<number | null>(null);
  const [words, setWords] = useState<Word[] | null>(null), [wordsProblem, setWordsProblem] = useState("");
  const [tab, setTab] = useState<Tab>("transcript");
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
    loadWords(clip).then((w) => on && setWords(w)).catch((e) => { if (on) { setWords([]); setWordsProblem(e.message); } });
    return () => { on = false; };
  }, [clip.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  const set = (change: Partial<Edit>) => setEdit((e) => ({ ...e, ...change }));
  const look = { ...startLook(listed), ...edit.options } as Look & Record<string, any>;
  const onLook = (change: Partial<Look>) => setEdit((e) => ({ ...e, options: { ...e.options, ...change } }));
  const setAspect = (aspect: string) => {
    const layout = layoutsFor(listed, aspect).includes(look.layout) ? look.layout : "auto";
    onLook({ aspect, layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });
  };

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
  const cutSelection = () => { if (selSpan) { set({ cuts: addCut(edit.cuts, selSpan) }); setSel(null); } };
  const restoreSelection = () => { if (selSpan) { set({ cuts: removeSpan(edit.cuts, selSpan) }); setSel(null); } };

  function setLine(i: number, text: string) {
    const next = (edit.caption_lines.length ? edit.caption_lines : computed).map((l, j) => (j === i ? { ...l, text } : l));
    set({ caption_lines: next.every((l, j) => l.text === computed[j]?.text) ? [] : next });
  }

  // ---------- saving and rendering ----------
  const canSave = !!known.patchClip?.fields.includes("edit");
  const exportRoute = known.exportRoute;
  const options = onlyListed(listed, edit.options);
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
  return (
    <div className="editor">
      {!canSave && !exportRoute && <p className="notice">Saving edits to your account and rendering them are on their way. Until then, your edit is kept as a draft in this browser and nothing is charged.</p>}
      {restored && <p className="notice" role="status">We brought back your unsaved edit from {new Date(restored).toLocaleString()}.{" "}
        <button className="link" onClick={() => { setEdit(base); dropDraft(clip.id); setDraftAt(null); setRestored(null); }}>Discard it</button>{" "}
        <button className="link" onClick={() => setRestored(null)}>Keep it</button></p>}

      {render && <div className={`job ${render.problem ? "failed" : render.done ? "succeeded" : "running"}`} role="status">
        <div className="job-head"><strong>Render</strong><span className="status">{render.problem ? "Failed" : render.done ? "Done: the new file is in the player" : `${render.job?.progress ?? 0}%`}</span></div>
        {working && <progress max={100} value={render.job?.progress ?? 0} aria-label="Render progress" />}
        {render.problem && <p className="error">{render.problem}</p>}
      </div>}
      <div className="editor-grid">
        <section className="editor-stage" aria-label="Preview and timeline">
          <div className="editor-video">
            <video ref={video} key={view} preload="metadata" playsInline src={view === "edit" ? project.source_url : clip.export_url || clip.video_url}
              poster={view === "file" ? clip.thumb_url || undefined : undefined} controls={view === "file"}
              onLoadedMetadata={() => { if (view === "edit" && video.current) video.current.currentTime = t; }}
              onTimeUpdate={onTime} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} />
            {lineNow && look.captions && <span className="editor-caption" aria-hidden="true">{lineNow.text}</span>}
          </div>
          <div className="editor-controls">
            {view === "edit" && <button type="button" className="btn small primary" onClick={toggle} aria-label={playing ? "Pause" : "Play the edit"}>
              <Icon name={playing ? "pause" : "play"} size={16} />{playing ? "Pause" : "Play"}</button>}
            {view === "edit" && <span className="muted small tabular">{stamp(Math.max(0, t - edit.trim.start))} · clip {stamp(keptLength(edit))}</span>}
            <div className="seg" role="group" aria-label="What the player shows">
              <button type="button" aria-pressed={view === "edit"} onClick={() => setView("edit")}>Your edit</button>
              <button type="button" aria-pressed={view === "file"} onClick={() => { video.current?.pause(); setView("file"); }}>Current file</button>
            </div>
          </div>
          <p className="muted small">{view === "edit" ? "The preview plays the source video with your trim and cuts. Captions show as plain text here; the render draws them in your style."
            : "The clip file as it is now."}</p>
          <TrimBar duration={project.duration_sec} clip={clip} edit={edit} t={t} sel={selSpan} onTrim={(trim) => { set({ trim }); seek(trim.start); }}
            onSeek={seek} onRestore={(c) => set({ cuts: removeSpan(edit.cuts, c) })} />
        </section>

        <section className="editor-side" aria-label="Edit">
          <Tabs label="Editor" panel="editor-panel" value={tab} onChange={setTab} tabs={[["transcript", "Transcript"], ["captions", "Caption lines"], ["look", "Look"]]} />
          <div id="editor-panel" role="tabpanel" aria-label={tab === "transcript" ? "Transcript" : tab === "captions" ? "Caption lines" : "Look"} className="stack-s">
            {tab === "transcript" && <>
              <p className="muted small">Click a word to jump to it. Shift-click another word to select everything between, then cut it. Delete cuts the selection too.</p>
              <div className="cutbar" role="group" aria-label="Selected words">
                <span className="small" aria-live="polite">{selCount ? `${selCount} word${selCount === 1 ? "" : "s"} selected` : "No words selected"}</span>
                <button type="button" className="btn small ghost danger" disabled={!selCount || selAllCut} onClick={cutSelection}><Icon name="scissors" size={16} />Cut</button>
                <button type="button" className="btn small ghost" disabled={!selCount || !edit.cuts.length} onClick={restoreSelection}>Restore</button>
              </div>
              {words === null ? <p className="muted">Reading the words…</p>
                : !words.length ? <p className="muted">{wordsProblem || "This clip has no captions file, so there are no words to edit. Trim and the look still work."}</p>
                : <div className="words" onKeyDown={(e) => { if ((e.key === "Delete" || e.key === "Backspace") && selCount) { e.preventDefault(); if (selAllCut) restoreSelection(); else cutSelection(); } }}>
                    {words.map((w, i) => {
                      const cut = !!inCut((w.start + w.end) / 2, edit.cuts), out = trimmedOut(w);
                      const picked = !!sel && i >= Math.min(sel.a, sel.b) && i <= Math.max(sel.a, sel.b);
                      const now = view === "edit" && t >= w.start && t < w.end;
                      return <button key={i} type="button" className={`word ${cut ? "cut" : ""} ${out ? "out" : ""} ${picked ? "sel" : ""} ${now ? "now" : ""}`}
                        aria-pressed={picked} aria-label={`${w.text}, ${stamp(w.start)}${cut ? ", cut" : ""}${out ? ", outside the trim" : ""}`}
                        onClick={(e) => pickWord(i, e.shiftKey)}>{w.text}</button>;
                    })}
                  </div>}
              {!mapping.exact && (job?.options?.tighten || job?.options?.flash_forward) && !!words?.length &&
                <p className="muted small">Word times may be off by a moment: dead air was cut from this clip when it was made, and the exact parts aren't known yet.</p>}
              {edit.cuts.length > 0 && <ul className="cut-list" aria-label="Cuts">
                {edit.cuts.map((c) => <li key={c.join("-")}><span className="tabular">{stamp(c[0])} to {stamp(c[1])}</span>
                  <button type="button" className="link" onClick={() => set({ cuts: removeSpan(edit.cuts, c) })}>Restore</button></li>)}
              </ul>}
            </>}

            {tab === "captions" && <>
              {!look.captions && <p className="notice">Subtitles are off under Look. These lines are used once they're on.</p>}
              {!words?.length ? <p className="muted">No caption lines: this clip has no words.</p> : <>
                <p className="muted small">Change the words of any line. Times stay as they were said.</p>
                <ol className="cap-lines">
                  {lines.map((l, i) => {
                    const cut = !!inCut((l.start + l.end) / 2, edit.cuts), changed = computed[i] && l.text !== computed[i].text;
                    return <li key={i} className={`${cut ? "cut" : ""} ${changed ? "changed" : ""}`}>
                      <button type="button" className="cap-time tabular" onClick={() => seek(l.start)} aria-label={`Play from ${stamp(l.start)}`}>{stamp(l.start)}</button>
                      <input value={l.text} maxLength={120} aria-label={`Caption line ${i + 1}, ${stamp(l.start)}`} onChange={(e) => setLine(i, e.target.value)} />
                      {changed ? <button type="button" className="link small" onClick={() => setLine(i, computed[i].text)}>Undo</button> : cut ? <span className="muted small">Cut</span> : <span />}
                    </li>;
                  })}
                </ol>
                {edit.caption_lines.length > 0 && <button type="button" className="link small" onClick={() => set({ caption_lines: [] })}>Put every line back as it was said</button>}
              </>}
            </>}

            {tab === "look" && <>
              <Custom listed={listed} look={look} onLook={onLook} setAspect={setAspect} hint="Tick what this clip gets when it is rendered again." />
              {"hook_overlay" in listed && look.hook_overlay && <fieldset className="panels hook-set">
                <legend>Hook</legend>
                <label className="grow">Hook text<input value={edit.hook_text ?? clip.hook ?? ""} maxLength={HOOK_MAX} placeholder="A short opening line"
                  onChange={(e) => set({ hook_text: e.target.value === (clip.hook ?? "") ? null : e.target.value })} /></label>
                {"hook_style" in listed && <label>Hook style<select value={String(look.hook_style ?? listed.hook_style.default ?? "")} onChange={(e) => onLook({ hook_style: e.target.value } as any)}>
                  {(listed.hook_style.values || []).map((v: string) => <option key={v} value={v}>{tidy(v)}</option>)}</select></label>}
                {"hook_position" in listed && <label>Hook position<select value={String(look.hook_position ?? listed.hook_position.default ?? "")} onChange={(e) => onLook({ hook_position: e.target.value } as any)}>
                  {(listed.hook_position.values || []).map((v: string) => <option key={v} value={v}>{POSITION_NAMES[v] || tidy(v)}</option>)}</select></label>}
              </fieldset>}
            </>}
          </div>
        </section>
      </div>

      <div className="editor-bar">
        <p className="muted small" aria-live="polite">{saidSaved || (unsaved ? (draftAt ? `Draft saved in this browser at ${new Date(draftAt).toLocaleTimeString()}.` : "Unsaved changes.") : "No changes.")}</p>
        <div className="editor-actions">
          <button type="button" className="btn small ghost" disabled={!unsaved} onClick={() => { setEdit(base); setSel(null); }}>Undo all changes</button>
          <button type="button" className="btn small ghost" disabled={!canSave || saving || !unsaved} onClick={save}>{saving ? "Saving…" : "Save"}{!canSave && <Soon />}</button>
          <button type="button" className="btn small primary" disabled={!exportRoute || working} onClick={() => setConfirm(true)}><Icon name="film" size={16} />Render{!exportRoute && <Soon />}</button>
        </div>
      </div>

      {confirm && body && <Confirm title="Render this clip again" onClose={() => setConfirm(false)}>
        <p className="muted">{stamp(keptLength(edit))} long · {edit.cuts.length} cut{edit.cuts.length === 1 ? "" : "s"} · {String(look.aspect)}{look.captions ? " · subtitles" : ""}</p>
        <p aria-live="polite">{known.exportQuote ? <QuoteLine quote={quote} what="This render" exact /> : "You only use credits for the minutes rendered."}</p>
        <div className="editor-actions">
          <button type="button" className="btn small ghost" onClick={() => setConfirm(false)}>Back</button>
          <button type="button" className="btn small primary" disabled={!!known.exportQuote && quote.state !== "ok"} onClick={startRender}>
            {quote.state === "ok" ? `Render for ${creditWords(quote.credits)}` : "Render"}</button>
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

// The source around the clip, with the two trim handles, the cuts and the playhead. Clicking the strip seeks.
// The handles are native sliders (arrows move a tenth of a second); the times can also be typed.
function TrimBar({ duration, clip, edit, t, sel, onTrim, onSeek, onRestore }: { duration: number; clip: any; edit: Edit; t: number; sel: Span | null;
  onTrim: (trim: { start: number; end: number }) => void; onSeek: (t: number) => void; onRestore: (c: Span) => void }) {
  const len = clip.end_sec - clip.start_sec;
  const [pad, setPad] = useState(Math.max(10, len * 0.5));
  const lo = Math.max(0, Math.min(clip.start_sec, edit.trim.start) - pad), hi = Math.min(duration, Math.max(clip.end_sec, edit.trim.end) + pad);
  const least = Math.min(MIN_LENGTH, len);
  const pct = (s: number) => `${((s - lo) / (hi - lo)) * 100}%`;
  const setStart = (s: number) => onTrim({ start: round(Math.max(0, Math.min(s, edit.trim.end - least))), end: edit.trim.end });
  const setEnd = (e: number) => onTrim({ start: edit.trim.start, end: round(Math.min(duration, Math.max(e, edit.trim.start + least))) });
  const whole = lo <= 0 && hi >= duration;
  return (
    <div className="trim">
      <div className="trim-track" onPointerDown={(e) => {
        if ((e.target as HTMLElement).tagName === "INPUT") return;
        const box = e.currentTarget.getBoundingClientRect();
        onSeek(round(lo + ((e.clientX - box.left) / box.width) * (hi - lo)));
      }}>
        <span className="trim-orig" style={{ left: pct(clip.start_sec), width: `calc(${pct(clip.end_sec)} - ${pct(clip.start_sec)})` }} title="Where the clip was first cut" />
        <span className="trim-kept" style={{ left: pct(edit.trim.start), width: `calc(${pct(edit.trim.end)} - ${pct(edit.trim.start)})` }} />
        {cutsInside(edit).map((c) => <span key={c.join("-")} className="trim-cut" title={`Cut ${stamp(c[0])} to ${stamp(c[1])}`}
          style={{ left: pct(c[0]), width: `calc(${pct(c[1])} - ${pct(c[0])})` }} />)}
        {sel && <span className="trim-sel" style={{ left: pct(sel[0]), width: `calc(${pct(sel[1])} - ${pct(sel[0])})` }} />}
        <span className="trim-head" style={{ left: pct(Math.min(hi, Math.max(lo, t))) }} />
        <div className="range2 trim-handles" style={{ "--a": pct(edit.trim.start), "--b": pct(edit.trim.end) } as React.CSSProperties}>
          <input type="range" min={lo} max={hi} step={0.1} value={edit.trim.start} aria-label="Trim start" aria-valuetext={stamp(edit.trim.start)}
            onChange={(e) => setStart(+e.target.value)} />
          <input type="range" min={lo} max={hi} step={0.1} value={edit.trim.end} aria-label="Trim end" aria-valuetext={stamp(edit.trim.end)}
            onChange={(e) => setEnd(+e.target.value)} />
        </div>
      </div>
      <div className="timeline-ends tabular" aria-hidden="true"><span>{stamp(lo)}</span><span>{stamp(hi)}</span></div>
      <div className="trim-fields">
        <StampField label="Start" sec={edit.trim.start} onSet={setStart} />
        <StampField label="End" sec={edit.trim.end} onSet={setEnd} />
        {!whole && <button type="button" className="link small" onClick={() => setPad((p) => p * 3)}>Show more of the video</button>}
      </div>
      {cutsInside(edit).length > 0 && <p className="muted small">{cutsInside(edit).length} cut{cutsInside(edit).length === 1 ? "" : "s"} marked in red.{" "}
        <button type="button" className="link" onClick={() => cutsInside(edit).forEach(onRestore)}>Restore all</button></p>}
    </div>
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
