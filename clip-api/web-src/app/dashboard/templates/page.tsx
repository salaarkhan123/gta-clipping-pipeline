"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { Tabs } from "@/components/dash/Tabs";
import { useVideoChooser } from "@/components/dash/Upload";
import { API, api } from "@/lib/api";

// Display names for the game ids the API may send. An id that is not listed here is shown tidied up.
const GAMES: Record<string, string> = { gta: "GTA", gta5: "GTA 5", lol: "League of Legends", wow: "World of Warcraft", ow2: "Overwatch 2",
  minecraft: "Minecraft", apex: "Apex Legends", valorant: "Valorant", fortnite: "Fortnite", dota2: "Dota 2", rust: "Rust", cs2: "CS2", other: "Other games" };
const EDITS: [string, string][] = [["tighten", "dead air cut"], ["punch_zoom", "punch-in zoom"], ["flash_forward", "opens on the best moment"], ["hook_overlay", "on-screen hook"]];
const tidy = (v: string) => v.replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());
const gameName = (id: string) => GAMES[id] || tidy(id);
const gameOf = (t: any): string => (typeof t.game === "string" && t.game) || "other";
// Preview files may arrive as full links or as paths on the API host.
const media = (v: unknown) => (typeof v !== "string" || !v ? null : /^https?:\/\//.test(v) ? v : `${API}/${v.replace(/^\//, "")}`);

// What a template sets, from whichever fields this version of the API sends (in `options` or on the template itself).
function sets(t: any): { chips: string[]; edits: string[] } {
  const o = t.options || {}, chips: string[] = [];
  if (typeof o.clip_length === "number") chips.push(`${o.clip_length} s clips`);
  else if (typeof t.duration === "string") chips.push(`${t.duration.replace("-", " to ")} s clips`);
  const style = o.caption_style || t.caption_style, layout = t.layout || o.layout, aspect = t.aspect || o.aspect;
  if (typeof style === "string") chips.push(`${tidy(style)} captions`);
  if (typeof layout === "string") chips.push(`${tidy(layout)} layout`);
  if (typeof aspect === "string") chips.push(aspect);
  return { chips, edits: EDITS.filter(([k]) => o[k] === true).map(([, name]) => name) };
}

// A template's picture: its own poster or preview clip when the API has one, otherwise a plain card in our colours.
function Preview({ t }: { t: any }) {
  const [broken, setBroken] = useState(false);
  const poster = media(t.preview?.poster), video = media(t.preview?.video);
  return (
    <div className="template-art" aria-hidden={!video || broken ? true : undefined}>
      {!broken && video ? <video controls muted loop playsInline preload="none" poster={poster || undefined} src={video}
          aria-label={`${t.name} preview`} onError={() => setBroken(true)} />
        : !broken && poster ? <img src={poster} alt="" loading="lazy" onError={() => setBroken(true)} />
        : <span className="template-blank"><Icon name="gamepad" size={30} /><b>{gameName(gameOf(t))}</b></span>}
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
    api("/v1/templates", { auth: false }).then((r) => setTemplates(Array.isArray(r?.templates) ? r.templates : [])).catch((e) => { setTemplates([]); fail(e); });
    api("/v1/projects").then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  }, [fail]);

  const games = [...new Set((templates || []).map(gameOf))];
  const shownGame = games.includes(game) ? game : "all";              // an unknown ?game= falls back to everything
  const shown = (templates || []).filter((t) => shownGame === "all" || gameOf(t) === shownGame);
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
          tabs={[["all", "All"], ...games.map((g): [string, string] => [g, gameName(g)])]} />
        <div id="template-list" role="tabpanel" aria-label={shownGame === "all" ? "All templates" : `${gameName(shownGame)} templates`}>
        <ul className="templates">
          {shown.map((t) => {
            const { chips, edits } = sets(t);
            return (
              <li key={t.id} className="template">
                <Preview t={t} />
                <div className="template-body">
                  <span className="badge">{gameName(gameOf(t))}</span>
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
