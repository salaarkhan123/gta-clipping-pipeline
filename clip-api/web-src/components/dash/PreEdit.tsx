"use client";
import { useId, useState } from "react";
import { Listed, layoutsFor } from "@/lib/options";
import { DEFAULT_PANELS, deleteCustom, gameName, gameOf, hasPanels, isPreset, isProvisional, layoutChoices, layoutName, layoutOf, Look, lookFrom,
  lookOptions, mediaUrl, NAME_MAX, renameCustom, saveCustom, Saved, tidy } from "@/lib/templates";
import { Icon, Soon } from "./Icon";
import { LookSketch } from "./LookSketch";
import { useDash } from "./Shell";
import { Tabs } from "./Tabs";

// What is chosen in Presets: a template from the API (a game-type preset or a per-game template) or a saved look.
export type Picked = { kind: "template" | "saved"; id: string } | null;
export type Templates = { presets: any[]; games: any[] };
const ASPECT_NAMES: Record<string, string> = { "9:16": "9:16 vertical", "4:5": "4:5 portrait", "1:1": "1:1 square", "16:9": "16:9 wide" };
const POSITION_NAMES: Record<string, string> = { auto: "Automatic", seam: "Between the panels", lower: "Lower third", center: "Centre" };
const CAMERA_NAMES: Record<string, string> = { top: "Camera on top", bottom: "Camera at the bottom" };
const LIME = "#b8ff3c";
const PROVISIONAL = "Still being checked against real output. The look may change.";

export function AspectSelect({ listed, value, onChange }: { listed: Listed; value: string; onChange: (aspect: string) => void }) {
  return (
    <label>Ratio<select value={value} onChange={(e) => onChange(e.target.value)}>
      {(listed.aspect?.values || [value]).map((a: string) => <option key={a} value={a}>{ASPECT_NAMES[a] || a}</option>)}</select></label>
  );
}

// Pre-editing: what is done to every clip after it is cut. Off leaves the clip as it is. Presets picks a whole
// look in one go; Custom sets each part of it. Both edit the same look, so switching tabs loses nothing.
export function PreEdit({ listed, on, onToggle, look, onLook, picked, onPick, templates, saved, onSavedChange }: {
  listed: Listed; on: boolean; onToggle: (on: boolean) => void; look: Look; onLook: (change: Partial<Look>) => void;
  picked: Picked; onPick: (kind: "template" | "saved", item: any | null) => void; templates: Templates; saved: Saved[] | null; onSavedChange: () => void }) {
  const [tab, setTab] = useState<"presets" | "custom">("presets");
  const title = useId();
  // Changing the ratio keeps the layout when the new ratio takes it; panel sizes go with the layout.
  function setAspect(aspect: string) {
    const layout = layoutsFor(listed, aspect).includes(look.layout) ? look.layout : "auto";
    onLook({ aspect, layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });
  }
  return (
    <section className="preedit" aria-labelledby={title}>
      <div className="preedit-head">
        <div><h3 id={title}>Pre-edit clips</h3>
          <p className="muted small">{on ? "Every clip is edited this way before you get it." : "Off: clips are cut out and left exactly as they are in your video."}</p></div>
        <button type="button" role="switch" aria-checked={on} aria-labelledby={title} className="switch" onClick={() => onToggle(!on)}><span /></button>
      </div>
      {on && <>
        <Tabs label="Pre-editing" panel="preedit-panel" value={tab} onChange={setTab} tabs={[["presets", "Presets"], ["custom", "Custom"]]} />
        <div id="preedit-panel" role="tabpanel" aria-label={tab === "presets" ? "Presets" : "Custom"} className="stack-s">
          {tab === "presets"
            ? <Presets listed={listed} look={look} onLook={onLook} setAspect={setAspect} picked={picked} onPick={onPick} templates={templates} saved={saved} onSavedChange={onSavedChange} />
            : <Custom listed={listed} look={look} onLook={onLook} setAspect={setAspect} />}
        </div>
      </>}
    </section>
  );
}

// ---------- Presets ----------
function Presets({ listed, look, onLook, setAspect, picked, onPick, templates, saved, onSavedChange }: {
  listed: Listed; look: Look; onLook: (change: Partial<Look>) => void; setAspect: (a: string) => void; picked: Picked;
  onPick: (kind: "template" | "saved", item: any | null) => void; templates: Templates; saved: Saved[] | null; onSavedChange: () => void }) {
  const { fail } = useDash();
  const [mine, setMine] = useState(false), [game, setGame] = useState("all");
  const [adding, setAdding] = useState(false), [name, setName] = useState(""), [busy, setBusy] = useState(false);
  const is = (kind: string, id: string) => picked?.kind === kind && picked.id === id;
  // A preset is a layout: it is offered only in a ratio that takes that layout. A game template still tunes what
  // is found when its layout is not available, so it stays and is drawn with the layout it will get.
  const presets = templates.presets.filter((t) => typeof t.layout !== "string" || layoutOf({ layout: t.layout }, listed, look.aspect));
  const games = [...new Set(templates.games.map(gameOf))];
  const shownGames = templates.games.filter((t) => game === "all" || gameOf(t) === game);
  const panels = look.vertical && hasPanels(look.layout) && "camera" in listed && "split_ratio" in listed;

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    try { await saveCustom(name.trim(), lookOptions(look, listed)); setAdding(false); setName(""); onSavedChange(); }
    catch (e) { fail(e); } finally { setBusy(false); }
  }

  return (
    <>
      <div className="options">
        <AspectSelect listed={listed} value={look.aspect} onChange={setAspect} />
        {!mine && games.length > 1 && <label>Game<select value={game} onChange={(e) => setGame(e.target.value)}>
          <option value="all">All games</option>{games.map((g) => <option key={g} value={g}>{gameName(g)}</option>)}</select></label>}
        {saved && <label className="check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /><span>My templates only</span></label>}
      </div>
      {adding && <form className="look-add" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <label className="grow">Name for this look
          <input autoFocus value={name} maxLength={NAME_MAX} placeholder="My stream look" onChange={(e) => setName(e.target.value)} /></label>
        <button className="btn small primary" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save template"}</button>
        <button type="button" className="btn small ghost" onClick={() => setAdding(false)}>Cancel</button>
        <p className="muted small">Saves the look as it is set now: ratio, layout, subtitles and editing. It never saves how many clips, their length or which part of the video.</p>
      </form>}
      <ul className="looks" aria-label="Templates">
        {saved && <li className="look"><button type="button" className="look-pick look-new" onClick={() => setAdding(true)}>
          <span className="look-art"><Icon name="plus" size={26} /></span><strong>Add template</strong><span className="muted small">Save the current look</span></button></li>}
        {(saved || []).map((s) => <SavedTile key={s.id} s={s} listed={listed} aspect={look.aspect} on={is("saved", s.id)}
          onPick={() => onPick("saved", is("saved", s.id) ? null : s)} onChange={onSavedChange} />)}
        {!mine && presets.map((t) => <Tile key={t.id} t={t} listed={listed} aspect={look.aspect} on={is("template", t.id)} onPick={() => onPick("template", is("template", t.id) ? null : t)} />)}
        {!mine && shownGames.map((t) => <Tile key={t.id} t={t} listed={listed} aspect={look.aspect} on={is("template", t.id)} onPick={() => onPick("template", is("template", t.id) ? null : t)} />)}
      </ul>
      {mine && saved && !saved.length && <p className="muted">No saved templates yet. Set a look, then use “Add template” to keep it.</p>}
      {!mine && !saved?.length && !presets.length && !shownGames.length && <p className="muted">No templates to show right now. Set the look yourself under Custom.</p>}
      {panels && <Panels listed={listed} look={look} onLook={onLook} />}
      <p className="muted small">A template sets the look and tunes what we look for in that kind of game. Change any part of it under Custom.</p>
    </>
  );
}

// A template's tile: its own picture when the API has one, otherwise our drawing of the look it gives.
function Tile({ t, listed, aspect, on, onPick }: { t: any; listed: Listed; aspect: string; on: boolean; onPick: () => void }) {
  const [broken, setBroken] = useState(false);
  const poster = mediaUrl(t.preview?.poster), fill = lookFrom(t, listed, aspect);
  const name = t.name || tidy(String(t.id));
  return (
    <li className={`look ${on ? "on" : ""}`}>
      <button type="button" className="look-pick" aria-pressed={on} onClick={onPick}>
        <span className="look-art">
          {poster && !broken ? <img src={poster} alt="" loading="lazy" onError={() => setBroken(true)} />
            : <LookSketch aspect={aspect} layout={fill.layout} camera={fill.camera ?? t.panels?.camera} split={fill.split_ratio ?? t.panels?.split_ratio}
                style={fill.caption_style} captions={fill.captions !== false} />}
          {on && <span className="look-check"><Icon name="check" size={16} /></span>}
        </span>
        <strong title={name}>{name}</strong>
        <span className="look-tags">
          <span className="badge">{isPreset(t) ? "Game type" : gameName(gameOf(t))}</span>
          {isProvisional(t) && <span className="soon-tag" title={PROVISIONAL}>Provisional</span>}
        </span>
      </button>
    </li>
  );
}

// A saved look: pick it, rename it or delete it.
function SavedTile({ s, listed, aspect, on, onPick, onChange }: { s: Saved; listed: Listed; aspect: string; on: boolean; onPick: () => void; onChange: () => void }) {
  const { fail } = useDash();
  const [mode, setMode] = useState<"" | "rename" | "delete">(""), [name, setName] = useState(s.name), [busy, setBusy] = useState(false);
  const fill = lookFrom(s, listed, aspect);
  const run = (work: Promise<unknown>) => { setBusy(true); work.then(() => { setMode(""); onChange(); }).catch(fail).finally(() => setBusy(false)); };
  return (
    <li className={`look ${on ? "on" : ""}`}>
      <button type="button" className="look-pick" aria-pressed={on} onClick={onPick}>
        <span className="look-art">
          <LookSketch aspect={fill.aspect || aspect} layout={fill.layout} camera={fill.camera} split={fill.split_ratio} style={fill.caption_style}
            captions={fill.captions !== false} reframed={fill.vertical !== false} />
          {on && <span className="look-check"><Icon name="check" size={16} /></span>}
        </span>
        <strong title={s.name}>{s.name}</strong>
        <span className="look-tags"><span className="badge">My template</span></span>
      </button>
      {mode === "rename" ? <form className="look-edit" onSubmit={(e) => { e.preventDefault(); if (name.trim()) run(renameCustom(s.id, name.trim())); }}>
          <input autoFocus value={name} maxLength={NAME_MAX} aria-label={`New name for ${s.name}`} onChange={(e) => setName(e.target.value)} />
          <button className="btn small primary" disabled={busy || !name.trim()}>Save</button>
          <button type="button" className="btn small ghost" onClick={() => { setMode(""); setName(s.name); }}>Cancel</button>
        </form>
        : mode === "delete" ? <div className="look-edit" role="group" aria-label={`Delete ${s.name}?`}>
          <span className="small">Delete this template?</span>
          <button type="button" className="btn small ghost danger" disabled={busy} onClick={() => run(deleteCustom(s.id))}>Delete</button>
          <button type="button" className="btn small ghost" onClick={() => setMode("")}>Keep</button>
        </div>
        : <div className="look-tools">
          <button type="button" className="icon-btn" aria-label={`Rename ${s.name}`} title="Rename" onClick={() => setMode("rename")}><Icon name="pencil" size={16} /></button>
          <button type="button" className="icon-btn" aria-label={`Delete ${s.name}`} title="Delete" onClick={() => setMode("delete")}><Icon name="trash" size={16} /></button>
        </div>}
    </li>
  );
}

// ---------- Panels ----------
// Where the camera sits and how the height is shared, for layouts with two panels. Shown only once the API takes both.
function Panels({ listed, look, onLook }: { listed: Listed; look: Look; onLook: (change: Partial<Look>) => void }) {
  const cams: string[] = listed.camera?.values || ["top", "bottom"];
  const lo = listed.split_ratio?.minimum ?? 0.25, hi = listed.split_ratio?.maximum ?? 0.75;
  const share = Math.round((look.split_ratio ?? DEFAULT_PANELS.split_ratio) * 100);
  function setCamera(v: string) {
    if (!v) return onLook({ camera: null, split_ratio: null });
    // Moving the camera to the other side keeps each panel's size.
    const kept = look.split_ratio === null ? (v === "top" ? 0.33 : DEFAULT_PANELS.split_ratio) : look.camera && look.camera !== v ? 1 - look.split_ratio : look.split_ratio;
    onLook({ camera: v, split_ratio: Math.min(hi, Math.max(lo, +kept.toFixed(2))) });
  }
  return (
    <fieldset className="panels">
      <legend>Panels <span className="soon-tag" title={PROVISIONAL}>Provisional</span></legend>
      <div className="panel-sketch" aria-hidden="true"><LookSketch aspect={look.aspect} layout={look.layout} camera={look.camera} split={look.split_ratio}
        style={look.caption_style} captions={look.captions} /></div>
      <div className="stack-s grow">
        <label>Camera<select value={look.camera || ""} onChange={(e) => setCamera(e.target.value)}>
          {listed.camera?.nullable !== false && <option value="">Automatic</option>}
          {cams.map((c) => <option key={c} value={c}>{CAMERA_NAMES[c] || tidy(c)}</option>)}</select></label>
        {look.camera
          ? <label>Split: top {share}%, bottom {100 - share}%
              <input type="range" className="slider" min={lo} max={hi} step={0.01} value={look.split_ratio ?? DEFAULT_PANELS.split_ratio}
                aria-valuetext={`Top panel ${share}%, bottom panel ${100 - share}%`} onChange={(e) => onLook({ split_ratio: +e.target.value })} /></label>
          : <p className="muted small">Automatic uses the layout's own camera position and sizes. Pick a position to set the split yourself.</p>}
        {look.camera && <p className="muted small">The {look.camera === "top" ? "top" : "bottom"} panel is the camera, cropped tight on the person. The other is the gameplay.</p>}
      </div>
    </fieldset>
  );
}

// ---------- Custom ----------
// One line of the checklist: a tick box, and the settings that belong to it while it is ticked.
function Line({ label, hint, checked, onChange, disabled, children }: { label: string; hint?: string; checked: boolean; onChange?: (on: boolean) => void;
  disabled?: boolean; children?: React.ReactNode }) {
  return (
    <li className={`line ${disabled ? "off" : ""}`}>
      <label className="check"><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange?.(e.target.checked)} />
        <span><b>{label}</b>{hint && <small>{hint}</small>}</span></label>
      {checked && children && <div className="line-set">{children}</div>}
    </li>
  );
}

function Custom({ listed, look, onLook, setAspect }: { listed: Listed; look: Look; onLook: (change: Partial<Look>) => void; setAspect: (a: string) => void }) {
  const has = (k: string) => k in listed;
  const styles: string[] = listed.caption_style?.values || [look.caption_style];
  const setLayout = (layout: string) => onLook({ layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });
  return (
    <>
      <p className="muted small">Tick what to apply to every clip.</p>
      <ul className="lines">
        {has("vertical") && <Line label="Resize" hint="Reshape the clip for the feed. Unticked keeps your video's own shape." checked={look.vertical} onChange={(v) => onLook({ vertical: v })}>
          <div className="options">
            {has("aspect") && <AspectSelect listed={listed} value={look.aspect} onChange={setAspect} />}
            {has("layout") && <label>Layout<select value={look.layout} onChange={(e) => setLayout(e.target.value)}>
              {layoutChoices(listed, look.aspect, look.layout).map((l) => <option key={l} value={l}>{layoutName(l)}</option>)}</select></label>}
          </div>
          {hasPanels(look.layout) && has("camera") && has("split_ratio") && <Panels listed={listed} look={look} onLook={onLook} />}
        </Line>}
        {has("captions") && <Line label="Subtitles" hint="Word-by-word captions burned into the clip." checked={look.captions}
          onChange={(v) => onLook({ captions: v, ...(v ? {} : { caption_emoji: false }) })}>
          <div className="options">
            {has("caption_style") && <label>Style<select value={look.caption_style} onChange={(e) => onLook({ caption_style: e.target.value })}>
              {styles.map((s) => <option key={s} value={s}>{tidy(s)}</option>)}</select></label>}
            {has("caption_position") && <label>Position<select value={look.caption_position} onChange={(e) => onLook({ caption_position: e.target.value })}>
              {(listed.caption_position.values || [look.caption_position]).map((p: string) => <option key={p} value={p}>{POSITION_NAMES[p] || tidy(p)}</option>)}</select></label>}
            {has("caption_accent") && <div className="accent">
              <label className="check"><input type="checkbox" checked={look.caption_accent !== null}
                onChange={(e) => onLook({ caption_accent: e.target.checked ? LIME : null })} /><span>Own accent colour</span></label>
              {look.caption_accent !== null && <input type="color" className="swatch" aria-label="Accent colour for the keyword" value={look.caption_accent}
                onChange={(e) => onLook({ caption_accent: e.target.value })} />}
            </div>}
            {has("censor") && <label className="check"><input type="checkbox" checked={look.censor} onChange={(e) => onLook({ censor: e.target.checked })} /><span>Censor swears</span></label>}
          </div>
        </Line>}
        {has("caption_emoji") && <Line label="Emojis" hint={look.captions ? "Adds fitting emojis to the subtitles." : "Needs Subtitles."} checked={look.captions && look.caption_emoji}
          disabled={!look.captions} onChange={(v) => onLook({ caption_emoji: v })} />}
        {has("hook_overlay") && <Line label="Hook text" hint="A short opening line on screen for the first seconds. Added to clips the AI has rated." checked={look.hook_overlay}
          onChange={(v) => onLook({ hook_overlay: v })} />}
        {has("tighten") && <Line label="Cut dead air" hint="Removes long silences and filler words." checked={look.tighten} onChange={(v) => onLook({ tighten: v })} />}
        {has("punch_zoom") && <Line label="Punch-in zoom" hint="A slight zoom on the gameplay at the big moments." checked={look.punch_zoom} onChange={(v) => onLook({ punch_zoom: v })} />}
        {has("flash_forward") && <Line label="Open on the best moment" hint="Starts with a flash of the peak, then plays from the start. Added to clips the AI has rated."
          checked={look.flash_forward} onChange={(v) => onLook({ flash_forward: v })} />}
        {["Logo", "Intro", "Outro"].map((name) => (
          <li key={name} className="line off"><label className="check"><input type="checkbox" checked={false} disabled readOnly /><span><b>{name}</b></span></label><Soon /></li>))}
      </ul>
    </>
  );
}
