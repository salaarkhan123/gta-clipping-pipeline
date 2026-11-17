"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { LookSketch } from "@/components/dash/LookSketch";
import { useDash } from "@/components/dash/Shell";
import { Tabs } from "@/components/dash/Tabs";
import { useVideoChooser } from "@/components/dash/Upload";
import { api } from "@/lib/api";
import { gameName, gameOf, isPreset, isProvisional, layoutName, loadTemplates, mediaUrl, tidy } from "@/lib/templates";

const EDITS: [string, string][] = [["tighten", "dead air cut"], ["punch_zoom", "punch-in zoom"], ["flash_forward", "opens on the best moment"], ["hook_overlay", "on-screen hook"]];
const PRESETS = "types";      // the tab for game-type presets, which belong to no single game
const groupOf = (t: any) => (isPreset(t) ? PRESETS : gameOf(t));
const groupName = (g: string) => (g === PRESETS ? "Game types" : gameName(g));

// What a template sets, from whichever fields this version of the API sends (in `options` or on the template itself).
function sets(t: any): { chips: string[]; edits: string[] } {
  const o = t.options || {}, chips: string[] = [];
  if (typeof o.clip_length === "number") chips.push(`${o.clip_length} s clips`);
  else if (typeof t.duration === "string") chips.push(`${t.duration.replace("-", " to ")} s clips`);
  const style = o.caption_style || t.caption_style, layout = t.layout || o.layout, aspect = t.aspect || o.aspect;
  if (typeof style === "string") chips.push(`${tidy(style)} captions`);
  if (typeof layout === "string") chips.push(`${layoutName(layout).replace(" (provisional)", "")} layout`);
  if (typeof aspect === "string") chips.push(aspect);
  return { chips, edits: EDITS.filter(([k]) => o[k] === true).map(([, name]) => name) };
}

// A template's picture: its own poster or preview clip when the API has one. Otherwise our own sketch of the
// look (the panels at the template's proportions, a caption drawn the way its style renders) next to its game.
function Preview({ t }: { t: any }) {
  const [broken, setBroken] = useState(false);
  const poster = mediaUrl(t.preview?.poster), video = mediaUrl(t.preview?.video);
  const style = t.options?.caption_style || t.caption_style;
  return (
    <div className="template-art" aria-hidden={!video || broken ? true : undefined}>
      {!broken && video ? <video controls muted loop playsInline preload="none" poster={poster || undefined} src={video}
          aria-label={`${t.name} preview`} onError={() => setBroken(true)} />
        : !broken && poster ? <img src={poster} alt="" loading="lazy" onError={() => setBroken(true)} />
        : <span className="template-blank">
            <LookSketch aspect={typeof t.aspect === "string" ? t.aspect : "9:16"} layout={typeof t.layout === "string" ? t.layout : "auto"}
              camera={t.panels?.camera} split={t.panels?.split_ratio} style={typeof style === "string" ? style : undefined} />
            <span className="mock-game"><Icon name="gamepad" size={22} />{groupName(groupOf(t))}</span>
          </span>}
    </div>
  );
}

// Game templates: filter by game, see what each one sets, and start a project with it applied.
export default function Templates() {
  const { fail } = useDash();
  const [templates, setTemplates] = useState<any[] | null>(null), [projects, setProjects] = useState<any[] | null>(null);
  const [game, setGame] = useState("all");
  const chooser = useVideoChooser(projects);

  useEffect(() => {
    setGame(new URLSearchParams(window.location.search).get("game") || "all");
    loadTemplates().then((t) => setTemplates([...t.presets, ...t.games])).catch((e) => { setTemplates([]); fail(e); });
    api("/v1/projects").then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  }, [fail]);

  const games = [...new Set((templates || []).map(groupOf))];
  const shownGame = games.includes(game) ? game : "all";              // an unknown ?game= falls back to everything
  const shown = (templates || []).filter((t) => shownGame === "all" || groupOf(t) === shownGame);
  function pick(g: string) {
    setGame(g);
    window.history.replaceState(null, "", g === "all" ? window.location.pathname : `?game=${encodeURIComponent(g)}`);
  }

  return (
    <>
      <p className="crumb"><Link href="/dashboard/">Home</Link> / Game templates</p>
      <h1 className="dash-title">Game templates</h1>
      <p className="muted">A template tunes what we look for in a game and sets the clip length, caption style and editing. You can still change every setting before you start.</p>
      {templates === null ? <p className="muted">Loading templates…</p> : !templates.length ? <p className="muted">No templates to show right now.</p> : <>
        <Tabs label="Game" panel="template-list" value={shownGame} onChange={pick}
          tabs={[["all", "All"], ...games.map((g): [string, string] => [g, groupName(g)])]} />
        <div id="template-list" role="tabpanel" aria-label={shownGame === "all" ? "All templates" : `${groupName(shownGame)} templates`}>
        <ul className="templates">
          {shown.map((t) => {
            const { chips, edits } = sets(t);
            return (
              <li key={t.id} className="template">
                <Preview t={t} />
                <div className="template-body">
                  <p className="template-tags"><span className="badge">{groupName(groupOf(t))}</span>
                    {isProvisional(t) && <span className="soon-tag" title="This template's look is still being checked against real output and may change.">Provisional</span>}</p>
                  <h2>{t.name || tidy(String(t.id))}</h2>
                  {t.description && <p className="muted">{t.description}</p>}
                  {chips.length > 0 && <ul className="chip-row" aria-label="This template sets">{chips.map((c) => <li key={c} className="chip">{c}</li>)}</ul>}
                  {edits.length > 0 && <p className="muted small">Editing: {edits.join(", ")}.</p>}
                  <button className="btn small primary" onClick={() => chooser.choose({ title: `Use “${t.name}”`, query: `tool=clips&template=${encodeURIComponent(t.id)}` })}>
                    Use template</button>
                </div>
              </li>);
          })}
        </ul>
        </div>
      </>}
      {chooser.element}
    </>
  );
}
