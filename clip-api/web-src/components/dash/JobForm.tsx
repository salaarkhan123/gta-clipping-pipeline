"use client";
import { useCallback, useEffect, useId, useState } from "react";
import { api, clock } from "@/lib/api";
import { useQuote } from "@/lib/exporting";
import { allows, inside, Listed, onlyListed } from "@/lib/options";
import { QUOTE, useRoutes } from "@/lib/routes";
import { AS_IT_IS, extrasFrom, loadCustom, loadTemplates, Look, lookFrom, Saved, startLook } from "@/lib/templates";
import { Icon } from "./Icon";
import { Picked, PreEdit, Templates } from "./PreEdit";
import { RangeSlider, Span } from "./RangeSlider";
import { useDash } from "./Shell";
import { StartRow } from "./StartRow";

// Clip length buckets in plain words. "0-90" is the automatic one and comes first.
const AUTO = "0-90";
const BUCKETS: Record<string, string> = { "0-90": "Auto (under 90 s)", "0-30": "Under 30 seconds", "30-60": "30 to 60 seconds", "60-90": "60 to 90 seconds",
  "90-180": "1½ to 3 minutes", "180-300": "3 to 5 minutes" };
// Clip lengths offered: the automatic one and the buckets that end at 60 s or sooner (owner, 2026-11-18).
export const offeredBucket = (b: string) => b === AUTO || +b.split("-")[1] <= 60;
const bucketName = (b: string) => BUCKETS[b] || `${b.replace("-", " to ")} seconds`;
const shortest = (b: string) => +b.split("-")[0] || 0;
const QUICK = ["Funny reactions", "Clutch wins", "Epic fails", "Emotional moments", "High-energy scenes"];
const CHAT: [string, string][] = [["none", "Not shown"], ["top-right", "Top right"], ["top-left", "Top left"], ["top-center", "Top centre"],
  ["bottom-right", "Bottom right"], ["bottom-left", "Bottom left"]];
const MIN_SPAN = 10;      // the shortest part of a video the API will search (its shortest clip)
// The export size the dashboard asks for. No plan exports above it today, and the API never goes above the
// video's own size or the plan's limit.
const RESOLUTION = "1080";
// New website jobs start with previews (the API's own default stays "full" for API customers).
export const RENDER = "preview";
const languageName = (code: string) => { try { return new Intl.DisplayNames(["en"], { type: "language" }).of(code) || code; } catch { return code; } };

// Clip Maker: what to look for, where, how long, and what is done to each clip. Built from what the API lists:
// a control is here only when its option is accepted, and only listed options are sent.
export function JobForm({ upload, listed, onStarted, template }: { upload: any; listed: Listed; onStarted: (job: any) => void; template?: string }) {
  const { reloadMe, fail } = useDash();
  const has = (k: string) => k in listed;
  // No clip cap by default: the server returns every clip that clears its quality bar. A cap is the user's choice.
  const [f, setF] = useState({ max_clips: null as number | null, clip_length: 30, duration: allows(listed, "duration", AUTO) ? AUTO : (listed.duration?.values?.[0] as string) || AUTO,
    limit: null as number | null, chat_region: "none", prompt: "", range: null as Span | null, source_lang: "" });
  const set = (change: Partial<typeof f>) => setF((x) => ({ ...x, ...change }));
  const [pre, setPre] = useState(true), [look, setLook] = useState<Look>(() => startLook(listed)), [picked, setPicked] = useState<Picked>(null);
  const [templates, setTemplates] = useState<Templates>({ presets: [], games: [] }), [saved, setSaved] = useState<Saved[] | null>(null);
  const [starting, setStarting] = useState(false);
  const ids = useId();
  const chosen = picked?.kind === "template" ? [...templates.presets, ...templates.games].find((t) => t.id === picked.id) : undefined;

  // Choosing a tile fills the look from it (and the clip length, for a game template). Everything can still be changed.
  function pick(kind: "template" | "saved", item: any | null) {
    if (!item) { setPicked(null); return; }
    setPicked({ kind, id: String(item.id) });
    setLook((x) => ({ ...x, ...lookFrom(item, listed, x.aspect) }));
    if (kind !== "template") return;
    const length = item.options?.clip_length;
    if (typeof item.duration === "string" && allows(listed, "duration", item.duration) && offeredBucket(item.duration) && shortest(item.duration) <= upload.duration_sec) set({ duration: item.duration });
    else if (!has("duration") && typeof length === "number" && inside(listed.clip_length, [length]).length) set({ clip_length: length });
  }
  const reloadSaved = useCallback(() => loadCustom().then(setSaved).catch(fail), [fail]);
  useEffect(() => {
    loadTemplates().then((t) => {
      setTemplates(t);
      const wanted = template && [...t.presets, ...t.games].find((x) => x.id === template);     // "Use template" in the gallery
      if (wanted) pick("template", wanted);
    }).catch(() => {});
    reloadSaved();
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  // Every setting is stated, including the ones this form has no control for, so a change to the API's defaults
  // can never change what the dashboard makes. Then only the names the API lists are sent.
  function body() {
    // render "preview": fast small clips to choose from first; each card's Export button renders full quality.
    const options: Record<string, unknown> = { facecam_region: "auto", zoom: 1, resolution: RESOLUTION, render: RENDER, chat_region: f.chat_region,
      ...look, ...(pre ? {} : AS_IT_IS), template: pre && chosen ? chosen.id : null, ...(pre && chosen ? extrasFrom(chosen, listed) : {}),
      prompt: f.prompt.trim() || null, range: f.range, source_lang: f.source_lang || null };
    if (has("duration")) options.duration = f.duration; else options.clip_length = f.clip_length;
    if (has("limit")) options.limit = f.limit; else if (f.max_clips !== null) options.max_clips = f.max_clips;
    return { upload_id: upload.upload_id, options: onlyListed(listed, options) };
  }
  // The exact price, asked again as the options change, once the API has POST /v1/clips/quote.
  const known = useRoutes();
  const quote = useQuote(known?.quote ? QUOTE : null, known?.quote ? body() : null);
  async function start() {
    setStarting(true);
    try { onStarted(await api("/v1/clips", { body: body() })); await reloadMe(); }
    catch (e) { fail(e); } finally { setStarting(false); }
  }

  const span = f.range ? f.range.end - f.range.start : upload.duration_sec;
  const thumb = upload.thumb_url || upload.clips?.find((c: any) => c.thumb_url)?.thumb_url;
  const limits = inside(listed.limit, [1, 3, 5, 10, 20, 30, 50]), langs: string[] = listed.source_lang?.values || [];
  const promptMax = listed.prompt?.maxLength ?? 300;
  return (
    <>
      <div className="src-card">
        <span className="src-thumb" aria-hidden="true">{thumb ? <img src={thumb} alt="" /> : <Icon name="film" size={26} />}</span>
        <span className="src-text"><strong>{upload.filename}</strong>
          <span className="muted">{clock(upload.duration_sec)} long{upload.width && upload.height ? ` · ${upload.width}×${upload.height}` : ""}</span></span>
      </div>

      <div className="options">
        {langs.length > 0 && <label>Language spoken<select value={f.source_lang} onChange={(e) => set({ source_lang: e.target.value })}>
          {listed.source_lang.nullable !== false && <option value="">Detect it for me</option>}
          {langs.map((l) => <option key={l} value={l}>{languageName(l)}</option>)}</select></label>}
        {has("duration")
          ? <label>Clip length<select value={f.duration} onChange={(e) => set({ duration: e.target.value })}>
              {[AUTO, ...(listed.duration.values || []).filter((b: string) => b !== AUTO)].filter((b) => allows(listed, "duration", b) && offeredBucket(b)).map((b) => (
                <option key={b} value={b} disabled={shortest(b) > span}>{bucketName(b)}{shortest(b) > span ? " (longer than this video)" : ""}</option>))}</select></label>
          : has("clip_length") && <label>Clip length<select value={f.clip_length} onChange={(e) => set({ clip_length: +e.target.value })}>
              {inside(listed.clip_length, [15, 20, 30, 40, 45, 60]).map((n) => <option key={n} value={n}>{n} seconds</option>)}</select></label>}
        {has("limit")
          ? <label>How many clips<select value={f.limit ?? ""} onChange={(e) => set({ limit: e.target.value ? +e.target.value : null })}>
              {listed.limit.nullable !== false && <option value="">Automatic: every clip that makes the cut</option>}
              {limits.map((n) => <option key={n} value={n}>{n === 1 ? "The best one" : `The best ${n}`}</option>)}</select></label>
          : has("max_clips") && <label>How many clips<select value={f.max_clips ?? ""} onChange={(e) => set({ max_clips: e.target.value ? +e.target.value : null })}>
              <option value="">Automatic: every clip that makes the cut</option>
              {inside(listed.max_clips, [1, 3, 5, 10, 20, 30, 50]).map((n) => <option key={n} value={n}>{n === 1 ? "The best one" : `At most ${n}`}</option>)}</select></label>}
        {has("chat_region") && <label>Chat on screen<select value={f.chat_region} onChange={(e) => set({ chat_region: e.target.value })}>
          {CHAT.filter(([v]) => allows(listed, "chat_region", v)).map(([v, name]) => <option key={v} value={v}>{name}</option>)}</select></label>}
      </div>

      {has("prompt") && <div className="ask">
        <label htmlFor={`${ids}prompt`}>What moments do you want to find? <small>Optional</small></label>
        <input id={`${ids}prompt`} value={f.prompt} maxLength={promptMax} placeholder="Say it your way, like: every time a chase ends in a crash"
          aria-describedby={`${ids}count`} onChange={(e) => set({ prompt: e.target.value })} />
        <div className="ask-row">
          <ul className="quick" aria-label="Quick picks">
            {QUICK.map((q) => <li key={q}><button type="button" className="chip pick" aria-pressed={f.prompt === q} onClick={() => set({ prompt: f.prompt === q ? "" : q })}>{q}</button></li>)}
          </ul>
          <span id={`${ids}count`} className="muted small">{f.prompt.length} / {promptMax}</span>
        </div>
      </div>}

      {has("range") && upload.duration_sec > MIN_SPAN && <div className="ask" role="group" aria-labelledby={`${ids}range`}>
        <p id={`${ids}range`} className="ask-title">Where to find clips</p>
        <p className="muted small">Drag the two handles, or type the times, to search only one part of the video.</p>
        <RangeSlider duration={upload.duration_sec} value={f.range} gap={MIN_SPAN} onChange={(range) => {
          // A length that no longer fits the chosen part falls back to the automatic one.
          const fits = shortest(f.duration) <= (range ? range.end - range.start : upload.duration_sec);
          set({ range, ...(fits ? {} : { duration: AUTO }) });
        }} />
      </div>}

      {(has("vertical") || has("captions")) && <PreEdit listed={listed} on={pre} onToggle={setPre} look={look} onLook={(change) => setLook((x) => ({ ...x, ...change }))}
        picked={picked} onPick={pick} templates={templates} saved={saved} onSavedChange={reloadSaved} />}

      <StartRow upload={upload} label="Make clips" busy={starting} perMinute onStart={start} quote={quote} />
    </>
  );
}
