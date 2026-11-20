"use client";
// Clip a long video: everything a clipping job takes, on one screen, with the price beside it.
// Left: the source (its picture, language and game), the part to clip, the layout, the template, then every
// setting grouped the way a clipper thinks about them. Right: the summary, the price from the server and the
// button. Used for a pasted link (LinkChooser) and an uploaded file (the project page).
//
// Every control is either wired to an option GET /v1/options lists (and only listed options are ever sent), or
// shown greyed out with the Coming soon mark, costs nothing and sends nothing. Prices come only from the
// caller's server quote (`price`). The parent decides what Create does (import then clip, or clip an upload).
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { clock } from "@/lib/api";
import { useLanguages } from "@/lib/languages";
import { allows, inside, layoutsFor, Listed, offeredBucket, onlyListed, RENDER } from "@/lib/options";
import { extrasFrom, gameName, gameOf, isPreset, loadCustom, loadTemplates, Look, lookFrom, Saved, startLook, tidy } from "@/lib/templates";
import { Icon } from "../Icon";
import { Span } from "../RangeSlider";
import { useDash } from "../Shell";
import { LayoutPicker } from "./Layout";
import { CARD, InlineSelect, LABEL, SettingRow, Switch } from "./parts";
import { RangeStrip } from "./Range";
import { CaptionStyles, HookTones } from "./Styles";

export type SetupSource = { title: string; duration: number | null; height?: number | null; thumb?: string | null; video?: string | null;
  badge?: string | null; detail?: string | null;
  // What the link preview says about the video (platform, type, status, creator, game…), only what the API sent.
  facts?: [string, string][] };
// The price, only ever from the server: a quote for this exact request, or the link preview's estimate.
export type Price = { state: "asking" } | { state: "ok"; credits: number; note?: string } | { state: "failed"; message: string } | { state: "unknown"; text: string };

const AUTO = "0-90";
const LENGTHS: Record<string, string> = { "0-90": "Auto (up to 60 s)", "0-30": "Under 30 s", "30-60": "30 to 60 s" };
const shortest = (b: string) => +b.split("-")[0] || 0;
const MIN_SPAN = 10;
const QUICK = ["Funny reactions", "Clutch plays", "Epic fails", "Chases and crashes", "Chat going wild"];
const DISPLAY: Record<string, string> = { translation: "Translated only", both: "Both languages" };
const languageName = (code: string) => { try { return new Intl.DisplayNames(["en"], { type: "language" }).of(code) || code; } catch { return code; } };

export function JobSetup({ source, listed, template, preset, price, onOptions, onCreate, onRemove, consent, step, problem, afterProblem, header, busy }: {
  source: SetupSource; listed: Listed; template?: string; preset?: Partial<Look>; price: Price; onOptions: (o: Record<string, unknown>) => void; onCreate: (o: Record<string, unknown>) => void;
  onRemove: () => void; consent?: { checked: boolean; onChange: (on: boolean) => void; text: string }; step?: { text: string; pct?: number } | null;
  problem?: string; afterProblem?: React.ReactNode; header?: React.ReactNode; busy?: boolean }) {
  const { me } = useDash();
  const langs = useLanguages();
  const has = (k: string) => k in listed;
  // Home's polish chips arrive as `preset` (captions, speech cleanup, hook); anything else starts from our defaults.
  const [look, setLook] = useState<Look>(() => ({ ...startLook(listed), ...preset, ...(has("caption_emoji") && preset?.captions !== false ? {} : { caption_emoji: false }) }));
  const onLook = (c: Partial<Look>) => setLook((x) => ({ ...x, ...c }));
  const [f, setF] = useState({ limit: null as number | null, duration: allows(listed, "duration", AUTO) ? AUTO : String(listed.duration?.values?.[0] || AUTO),
    prompt: "", range: null as Span | null, source_lang: "", chat_region: "none", hook_style: String(listed.hook_style?.default || "serious"),
    translate: false, target_lang: "", caption_display: "translation", game: "" });
  const set = (c: Partial<typeof f>) => setF((x) => ({ ...x, ...c }));
  const [templates, setTemplates] = useState<{ presets: any[]; games: any[] }>({ presets: [], games: [] }), [saved, setSaved] = useState<Saved[] | null>(null);
  const [picked, setPicked] = useState("");                      // "" none, "t:<id>" a template, "s:<id>" a saved look
  const [open, setOpen] = useState(true);

  const allTemplates = [...templates.presets, ...templates.games];
  const chosen = picked.startsWith("t:") ? allTemplates.find((t) => t.id === picked.slice(2)) : undefined;
  function pick(v: string) {
    setPicked(v);
    const item = v.startsWith("t:") ? allTemplates.find((t) => t.id === v.slice(2)) : v.startsWith("s:") ? saved?.find((s) => s.id === v.slice(2)) : null;
    if (!item) return;
    setLook((x) => ({ ...x, ...lookFrom(item, listed, x.aspect) }));
    if (typeof item.duration === "string" && allows(listed, "duration", item.duration) && offeredBucket(item.duration) && (!source.duration || shortest(item.duration) <= source.duration))
      set({ duration: item.duration });
    if (typeof item.game === "string") set({ game: item.game });
  }
  useEffect(() => {
    loadTemplates().then((t) => {
      setTemplates(t);
      const wanted = template && [...t.presets, ...t.games].find((x) => x.id === template);       // "Use template" in the gallery
      if (wanted) { setPicked(`t:${wanted.id}`); setLook((x) => ({ ...x, ...lookFrom(wanted, listed, x.aspect) })); }
    }).catch(() => {});
    loadCustom().then(setSaved).catch(() => setSaved(null));
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const setAspect = (aspect: string) => {
    const layout = layoutsFor(listed, aspect).includes(look.layout) ? look.layout : "auto";
    onLook({ aspect, layout, ...(layout === look.layout ? {} : { camera: null, split_ratio: null }) });
  };

  // Every setting is stated, so a change to the API's defaults never changes what this screen makes. Then only
  // the names the API lists are sent.
  const options = useMemo(() => {
    const o: Record<string, unknown> = { facecam_region: "auto", zoom: 1, resolution: "1080", render: RENDER, chat_region: f.chat_region,
      ...look, template: chosen ? chosen.id : null, ...(chosen ? extrasFrom(chosen, listed) : {}),
      prompt: f.prompt.trim() || null, range: f.range, source_lang: f.source_lang || null, limit: f.limit, duration: f.duration };
    if (look.hook_overlay) o.hook_style = f.hook_style;
    o.target_lang = f.translate && f.target_lang ? f.target_lang : null;
    if (f.translate && f.target_lang) o.caption_display = f.caption_display;
    if (!has("duration")) o.clip_length = 30;
    if (!has("limit") && f.limit !== null) o.max_clips = Math.min(f.limit, listed.max_clips?.maximum ?? f.limit);
    return onlyListed(listed, o);
  }, [look, f, chosen, listed]);   // eslint-disable-line react-hooks/exhaustive-deps
  const key = JSON.stringify(options);
  useEffect(() => { onOptions(options); }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- price and the button ----------
  const credits = price.state === "ok" ? price.credits : null;
  const short = credits !== null && credits > me.credits ? credits - me.credits : 0;
  // Create waits for a price from the server: no quote, no start.
  const ready = !busy && !step && price.state === "ok" && !short && me.email_verified && (!consent || consent.checked);

  const span = f.range ? f.range.end - f.range.start : source.duration;
  const games = [...new Set(allTemplates.map(gameOf))].filter((g) => g !== "other");
  const forGame = (t: any) => !f.game || gameOf(t) === f.game;
  const spoken: string[] = listed.source_lang?.values || langs?.languages.filter((l) => l.transcribe).map((l) => l.code) || [];
  const translateOn = has("target_lang") && !!langs?.translation;
  const lengths = [AUTO, ...(listed.duration?.values || []).filter((b: string) => b !== AUTO)].filter((b) => allows(listed, "duration", b) && offeredBucket(b));
  const limits = inside(listed.limit || listed.max_clips, [1, 3, 5, 10, 20, 30, 50]);
  const promptMax = listed.prompt?.maxLength ?? 300;
  const res = source.height ? (source.height >= 2160 ? "4K" : source.height >= 1440 ? "1440p" : `${source.height}p`) : null;
  const included: [string, boolean][] = [["Clipping", true], ["Captions", look.captions], ["Auto hook", look.hook_overlay], ["Open on the peak", look.flash_forward],
    ["Speech cleanup", look.tighten], ["Auto zoom", look.punch_zoom], ["Caption translation", !!options.target_lang]];
  const total = price.state === "ok" ? `${price.credits.toLocaleString()} credit${price.credits === 1 ? "" : "s"}` : price.state === "asking" ? "Working it out…"
    : price.state === "failed" ? "No price yet" : "Shown before you start";

  // After a failed import the way forward is the action under the problem (Upload original video): Create steps back
  // to an outline button and says it tries the link again.
  const create = <button type="button" className={`btn w-full ${afterProblem ? "ghost" : "primary"}`} disabled={!ready} onClick={() => onCreate(options)}>
    {step ? "Working…" : afterProblem ? "Try the link again" : "Create"}</button>;

  return (
    <div className="wide mx-auto grid w-full max-w-[1320px] grid-cols-[minmax(0,1fr)] gap-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <button type="button" onClick={onRemove} aria-label="Back" className="grid h-9 w-9 flex-none cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted hover:bg-chip hover:text-text"><Icon name="back" size={20} /></button>
          <h1 title={source.title} className="m-0 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[20px] font-semibold tracking-[-0.01em]">{source.title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2 text-[15px] tabular-nums" title="Your credits"><Icon name="bolt" size={17} className="text-lime" />{me.credits.toLocaleString()}<span className="sr-only"> credits</span></span>
          <Link href="/dashboard/pricing/" className="btn small ghost">Add credits</Link>
        </div>
      </header>
      {header}

      <div className="grid grid-cols-[minmax(0,1fr)_360px] items-start gap-8 mid:grid-cols-[minmax(0,1fr)]">
        <div className="grid min-w-0 gap-5">
          {/* The source and the part of it to clip. */}
          <section className={`${CARD} grid grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] gap-6 narrow:grid-cols-[minmax(0,1fr)]`} aria-label="Your video">
            <div className="grid content-start gap-2 rounded-16 border border-solid border-line-soft bg-surface p-2">
              <div className="relative aspect-video overflow-hidden rounded-12 bg-black">
                {source.thumb ? <img src={source.thumb} alt="" className="h-full w-full object-cover" />
                  : <span className="grid h-full w-full place-items-center text-[13px] text-muted">{source.badge ? `${source.badge}: no picture for this video` : "No picture for this video"}</span>}
                {(res || source.badge) && <span className="absolute left-2 top-2 rounded-8 bg-[rgba(0,0,0,.66)] px-2 py-[2px] text-[12px] font-medium [backdrop-filter:blur(6px)]">{res || source.badge}</span>}
                {source.duration && <span className="absolute bottom-2 right-2 rounded-8 bg-[rgba(0,0,0,.66)] px-2 py-[2px] text-[12px] font-medium tabular-nums">{clock(source.duration)}</span>}
                <button type="button" onClick={onRemove} aria-label="Choose a different video" title="Choose a different video"
                  className="absolute right-2 top-2 grid h-9 w-9 cursor-pointer place-items-center rounded-full border-0 bg-[rgba(0,0,0,.6)] text-text hover:bg-[rgba(0,0,0,.85)]"><Icon name="close" size={17} /></button>
              </div>
              {source.facts?.length ? <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 px-1 text-[12.5px]">{source.facts.map(([k, v]) => <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-label" title={v}>{v}</dd></div>)}</dl>
                : source.detail && <p className="m-0 overflow-hidden text-ellipsis whitespace-nowrap px-1 text-[12.5px] text-muted">{source.detail}</p>}
              <div className="flex flex-wrap gap-1">
                {spoken.length > 0 && <InlineSelect label="Speech" value={f.source_lang} shown={f.source_lang ? languageName(f.source_lang) : "Auto"} onChange={(v) => set({ source_lang: v })}>
                  {listed.source_lang?.nullable !== false && <option value="">Detect it</option>}
                  {spoken.map((c) => <option key={c} value={c}>{langs?.languages.find((l) => l.code === c)?.name || languageName(c)}</option>)}</InlineSelect>}
                <InlineSelect label="Templates for" value={f.game} shown={f.game ? gameName(f.game) : "Every game"} onChange={(v) => set({ game: v })}>
                  <option value="">Every game</option>{games.map((g) => <option key={g} value={g}>{gameName(g)}</option>)}</InlineSelect>
              </div>
            </div>
            <div className="grid content-start gap-4">
              <div className="flex items-center justify-between gap-2"><h2 className="m-0 text-[15px] font-semibold">Adjust range</h2>
                <span className="text-[12.5px] text-muted">Clips come only from this part</span></div>
              {has("range") ? <RangeStrip duration={source.duration} value={f.range} gap={MIN_SPAN} video={source.video} thumb={source.thumb}
                onChange={(range) => { const fits = shortest(f.duration) <= (range ? range.end - range.start : source.duration || Infinity); set({ range, ...(fits ? {} : { duration: AUTO }) }); }} />
                : <p className="m-0 flex items-center gap-2 text-[13px] text-muted">Picking a part of the video <ComingSoonBadge short /></p>}
              <div className="flex flex-wrap items-center gap-1">
                <LayoutPicker listed={listed} look={look} onLook={onLook} setAspect={setAspect} chat={f.chat_region} onChat={(v) => set({ chat_region: v })} />
                <span className="inline-flex min-h-[36px] items-center gap-2 px-3 text-[14px] text-fg-2" aria-disabled="true"><Icon name="upload" size={16} />Upload SRT <ComingSoonBadge short /></span>
              </div>
            </div>
          </section>

          {/* The template and the settings. */}
          <section className={`${CARD} grid gap-2`} aria-label="Settings">
            <div className="grid grid-cols-2 gap-3 narrow:grid-cols-1">
              <label className="relative m-0 flex min-h-[72px] cursor-pointer items-center gap-3 rounded-16 bg-surface px-4 font-normal hover:bg-raised">
                <span className="grid h-10 w-10 flex-none place-items-center rounded-12 bg-text text-bg" aria-hidden="true"><Icon name="grid" size={20} /></span>
                <span className="grid min-w-0 flex-1"><span className="text-[15px] font-medium text-text">Template</span>
                  <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] text-muted">{chosen?.name || "None: our defaults"}</span></span>
                <Icon name="chevron" size={18} className="text-muted" />
                <select value={picked} onChange={(e) => pick(e.target.value)} aria-label="Template" className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0">
                  <option value="">None: our defaults</option>
                  {templates.presets.length > 0 && <optgroup label="Game types">{templates.presets.map((t) => <option key={t.id} value={`t:${t.id}`}>{t.name || tidy(t.id)}</option>)}</optgroup>}
                  {(f.game ? [f.game] : [...games, "other"]).map((g) => { const list = templates.games.filter((t) => gameOf(t) === g && forGame(t) && !isPreset(t));
                    return list.length ? <optgroup key={g} label={gameName(g)}>{list.map((t) => <option key={t.id} value={`t:${t.id}`}>{t.name || tidy(t.id)}</option>)}</optgroup> : null; })}
                </select>
              </label>
              {/* Brand kits are the account's saved looks (GET /v1/templates/custom). Picking one sets the look it holds. */}
              <label className={`relative m-0 flex min-h-[72px] items-center gap-3 rounded-16 bg-surface px-4 font-normal ${saved?.length ? "cursor-pointer hover:bg-raised" : ""}`}>
                <span className="grid h-10 w-10 flex-none place-items-center rounded-12 bg-text text-bg" aria-hidden="true"><Icon name="brand" size={20} /></span>
                <span className="grid min-w-0 flex-1"><span className="text-[15px] font-medium text-text">Brand kit</span>
                  <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] text-muted">{saved?.find((k) => `s:${k.id}` === picked)?.name
                    || (saved?.length ? "No brand kit" : "No brand kits saved yet")}</span></span>
                {!!saved?.length && <Icon name="chevron" size={18} className="text-muted" />}
                {!!saved?.length && <select value={picked.startsWith("s:") ? picked : ""} onChange={(e) => pick(e.target.value)} aria-label="Brand kit"
                  className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0">
                  <option value="">No brand kit</option>{saved.map((k) => <option key={k.id} value={`s:${k.id}`}>{k.name}</option>)}</select>}
              </label>
            </div>
            <p className="m-0 px-1 pt-1 text-[13px] text-muted">A template tunes what we look for in a game; a brand kit is a look you saved. Either one sets the layout, captions and edits below, and you can still change each.</p>
            <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex w-max cursor-pointer items-center gap-1 border-0 bg-transparent px-1 py-2 font-sans text-[14px] text-muted hover:text-text">
              Settings <Icon name="chevron" size={16} className={open ? "rotate-180" : ""} /></button>

            {open && <div className="grid divide-x-0 divide-y divide-solid divide-line-soft">
              <SettingRow icon="scissors" name="Clipping" hint="Finds the best moments and cuts them into clips with an AI rating." under={<div className="grid gap-3 pl-12 narrow:pl-0">
                <div className="flex flex-wrap gap-1">
                  {limits.length > 0 && <InlineSelect label="AI picks" value={f.limit === null ? "" : String(f.limit)} shown={f.limit === null ? "Auto" : f.limit === 1 ? "The best one" : `The best ${f.limit}`}
                    onChange={(v) => set({ limit: v ? +v : null })}><option value="">Auto: every clip that makes the cut</option>
                    {limits.map((n) => <option key={n} value={n}>{n === 1 ? "The best one" : `The best ${n}`}</option>)}</InlineSelect>}
                  {has("duration") && <InlineSelect label="Clip length" value={f.duration} shown={LENGTHS[f.duration] || f.duration} onChange={(v) => set({ duration: v })}>
                    {lengths.map((b) => <option key={b} value={b} disabled={!!span && shortest(b) > span}>{LENGTHS[b] || b}</option>)}</InlineSelect>}
                </div>
                {has("prompt") && <div className="grid gap-2">
                  <label htmlFor="setup-prompt" className="m-0 flex items-center justify-between gap-2 text-[13px] font-normal text-muted">Moments to include (optional)
                    <span className="tabular-nums">{f.prompt.length} / {promptMax}</span></label>
                  <input id="setup-prompt" value={f.prompt} maxLength={promptMax} placeholder="Example: every time a chase ends in a crash" onChange={(e) => set({ prompt: e.target.value })}
                    className="w-full rounded-full px-[18px]" />
                  <div className="flex flex-wrap gap-2" aria-label="Ideas">{QUICK.map((q) => <button key={q} type="button" aria-pressed={f.prompt === q} onClick={() => set({ prompt: f.prompt === q ? "" : q })}
                    className="cursor-pointer rounded-full border border-solid border-line bg-transparent px-3 py-[6px] font-sans text-[12.5px] text-label hover:border-line-strong aria-pressed:border-text aria-pressed:text-text">{q}</button>)}</div>
                </div>}
              </div>}><Switch on label="Clipping" disabled /></SettingRow>

              <h3 className={`m-0 pt-5 ${LABEL}`}>Essentials</h3>
              {has("captions") ? <SettingRow icon="captions" name="Captions" hint="Word-by-word captions burned into each clip." under={look.captions && <div className="grid gap-3">
                  {has("caption_style") && <CaptionStyles styles={listed.caption_style.values || [look.caption_style]} value={look.caption_style} onChange={(s) => onLook({ caption_style: s })} />}
                  <div className="flex flex-wrap items-center gap-1">
                    {has("caption_position") && <InlineSelect label="Position" value={look.caption_position} shown={tidy(look.caption_position === "auto" ? "Automatic" : look.caption_position)}
                      onChange={(v) => onLook({ caption_position: v })}>{(listed.caption_position.values || []).map((p: string) => <option key={p} value={p}>{p === "auto" ? "Automatic" : p === "seam" ? "Between the panels" : tidy(p)}</option>)}</InlineSelect>}
                    {has("censor") && <label className="m-0 inline-flex min-h-[36px] cursor-pointer items-center gap-2 px-3 text-[14px] font-normal text-label"><input type="checkbox" checked={look.censor} onChange={(e) => onLook({ censor: e.target.checked })} />Bleep swears</label>}
                  </div>
                </div>}><Switch on={look.captions} label="Captions" onChange={(v) => onLook({ captions: v, ...(v ? {} : { caption_emoji: false }) })} /></SettingRow>
                : <SettingRow icon="captions" name="Captions" soon />}
              {has("hook_overlay") ? <SettingRow icon="hook" name="Auto hook" hint="A short opening line on screen for the first seconds." under={look.hook_overlay && has("hook_style") &&
                  <HookTones tones={listed.hook_style.values || []} catalogue={listed.hook_style.catalogue} value={f.hook_style} onChange={(s) => set({ hook_style: s })} />}>
                  <Switch on={look.hook_overlay} label="Auto hook" onChange={(v) => onLook({ hook_overlay: v })} /></SettingRow>
                : <SettingRow icon="hook" name="Auto hook" soon />}
              {has("flash_forward") && <SettingRow icon="rewind" name="Open on the peak" hint="Starts with a flash of the best moment, then plays from the start.">
                <Switch on={look.flash_forward} label="Open on the peak" onChange={(v) => onLook({ flash_forward: v })} /></SettingRow>}
              <SettingRow icon="shapes" name="Motion graphics" soon />
              {has("caption_emoji") ? <SettingRow icon="smile" name="AI emojis" hint={look.captions ? "Fitting emojis in the captions." : "Needs captions."}>
                <Switch on={look.captions && look.caption_emoji} label="AI emojis" disabled={!look.captions} onChange={(v) => onLook({ caption_emoji: v })} /></SettingRow>
                : <SettingRow icon="smile" name="AI emojis" soon />}
              <SettingRow icon="image" name="Auto B-roll" soon />

              <h3 className={`m-0 pt-5 ${LABEL}`}>Sound sharp</h3>
              {has("tighten") ? <SettingRow icon="scissors" name="Speech cleanup" hint="Removes long pauses and filler words.">
                <Switch on={look.tighten} label="Speech cleanup" onChange={(v) => onLook({ tighten: v })} /></SettingRow>
                : <SettingRow icon="scissors" name="Speech cleanup" soon />}
              <SettingRow icon="volume" name="Enhance audio" soon />
              <SettingRow icon="wave" name="Auto sound effects" soon />

              <h3 className={`m-0 pt-5 ${LABEL}`}>Look good</h3>
              {has("punch_zoom") ? <SettingRow icon="expand" name="Auto zoom" hint="A quick punch-in on the gameplay at the big moments.">
                <Switch on={look.punch_zoom} label="Auto zoom" onChange={(v) => onLook({ punch_zoom: v })} /></SettingRow>
                : <SettingRow icon="expand" name="Auto zoom" soon />}
              <SettingRow icon="transitions" name="Auto transitions" soon />
              <SettingRow icon="palette" name="Auto colour correction" soon />
              <SettingRow icon="eye" name="Eye-contact correction" soon />

              <h3 className={`m-0 pt-5 ${LABEL}`}>Translate</h3>
              <SettingRow icon="mic" name="Voice dubbing" soon />
              {translateOn ? <SettingRow icon="translate" name="Caption translation" hint={look.captions ? "Captions in another language." : "Needs captions."}
                under={f.translate && <div className="flex flex-wrap gap-1 pl-12 narrow:pl-0">
                  <InlineSelect label="Into" value={f.target_lang} shown={f.target_lang ? languageName(f.target_lang) : "Choose"} onChange={(v) => set({ target_lang: v })}>
                    <option value="">Choose a language</option>{(listed.target_lang?.values || []).map((c: string) => <option key={c} value={c}>{languageName(c)}</option>)}</InlineSelect>
                  {has("caption_display") && <InlineSelect label="Show" value={f.caption_display} shown={DISPLAY[f.caption_display] || f.caption_display} onChange={(v) => set({ caption_display: v })}>
                    {(listed.caption_display.values || []).filter((v: string) => v !== "original").map((v: string) => <option key={v} value={v}>{DISPLAY[v] || tidy(v)}</option>)}</InlineSelect>}
                </div>}><Switch on={f.translate && look.captions} disabled={!look.captions} label="Caption translation" onChange={(v) => set({ translate: v })} /></SettingRow>
                : <SettingRow icon="translate" name="Caption translation" soon />}
            </div>}
          </section>
        </div>

        {/* The summary: what runs, the server's price, and the button. */}
        <aside aria-label="Summary" className={`${CARD} sticky top-[88px] grid gap-4 mid:static`}>
          <h2 className="m-0 text-[16px] font-semibold">Summary</h2>
          <dl className="m-0 grid gap-3 text-[14px]">
            <div className="flex items-baseline justify-between gap-3"><dt className="text-muted">Video processing</dt>
              <dd className="m-0 text-right tabular-nums">{price.state === "ok" ? `${price.credits.toLocaleString()} credits` : price.state === "asking" ? "…" : "—"}</dd></div>
            {included.filter(([, on]) => on).map(([name]) => <div key={name} className="flex items-baseline justify-between gap-3"><dt className="text-muted">{name}</dt><dd className="m-0 text-fg-2">Included</dd></div>)}
          </dl>
          <div className="flex items-center justify-between gap-3 border-0 border-t border-solid border-line-soft pt-4 text-[14px]">
            <span>Premium features</span><span className="flex items-center gap-2 text-fg-2">Top clips only <ComingSoonBadge short /></span></div>
          <div className="flex items-baseline justify-between gap-3 border-0 border-t border-solid border-line-soft pt-4">
            <span className="text-[15px] font-medium">Total</span>
            <span className="inline-flex items-center gap-1 text-[17px] font-semibold tabular-nums"><Icon name="bolt" size={17} className="text-lime" />{total}</span></div>
          {price.state === "ok" && price.note && <p className="m-0 text-[12.5px] text-muted">{price.note} A failed or cancelled job gives its credits back.</p>}
          {price.state === "unknown" && <p className="m-0 text-[12.5px] text-muted">{price.text}</p>}
          {price.state === "failed" && <p className="m-0 text-[12.5px] text-warn">No price yet: {price.message}</p>}
          {consent && <label className="check m-0 text-[13.5px] text-label"><input type="checkbox" checked={consent.checked} disabled={!!step} onChange={(e) => consent.onChange(e.target.checked)} /><span>{consent.text}</span></label>}
          {problem && <p className="error m-0" role="alert">{problem}</p>}
          {afterProblem}
          {step ? <div className="grid gap-2" role="status"><p className="m-0 text-[14px]">{step.text}{typeof step.pct === "number" ? ` ${step.pct}%` : ""}</p>
            {typeof step.pct === "number" && <progress max={100} value={step.pct} aria-label="Progress" />}</div> : create}
          {!consent && <p className="m-0 text-center text-[12.5px] text-muted">You confirmed you own this video, or have permission to clip it, when you uploaded it.</p>}
          {!!short && <div className="grid gap-2 rounded-16 bg-[rgba(255,182,72,.1)] p-4 text-[14px]" role="alert">
            <p className="m-0 flex items-center gap-2 text-warn"><Icon name="bolt" size={16} />Not enough credits. You need {short.toLocaleString()} more.</p>
            <Link href="/dashboard/pricing/" className="font-medium text-text underline">Add credits</Link></div>}
          {!me.email_verified && <p className="m-0 text-[12.5px] text-warn">Confirm your email to start making clips.</p>}
        </aside>
      </div>

      {/* On a phone the total and the button stay in reach. */}
      {/* A problem (and what to do about it, like Upload original video) shows here too: the summary is far below. */}
      <div className="sticky bottom-[calc(var(--app-bottom-bar,theme(spacing.tabbar))+env(safe-area-inset-bottom))] z-30 hidden gap-3 rounded-16 border border-solid border-line bg-[rgba(20,20,20,.96)] p-3 shadow-bar [backdrop-filter:blur(10px)] narrow:grid">
        {problem && <p className="error m-0 text-[13px]" role="alert">{problem}</p>}
        {afterProblem}
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-1 text-[15px] font-semibold tabular-nums"><Icon name="bolt" size={16} className="text-lime" />{total}</span>
          <div className="w-[150px]">{step ? <span className="text-[13px] text-muted">{step.text}</span> : create}</div>
        </div>
      </div>
    </div>
  );
}
