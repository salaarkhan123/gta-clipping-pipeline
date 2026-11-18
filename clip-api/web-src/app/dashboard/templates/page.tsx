"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { LookSketch } from "@/components/dash/LookSketch";
import { useDash } from "@/components/dash/Shell";
import { BackTitle } from "@/components/dash/ui";
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


// A template's shape: 16:9 templates get a wide card, everything else a tall 9:16 one, all the same picture height.
const wideOf = (t: any) => (t.aspect || t.options?.aspect) === "16:9";
const CARD = { tall: "w-[200px] flex-none narrow:w-[calc((100%-12px)/2)]", wide: "w-[632px] max-w-full flex-none narrow:w-full" };

// A template's picture: its own poster or preview clip when the API has one. Otherwise our own sketch of the
// look (the panels at the template's proportions, a caption drawn the way its style renders) next to its game.
function Preview({ t }: { t: any }) {
  const [broken, setBroken] = useState(false);
  const poster = mediaUrl(t.preview?.poster), video = mediaUrl(t.preview?.video);
  const style = t.options?.caption_style || t.caption_style;
  return (
    <div className={`relative grid ${wideOf(t) ? "aspect-video" : "aspect-[9/16]"} place-items-center overflow-hidden rounded-16 bg-card-2 ring-1 ring-inset ring-[rgba(255,255,255,.06)]
      transition-shadow duration-200 group-hover:ring-[rgba(255,255,255,.22)] [&_img]:h-full [&_img]:w-full [&_img]:object-cover [&_video]:h-full [&_video]:w-full [&_video]:object-cover`}
      aria-hidden={!video || broken ? true : undefined}>
      {!broken && video ? <video controls muted loop playsInline preload="none" poster={poster || undefined} src={video}
          aria-label={`${t.name} preview`} onError={() => setBroken(true)} />
        : !broken && poster ? <img src={poster} alt="" loading="lazy" onError={() => setBroken(true)} />
        : <span className="grid h-full w-full place-items-center content-center gap-3 [&_.mock]:h-[58%]">
            <LookSketch aspect={typeof t.aspect === "string" ? t.aspect : "9:16"} layout={typeof t.layout === "string" ? t.layout : "auto"}
              camera={t.panels?.camera} split={t.panels?.split_ratio} style={typeof style === "string" ? style : undefined} />
            <span className="inline-flex items-center gap-2 text-[13px] font-semibold text-soft"><Icon name="gamepad" size={18} />{groupName(groupOf(t))}</span>
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
    <div className="wide stack">
      <div className="grid gap-2">
        <BackTitle title="Game templates" />
        <p className="muted m-0 max-w-[720px] text-[14px]">A template tunes what we look for in a game and sets the clip length, caption style and editing. You can still change every setting before you start.</p>
      </div>
      {templates === null ? <p className="muted">Loading templates…</p> : !templates.length ? <p className="muted">No templates to show right now.</p> : <>
        <div className="-mx-1 overflow-x-auto px-1 pb-1 [&_.tabs]:flex-nowrap [&_.tabs_button]:whitespace-nowrap">
          <Tabs label="Game" panel="template-list" value={shownGame} onChange={pick}
            tabs={[["all", "All"], ...games.map((g): [string, string] => [g, groupName(g)])]} />
        </div>
        <div id="template-list" role="tabpanel" aria-label={shownGame === "all" ? "All templates" : `${groupName(shownGame)} templates`}>
        <ul className="m-0 flex list-none flex-wrap items-start gap-x-[14px] gap-y-7 p-0 narrow:gap-x-3 narrow:gap-y-6">
          {shown.map((t) => {
            const { chips, edits } = sets(t);
            const name = t.name || tidy(String(t.id));
            return (
              <li key={t.id} className={`group grid min-w-0 content-start gap-[10px] ${CARD[wideOf(t) ? "wide" : "tall"]}`}>
                <div className="relative">
                  <Preview t={t} />
                  <span className="pointer-events-none absolute left-2 top-2 flex flex-wrap gap-1">
                    <span className="rounded-full bg-[rgba(0,0,0,.66)] px-2 py-[2px] text-[11px] font-semibold text-text [backdrop-filter:blur(6px)]">{groupName(groupOf(t))}</span>
                    {isProvisional(t) && <span className="rounded-full bg-[rgba(0,0,0,.66)] px-2 py-[2px] text-[11px] font-medium text-soft [backdrop-filter:blur(6px)]"
                      title="This template's look is still being checked against real output and may change.">Provisional</span>}
                  </span>
                </div>
                <div className="grid min-w-0 gap-1 px-[2px]">
                  <h2 className="m-0 overflow-hidden text-ellipsis whitespace-nowrap font-body text-[14px] font-semibold leading-[1.3]" title={name}>{name}</h2>
                  {t.description && <p className="m-0 line-clamp-2 text-[12.5px] leading-[1.45] text-muted" title={t.description}>{t.description}</p>}
                  {chips.length > 0 && <p className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-dim" title={[...chips, ...edits].join(" · ")}>{chips.join(" · ")}</p>}
                </div>
                <button className="btn small ghost justify-self-start" onClick={() => chooser.choose({ title: `Use “${name}”`, query: `tool=clips&template=${encodeURIComponent(t.id)}` })}>
                  Use template</button>
              </li>);
          })}
        </ul>
        </div>
      </>}
      {chooser.element}
    </div>
  );
}
