"use client";
import { useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { StyleComposer } from "@/components/dash/StyleComposer";
import { BackTitle } from "@/components/dash/ui";
import { Tabs } from "@/components/dash/Tabs";
import { useVideoChooser } from "@/components/dash/Upload";
import { api } from "@/lib/api";
import { MediaItem, mediaUrl as mediaFile, useMedia } from "@/lib/media";
import { gameName, gameOf, hasPanels, isPreset, isProvisional, layoutName, loadTemplates, tidy } from "@/lib/templates";

const EDITS: [string, string][] = [["tighten", "dead air cut"], ["punch_zoom", "punch-in zoom"], ["flash_forward", "opens on the best moment"], ["hook_overlay", "on-screen hook"]];
const PRESETS = "types";      // the tab for game-type presets, which belong to no single game
const GAMING = "gaming";      // all per-game templates (product default) — not a named-creator recreate
const groupOf = (t: any) => (isPreset(t) ? PRESETS : gameOf(t));
const groupName = (g: string) => (g === PRESETS ? "Game types" : g === GAMING ? "Gaming" : gameName(g));

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
const FRAME = "relative grid overflow-hidden rounded-16 ring-1 ring-inset ring-[rgba(255,255,255,.06)] transition-shadow duration-200 group-hover:ring-[rgba(255,255,255,.22)]";

// A template's own clip in the site media's "templates" manifest (one moment per template, published by the media
// pipeline), or null. Never another template's clip and never another game's footage (owner, 2026-11-18).
const footageFor = (t: any, items: MediaItem[]): MediaItem | null => items.find((i) => i.id === t.id || (i as any).template === t.id) || null;

function handoffQuery(templateId: string, note: string) {
  const q = `tool=clips&template=${encodeURIComponent(templateId)}`;
  const prompt = note.trim();
  return prompt ? `${q}&prompt=${encodeURIComponent(prompt.slice(0, 300))}` : q;
}

// The clip: its still first (lazy), the video only while the pointer or focus is on the card.
function Clip({ t, clip }: { t: any; clip: MediaItem }) {
  const [play, setPlay] = useState(false), [broken, setBroken] = useState(false);
  const poster = clip.poster ? mediaFile("templates", clip.poster) : null;
  return (
    <div className={`${FRAME} ${wideOf(t) ? "aspect-video" : "aspect-[9/16]"} bg-card-2 [&_img]:h-full [&_img]:w-full [&_img]:object-cover [&_video]:absolute [&_video]:inset-0 [&_video]:h-full [&_video]:w-full [&_video]:object-cover`}
      onPointerEnter={() => setPlay(true)} onPointerLeave={() => setPlay(false)} onFocusCapture={() => setPlay(true)} onBlurCapture={() => setPlay(false)}>
      {poster && !broken && <img src={poster} alt="" loading="lazy" onError={() => setBroken(true)} />}
      {play && clip.kind === "video" && <video muted loop playsInline autoPlay preload="auto" aria-label={`${t.name}: ${clip.label}`}>
        {clip.webm && <source src={mediaFile("templates", clip.webm)} type="video/webm" />}
        <source src={mediaFile("templates", clip.src)} type="video/mp4" />
      </video>}
      {!play && clip.kind === "video" && <span className="pointer-events-none absolute bottom-2 right-2 grid h-7 w-7 place-items-center rounded-full bg-[rgba(0,0,0,.55)] text-text" aria-hidden="true"><Icon name="play" size={14} /></span>}
    </div>
  );
}

// No clip for this template yet: its game, its real layout as a wireframe (panels at the template's own
// proportions, where the caption sits), and a quiet "Preview coming soon". Nothing here is footage.
function Wireframe({ t }: { t: any }) {
  const layout = String(t.layout || t.options?.layout || "auto"), wide = wideOf(t);
  const W = wide ? 160 : 90, H = wide ? 90 : 160;
  const two = hasPanels(layout);
  const camTop = two ? (t.panels?.camera ? t.panels.camera === "top" : layout !== "screen_first") : false;
  const share = two ? (t.panels?.split_ratio ?? (camTop ? 0.38 : 0.6)) : 0;
  const line = "rgba(255,255,255,.55)", fill = "rgba(255,255,255,.06)", txt = { fill: "rgba(255,255,255,.6)", fontSize: 7, fontFamily: "inherit", textAnchor: "middle" as const };
  const capY = two ? H * share : H * 0.72;
  const fitH = W * 9 / 16;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={wide ? "h-[46%]" : "h-[52%]"} aria-hidden="true">
      <rect x="0.5" y="0.5" width={W - 1} height={H - 1} rx="5" fill="none" stroke={line} />
      {two ? <>
          <rect x="3" y="3" width={W - 6} height={H * share - 4.5} rx="3" fill={fill} stroke={line} strokeDasharray="2 2" />
          <rect x="3" y={H * share + 1.5} width={W - 6} height={H * (1 - share) - 4.5} rx="3" fill={fill} stroke={line} strokeDasharray="2 2" />
          <text x={W / 2} y={(H * share) / 2 + 2} {...txt}>{camTop ? "Facecam" : "Gameplay"}</text>
          <text x={W / 2} y={H * share + (H * (1 - share)) / 2 + 2} {...txt}>{camTop ? "Gameplay" : "Facecam"}</text>
        </>
        : layout === "fit" || layout === "classic" ? <>
          <rect x="3" y={(H - fitH) / 2} width={W - 6} height={fitH} rx="3" fill={fill} stroke={line} strokeDasharray="2 2" />
          <text x={W / 2} y={H / 2 + 2} {...txt}>Gameplay</text>
        </>
        : <>
          <rect x="3" y="3" width={W - 6} height={H - 6} rx="3" fill={fill} stroke={line} strokeDasharray="2 2" />
          <text x={W / 2} y={H / 2 + 2} {...txt}>{layout === "auto" ? "Layout per clip" : "Gameplay"}</text>
          {layout === "pip" && <><rect x={W - 33} y={H - 33} width="27" height="27" rx="3" fill={fill} stroke={line} /><text x={W - 19.5} y={H - 17} {...txt}>Cam</text></>}
        </>}
      {(t.options?.captions ?? true) !== false && <rect x={W * 0.22} y={capY - 3} width={W * 0.56} height="6" rx="3" fill="rgba(255,255,255,.85)" />}
    </svg>
  );
}

function Empty({ t, group }: { t: any; group: string }) {
  return (
    <div className={`${FRAME} ${wideOf(t) ? "aspect-video" : "aspect-[9/16]"} content-between justify-items-center p-3 text-center [background:radial-gradient(ellipse_at_50%_0%,rgba(255,255,255,.07),transparent_65%),theme(colors.card-2)]`}>
      <p className="m-0 w-full text-[19px] font-semibold leading-[1.1] tracking-[-0.01em] text-text">{group}</p>
      <Wireframe t={t} />
      <p className="m-0 text-[11px] font-medium uppercase tracking-[.06em] text-fg-3">Preview coming soon</p>
    </div>
  );
}

// Gaming style gallery: filter by game, Recreate a ClutchClips template onto your footage, optional brand note.
// Templates with a clip come first; a game with no clips moves to the end of the tabs.
export default function Templates() {
  const { fail } = useDash();
  const [templates, setTemplates] = useState<any[] | null>(null), [projects, setProjects] = useState<any[] | null>(null);
  const [game, setGame] = useState(GAMING);
  const [styleId, setStyleId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const chooser = useVideoChooser(projects);
  const media = useMedia("templates"), footage = media?.items || [];

  useEffect(() => {
    const g = new URLSearchParams(window.location.search).get("game");
    setGame(g || GAMING);
    loadTemplates().then((t) => setTemplates([...t.presets, ...t.games])).catch((e) => { setTemplates([]); fail(e); });
    api("/v1/projects").then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  }, [fail]);

  const withClip = (t: any) => !!footageFor(t, footage);
  const all = (templates || []).map((t, i) => ({ t, i })).sort((a, b) => Number(withClip(b.t)) - Number(withClip(a.t)) || a.i - b.i).map((x) => x.t);
  const groups = [...new Set((templates || []).map(groupOf))];
  const games = [...groups.filter((g) => all.some((t) => groupOf(t) === g && withClip(t))), ...groups.filter((g) => !all.some((t) => groupOf(t) === g && withClip(t)))];
  const tabIds = new Set([GAMING, "all", ...games]);
  const shownGame = tabIds.has(game) ? game : GAMING;
  const shown = all.filter((t) => shownGame === "all" ? true : shownGame === GAMING ? !isPreset(t) : groupOf(t) === shownGame);
  const credits = (media?.credits || []).filter((c) => footage.some((i) => withClipItem(i, all) && i.source?.creator === c.creator));
  const selected = styleId ? all.find((t) => t.id === styleId) : null;
  const styleRef = selected ? { id: selected.id, name: selected.name || tidy(String(selected.id)) } : null;

  function pick(g: string) {
    setGame(g);
    window.history.replaceState(null, "", g === GAMING ? window.location.pathname : `?game=${encodeURIComponent(g)}`);
  }
  function recreate(t: any) {
    const name = t.name || tidy(String(t.id));
    setStyleId(t.id);
    chooser.choose({ title: `Recreate “${name}”`, query: handoffQuery(t.id, note) });
  }
  function addFootage() {
    if (styleId) {
      chooser.choose({ title: `Clip with “${styleRef?.name || "style"}”`, query: handoffQuery(styleId, note) });
      return;
    }
    const prompt = note.trim();
    chooser.choose({ title: "Add raw footage", query: prompt ? `tool=clips&prompt=${encodeURIComponent(prompt.slice(0, 300))}` : "tool=clips" });
  }
  function clipWithStyle() {
    if (!styleId) return;
    chooser.choose({ title: `Clip with “${styleRef?.name || "style"}”`, query: handoffQuery(styleId, note) });
  }

  const tabs: [string, string][] = [
    [GAMING, "Gaming"],
    ["all", "All"],
    ...games.map((g): [string, string] => [g, groupName(g)]),
  ];

  return (
    <div className="wide stack pb-36">
      <div className="grid gap-2">
        <BackTitle title="Game templates" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Game templates" }]} />
        <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] font-semibold text-text">
          Choose a gaming style
          <span className="inline-flex items-center gap-1 rounded-full border border-solid border-lime/40 bg-lime-wash px-2 py-[2px] text-[11px] font-semibold uppercase tracking-[.04em] text-lime">New</span>
        </p>
        <p className="muted m-0 max-w-[720px] text-[14px]">
          Recreate applies a ClutchClips game template (layout, captions, detection) to <em>your</em> footage.
          It does not copy another creator&apos;s look. Change every setting in Clip Maker before you start.
        </p>
      </div>
      {templates === null ? <p className="muted">Loading templates…</p> : !templates.length ? <p className="muted">No templates to show right now.</p> : <>
        <div className="-mx-1 flex flex-wrap items-center gap-2 overflow-x-auto px-1 pb-1 [&_.tabs]:flex-nowrap [&_.tabs_button]:whitespace-nowrap">
          <Tabs label="Style category" panel="template-list" value={shownGame} onChange={pick} tabs={tabs} />
        </div>
        <div id="template-list" role="tabpanel" aria-label={`${groupName(shownGame)} styles`}>
        <ul className="m-0 flex list-none flex-wrap items-start gap-x-[14px] gap-y-7 p-0 narrow:gap-x-3 narrow:gap-y-6">
          {shown.map((t) => {
            const { chips, edits } = sets(t);
            const name = t.name || tidy(String(t.id)), clip = footageFor(t, footage);
            const on = styleId === t.id;
            return (
              <li key={t.id} className={`group grid min-w-0 content-start gap-[10px] ${CARD[wideOf(t) ? "wide" : "tall"]}`}>
                <div className={`relative ${on ? "rounded-16 ring-2 ring-lime ring-offset-2 ring-offset-bg" : ""}`}>
                  {clip ? <Clip t={t} clip={clip} /> : <Empty t={t} group={groupName(groupOf(t))} />}
                  {clip && <span className="pointer-events-none absolute left-2 top-2 flex flex-wrap gap-1">
                    <span className="rounded-full bg-[rgba(0,0,0,.66)] px-2 py-[2px] text-[11px] font-semibold text-text [backdrop-filter:blur(6px)]">{groupName(groupOf(t))}</span>
                  </span>}
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center bg-gradient-to-t from-[rgba(0,0,0,.72)] to-transparent p-3 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
                    <button type="button" className="pointer-events-auto btn small primary" onClick={() => recreate(t)}>Recreate</button>
                  </div>
                </div>
                <div className="grid min-w-0 gap-1 px-[2px]">
                  <h2 className="m-0 flex min-w-0 items-center gap-2 font-body text-[14px] font-semibold leading-[1.3]" title={name}>
                    <span className="overflow-hidden text-ellipsis whitespace-nowrap">{name}</span>
                    {isProvisional(t) && <span className="flex-none text-[11px] font-medium text-fg-3" title="This template's look is still being checked against real output and may change.">Provisional</span>}</h2>
                  {t.description && <p className="m-0 line-clamp-2 text-[12.5px] leading-[1.45] text-muted" title={t.description}>{t.description}</p>}
                  {chips.length > 0 && <p className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-dim" title={[...chips, ...edits].join(" · ")}>{chips.join(" · ")}</p>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className="btn small primary justify-self-start" onClick={() => recreate(t)}>Recreate</button>
                  <button className="btn small ghost justify-self-start" onClick={() => setStyleId(t.id)} aria-pressed={on}>
                    {on ? "Selected" : "Use as reference"}</button>
                </div>
              </li>);
          })}
        </ul>
        {credits.length > 0 && <p className="muted m-0 mt-8 text-[12.5px]">Preview footage from {credits.map((c, i) => <span key={c.creator}>{i ? (i === credits.length - 1 ? " and " : ", ") : ""}
          <a href={c.url} target="_blank" rel="noreferrer" className="text-label underline">{c.creator}</a></span>)}, used with permission.</p>}
        </div>
      </>}
      <StyleComposer style={styleRef} note={note} onNote={setNote} onFootage={addFootage} onClip={clipWithStyle}
        onClearStyle={() => setStyleId(null)} canSubmit={!!styleId} />
      {chooser.element}
    </div>
  );
}

// Whether a manifest clip is shown on some template here (only those creators are credited).
const withClipItem = (i: MediaItem, all: any[]) => all.some((t) => footageFor(t, [i]));
