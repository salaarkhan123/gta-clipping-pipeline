"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API, api, ApiError, clock, getToken } from "@/lib/api";
import { ExportFull } from "./ExportFull";
import { Icon, IconName, Soon } from "./Icon";
import { BACKDROP, CARD_ROW, MEDIA, Shape, thumbVar, useShape } from "./ProjectCard";
import { useDash } from "./Shell";
import { CLIP_LAYOUT_KEY, ClipLayout, parseClipLayout } from "@/lib/clip-layout";
import { scoreLabel } from "@/lib/scores";

export type { ClipLayout };
export { CLIP_LAYOUT_KEY, parseClipLayout };

export async function downloadSubtitles(clipId: string, format = "srt") {
  const res = await fetch(`${API}/v1/clips/${clipId}/subtitles?format=${format}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, "error", "Couldn't get the subtitles for this clip.");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob()); a.download = `${clipId}.${format}`; a.click();
  URL.revokeObjectURL(a.href);
}

// A clip's place by virality (1 = best) and by position in the video (1 = earliest). The API is adding
// `rank_index` (from 0) and `timeline_index` (from 1); a clip without them uses today's `rank` and `index`.
export const rankOf = (c: any): number | null => (typeof c.rank_index === "number" ? c.rank_index + 1 : c.rank || null);
export const numberOf = (c: any): number => (typeof c.timeline_index === "number" ? c.timeline_index : c.index);
// A clip without a title is named by its number in its project (see `numbering`), so no two cards share a name.
// Where there is no project around it (the Library lists clips from every video), by where it starts.
export const nameOf = (c: any, number?: number): string => c.title || (number ? `Clip ${number}` : `Clip at ${clock(c.start_sec)}`);
// Each clip's own number in a project: 1 for the first one made, counting on across every run. `index` starts
// again at 1 in each run, so it cannot tell two runs' clips apart. A clip keeps its number when more arrive.
export function numbering(clips: any[]): Map<string, number> {
  const made = [...clips].sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")) || String(a.job_id).localeCompare(String(b.job_id)) || numberOf(a) - numberOf(b));
  return new Map(made.map((c, i) => [c.id, i + 1]));
}

const BADGE = "pointer-events-none absolute top-2 z-[2] rounded-full bg-[rgba(0,0,0,.66)] px-2 py-[2px] font-body text-[11.5px] font-medium leading-[1.5] tabular-nums text-text [backdrop-filter:blur(6px)]";
const ACTION = "grid h-8 w-8 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-soft enabled:hover:bg-chip-hover enabled:hover:text-text hover:bg-chip-hover hover:text-text disabled:cursor-default disabled:opacity-[.4] narrow:h-10 narrow:w-10";
const SOON: [IconName, string][] = [["calendar", "Schedule"]];

// One clip as a card: the picture in the clip's own shape with its AI rating and time range on it, then the
// title and its actions. Clicking the picture plays the clip in place.
// `project` links back to where it came from (Library). `lit` marks the card the timeline just jumped to.
// `onSelect` adds the tick box (the project page's bulk actions).
// `uploadId` (or `project`) gives the card its Edit action: the editor needs the source video.
// The results grid: cards shaped like their clip (see ProjectCard's `useShape`), same picture height, wrapping.
export const CLIP_GRID = CARD_ROW;
// Compact stacked rows for the list layout (Library clips, and any other ClipCard grid that opts in).
export const CLIP_LIST = "grid gap-2";

// Grid vs list: remembered in this browser only. Always start as grid so SSR matches the first paint.
export function useClipLayout(): [ClipLayout, (v: ClipLayout) => void] {
  const [layout, setLayout] = useState<ClipLayout>("grid");
  useEffect(() => {
    try { setLayout(parseClipLayout(localStorage.getItem(CLIP_LAYOUT_KEY))); } catch { /* private mode */ }
  }, []);
  const set = (v: ClipLayout) => {
    setLayout(v);
    try { localStorage.setItem(CLIP_LAYOUT_KEY, v); } catch { /* private mode */ }
  };
  return [layout, set];
}

export function LayoutToggle({ value, onChange }: { value: ClipLayout; onChange: (v: ClipLayout) => void }) {
  return (
    <div role="group" aria-label="Clip layout" className="inline-flex gap-[2px] rounded-12 border border-solid border-line-soft bg-panel p-[3px]">
      {([["grid", "Grid layout"], ["list", "List layout"]] as const).map(([mode, label]) => (
        <button key={mode} type="button" aria-pressed={value === mode} aria-label={label} title={label} onClick={() => onChange(mode)}
          className={`grid h-8 w-8 cursor-pointer place-items-center rounded-8 border-0 ${value === mode ? "bg-chip-hover text-lime" : "bg-transparent text-muted hover:text-text"}`}>
          <Icon name={mode} size={16} />
        </button>
      ))}
    </div>
  );
}

// Same picture height for both shapes: a tall card is 216 px wide (384 px high), a wide one 683 px.
const CLIP_WIDTH: Record<Shape, string> = { tall: "w-[216px] flex-none narrow:w-[calc((100%-12px)/2)]", wide: "w-[683px] max-w-full flex-none narrow:w-full" };

export function ClipCard({ clip, onChange, project, uploadId, lit, number, selected, onSelect, layout = "grid" }: { clip: any; onChange: (c: any) => void;
  project?: { id: string; name: string }; uploadId?: string; lit?: boolean; number?: number; selected?: boolean; onSelect?: (id: string, on: boolean) => void; layout?: ClipLayout }) {
  const { fail } = useDash();
  // A reply signs new links for the same files; the ones on the page stay, so a playing clip is not restarted.
  const merge = (r: any) => onChange({ ...clip, ...r, video_url: clip.video_url, thumb_url: clip.thumb_url || r.thumb_url, captions_url: clip.captions_url || r.captions_url });
  // Pressing the active choice again clears it.
  const send = (body: Record<string, unknown>) => api(`/v1/clips/${clip.id}/feedback`, { body }).then(merge).catch(fail);
  const keep = (kept: boolean) => send({ kept: clip.kept === kept ? null : kept });
  const react = (reaction: "like" | "dislike") => send({ reaction: clip.reaction === reaction ? null : reaction });
  // The AI offers a few titles; picking one changes the clip's title everywhere. Nothing is re-rendered.
  const titles: string[] = clip.titles?.length ? (clip.titles.includes(clip.title) ? clip.titles : [clip.title, ...clip.titles]) : [];
  const retitle = (title: string) => api(`/v1/clips/${clip.id}`, { method: "PATCH", body: { title } }).then(merge).catch(fail);
  const name = nameOf(clip, number), rank = rankOf(clip);
  const source = uploadId || project?.id;
  const shape = useShape(clip.thumb_url, "tall");
  const [play, setPlay] = useState(false);
  const length = typeof clip.end_sec === "number" && typeof clip.start_sec === "number" ? clip.end_sec - clip.start_sec : clip.start_sec;
  if (layout === "list") {
    return (
      <article id={`clip-${clip.id}`} tabIndex={-1} aria-label={name}
        className={`clip group/card flex min-w-0 scroll-mt-24 items-center gap-3 rounded-12 bg-card px-2 py-2 ring-1 ring-inset focus:outline-none
          ${selected ? "ring-2 ring-lime" : "ring-[rgba(255,255,255,.06)] hover:ring-[rgba(255,255,255,.14)]"}
          ${clip.kept === false ? "opacity-[.45]" : ""} ${lit ? "outline outline-2 outline-offset-2 outline-lime" : ""}`}>
        {onSelect && <input type="checkbox" checked={!!selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
          className="h-5 w-5 flex-none cursor-pointer accent-lime" />}
        <div className="relative h-14 w-10 flex-none overflow-hidden rounded-8 bg-card-2">
          {play ? <video controls autoPlay playsInline preload="auto" poster={clip.thumb_url || undefined} src={clip.video_url} className="block h-full w-full bg-black object-contain" />
            : <button type="button" onClick={() => setPlay(true)} aria-label={`Play ${name}`} className="grid h-full w-full cursor-pointer place-items-center border-0 bg-transparent p-0">
                {clip.thumb_url ? <img src={clip.thumb_url} alt="" loading="lazy" className="h-full w-full object-cover" />
                  : <Icon name="film" size={18} className="text-muted" />}
              </button>}
        </div>
        <button type="button" onClick={() => setPlay(true)} aria-label={`Play ${name}`}
          className="grid min-w-0 flex-1 cursor-pointer gap-[2px] border-0 bg-transparent p-0 text-left">
          <h3 title={name} className="m-0 truncate font-body text-[14px] font-semibold leading-[1.3] tracking-[-0.005em] text-text">
            {rank && <span className="tabular-nums text-muted">#{rank} </span>}{name}</h3>
          {project && <span className="truncate text-[12.5px] text-muted">{project.name}</span>}
        </button>
        <span className="flex-none tabular-nums text-[12.5px] text-muted">{clock(length)}</span>
        <ScoreBadge clip={clip} />
      </article>
    );
  }
  return (
    <article id={`clip-${clip.id}`} tabIndex={-1} aria-label={name}
      className={`clip group/card grid min-w-0 scroll-mt-24 content-start gap-[10px] ${CLIP_WIDTH[shape]} rounded-16 focus:outline-none
        ${clip.kept === false ? "opacity-[.45]" : ""} ${lit ? "outline outline-2 outline-offset-[6px] outline-lime" : ""}`}>
      <div className="relative">
        <div style={clip.thumb_url ? thumbVar(clip.thumb_url) : undefined}
          className={`relative ${MEDIA[shape]} overflow-hidden rounded-16 bg-card-2 ring-1 ring-inset transition-shadow duration-200 ${selected ? "ring-2 ring-lime" : "ring-[rgba(255,255,255,.06)] group-hover/card:ring-[rgba(255,255,255,.18)]"} ${clip.thumb_url ? BACKDROP : ""}`}>
          {play ? <video controls autoPlay playsInline preload="auto" poster={clip.thumb_url || undefined} src={clip.video_url} className="relative z-[1] block h-full w-full bg-black object-contain" />
            : <button type="button" onClick={() => setPlay(true)} aria-label={`Play ${name}`} className="group/play relative block h-full w-full cursor-pointer border-0 bg-transparent p-0">
                {clip.thumb_url ? <img src={clip.thumb_url} alt="" loading="lazy" className="relative block h-full w-full object-contain" />
                  : <span className="grid h-full place-items-center text-muted"><Icon name="film" size={30} /></span>}
                <span className="pointer-events-none absolute inset-x-0 bottom-0 h-[42%] bg-[linear-gradient(transparent,rgba(0,0,0,.8))]" aria-hidden="true" />
                <span className="absolute left-1/2 top-1/2 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[rgba(0,0,0,.55)] text-text opacity-0
                  transition-opacity duration-150 [backdrop-filter:blur(6px)] group-hover/play:opacity-100 group-focus-visible/play:opacity-100" aria-hidden="true"><Icon name="play" size={20} /></span>
              </button>}
          {!play && <span className={`${BADGE} right-2`}>{clock(clip.start_sec)} – {clock(clip.end_sec)}</span>}
          {!play && clip.edited === true && <span className={`${BADGE} bottom-2 right-2 top-auto text-cyan`}>Edited</span>}
          {!play && <div className="absolute right-2 top-10 z-[2] grid gap-[6px] opacity-0 transition-opacity duration-150 group-hover/card:opacity-100 group-focus-within/card:opacity-100
            has-[[aria-pressed=true]]:opacity-100 [@media(hover:none)]:opacity-100" role="group" aria-label="Rate this clip">
            <IconToggle icon="like" label="Like" on={clip.reaction === "like"} onClick={() => react("like")} />
            <IconToggle icon="dislike" label="Dislike" on={clip.reaction === "dislike"} onClick={() => react("dislike")} />
            <IconToggle icon="bookmark" label="Bookmark" on={!!clip.bookmarked} onClick={() => send({ bookmarked: !clip.bookmarked })} />
          </div>}
        </div>
        {onSelect && <input type="checkbox" checked={!!selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)}
          className="absolute left-2 top-2 z-[3] h-5 w-5 cursor-pointer p-0 accent-lime narrow:h-6 narrow:w-6" />}
        {!play && <div className="absolute bottom-2 left-[10px] z-[3] grid leading-none">
          <span className="font-body text-[9.5px] font-semibold uppercase tracking-[.08em] text-soft" aria-hidden="true">{typeof clip.display_score === "number" ? "AI rating" : "Rank"}</span>
          <ScoreBadge clip={clip} />
        </div>}
      </div>
      <div className="grid min-w-0 gap-1 px-[2px]">
        <h3 title={name} className="m-0 line-clamp-2 min-h-[2.6em] font-body text-[14px] font-semibold leading-[1.3] tracking-[-0.005em]">
          {rank && <span className="tabular-nums text-muted">#{rank} </span>}{name}</h3>
        {project && <Link className="muted overflow-hidden text-ellipsis whitespace-nowrap text-[12.5px]" href={`/dashboard/project/?id=${project.id}`}>From {project.name}</Link>}
      </div>
      <div className="flex min-h-[34px] flex-wrap items-center gap-1" role="group" aria-label="Clip actions">
        {source && <Link className="btn small ghost min-h-[32px] gap-[6px] px-3 py-1 text-[13px]" href={`/dashboard/edit/?project=${source}&clip=${clip.id}`} aria-label={`Edit ${name}`}
          title="Trim, cut by transcript, captions and look"><Icon name="sliders" size={16} />Edit</Link>}
        {clip.rendered && clip.rendered !== "full" && <ExportFull clip={clip} onDone={(n) => onChange({ ...clip, ...n })} />}
        <a className={`${ACTION} ml-auto`} href={clip.video_url} download aria-label={`Download ${name}`} title="Download"><Icon name="download" size={18} /></a>
        <button type="button" className={ACTION} disabled={!clip.captions_url}
          aria-label={clip.captions_url ? `Download the captions file for ${name}` : "No captions file: this clip has no captions"}
          title={clip.captions_url ? "Captions file (SRT)" : "This clip has no captions"} onClick={() => downloadSubtitles(clip.id).catch(fail)}><Icon name="captions" size={18} /></button>
      </div>
      <details className="clip-more">
        <summary>Details</summary>
        <div className="clip-more-body">
          {titles.length > 1 && <label className="title-pick">Title
            <select value={clip.title} onChange={(e) => retitle(e.target.value)}>
              {titles.map((x) => <option key={x} value={x}>{x}</option>)}
            </select></label>}
          {clip.description && <p>{clip.description}</p>}
          {clip.hook && <p className="muted">{clip.hook_on_screen ? "On-screen hook" : "Hook idea (not on the video)"}: “{clip.hook}”</p>}
          {clip.suggestion?.text && <p className="tip"><b>Tip</b> {clip.suggestion.text}</p>}
          {clip.hashtags?.length > 0 && <p className="tags">{clip.hashtags.map((t: string) => `#${t}`).join(" ")}</p>}
          <div className="clip-actions">
            <button className="btn small ghost" aria-pressed={clip.kept === true} onClick={() => keep(true)}>Keep</button>
            <button className="btn small ghost" aria-pressed={clip.kept === false} onClick={() => keep(false)}>Discard</button>
          </div>
          <p className="muted small flex flex-wrap items-center gap-2">{SOON.map(([, label]) => label).join(", ")} <Soon short /></p>
          {clip.captions_url && <div className="clip-actions" role="group" aria-label="Captions file">
            <span className="muted">Captions file</span>
            {["srt", "vtt", "txt"].map((f) => <button key={f} className="btn small ghost" onClick={() => downloadSubtitles(clip.id, f).catch(fail)}>{f.toUpperCase()}</button>)}
          </div>}
        </div>
      </details>
    </article>
  );
}


// Like, dislike, bookmark: round buttons over the preview.
function IconToggle({ icon, label, on, onClick }: { icon: IconName; label: string; on: boolean; onClick: () => void }) {
  return <button type="button" aria-pressed={on} aria-label={label} title={label} onClick={onClick}
    className={`grid h-8 w-8 cursor-pointer place-items-center rounded-full border-0 ${on ? "bg-lime text-ink" : "bg-[rgba(7,8,10,.78)] text-[#e9edf1]"}`}><Icon name={icon} size={18} /></button>;
}

export type ClipSort = "score" | "time" | "newest";
export type ClipFilter = "all" | "kept" | "discarded" | "bookmarked" | "liked";
const FILTER_NAMES: Record<ClipFilter, string> = { all: "All clips", kept: "Kept", discarded: "Discarded", bookmarked: "Bookmarked", liked: "Liked" };
const SORT_NAMES: Record<ClipSort, string> = { score: "Best first", time: "Earliest first", newest: "Newest first" };

export function ClipToolbar({ sort, filter, sorts, onSort, onFilter }: { sort: ClipSort; filter: ClipFilter; sorts: ClipSort[];
  onSort: (s: ClipSort) => void; onFilter: (f: ClipFilter) => void }) {
  return (
    <div className="clip-toolbar">
      <label>Sort<select value={sort} onChange={(e) => onSort(e.target.value as ClipSort)}>
        {sorts.map((s) => <option key={s} value={s}>{SORT_NAMES[s]}</option>)}</select></label>
      <label>Show<select value={filter} onChange={(e) => onFilter(e.target.value as ClipFilter)}>
        {(Object.keys(FILTER_NAMES) as ClipFilter[]).map((f) => <option key={f} value={f}>{FILTER_NAMES[f]}</option>)}</select></label>
    </div>
  );
}

const MATCH: Record<ClipFilter, (c: any) => boolean> = { all: () => true, kept: (c) => c.kept === true, discarded: (c) => c.kept === false,
  bookmarked: (c) => !!c.bookmarked, liked: (c) => c.reaction === "like" };
// For lists already in the browser (a project). The Library asks the server instead.
// "Best first" is by virality, "Earliest first" by position in the original video. The new index fields count
// within one run, so they order the list only when every clip shown has one and comes from the same run;
// otherwise (today's API, or clips from several runs) the score and the start time do.
export function arrange(clips: any[], sort: ClipSort, filter: ClipFilter): any[] {
  const out = clips.filter(MATCH[filter]);
  const oneRun = (key: string) => out.every((c) => typeof c[key] === "number" && c.job_id === out[0].job_id);
  if (sort === "time") out.sort(oneRun("timeline_index") ? (a, b) => a.timeline_index - b.timeline_index : (a, b) => a.start_sec - b.start_sec);
  else if (sort === "score") out.sort(oneRun("rank_index") ? (a, b) => a.rank_index - b.rank_index : (a, b) => b.score - a.score);
  return out;
}

// The order the cards are shown in. While clips are still arriving (`settled` false) the cards already on the
// page stay where they are and new ones join at the end, so nothing moves under the cursor; the list is put in
// its sorted order when the run ends or when the sort or filter is changed.
export function useSteadyOrder(clips: any[], sort: ClipSort, filter: ClipFilter, settled: boolean): any[] {
  const sorted = arrange(clips, sort, filter);
  const last = useRef<{ key: string; ids: string[] }>({ key: "", ids: [] });
  const key = `${sort}|${filter}`;
  let ids = sorted.map((c) => c.id);
  if (!settled && last.current.key === key) {
    const here = new Set(ids), had = new Set(last.current.ids);
    ids = [...last.current.ids.filter((id) => here.has(id)), ...ids.filter((id) => !had.has(id))];
  }
  useEffect(() => { last.current = { key, ids }; });
  const by = new Map(sorted.map((c) => [c.id, c]));
  return ids.map((id) => by.get(id));
}

const TIER_NAMES: Record<string, string> = { top: "Top pick", strong: "Strong", solid: "Solid", long_shot: "Long shot" };
const SIGNAL_NAMES: Record<string, string> = { audio: "Loud reaction", chat_motion: "Chat activity", transcript: "What was said" };

// The score on the card: "N /100" once the API sends a calibrated `display_score`, the rank and tier until then.
// The numbers behind it open on hover, on keyboard focus and on a tap or click; Escape or a tap elsewhere closes them.
export function ScoreBadge({ clip }: { clip: any }) {
  const [mode, setMode] = useState<"" | "open" | "shut">("");
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (mode !== "open") return;
    const away = (e: Event) => { if (!box.current?.contains(e.target as Node)) setMode(""); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [mode]);
  const rank = rankOf(clip), shown = typeof clip.display_score === "number" ? Math.round(clip.display_score) : null;
  if (shown === null && !rank) return null;
  const v = clip.virality || {}, tip = `score-${clip.id}`;
  const raw = typeof v.score === "number" ? v.score : null;
  // Sub-scores: the five dimensions under `scores` once the API sends them, today's four under `virality` until then.
  const parts = Object.entries({ ...v, ...(clip.scores && typeof clip.scores === "object" ? clip.scores : {}) })
    .filter(([k, n]) => k !== "score" && typeof n === "number") as [string, number][];
  const signals = Object.entries(clip.signals || {}).filter(([, share]) => (share as number) >= 0.05).sort((a, b) => (b[1] as number) - (a[1] as number));
  const rated = shown !== null || !!clip.tier;
  return (
    <span ref={box} className={`score-badge ${mode}`} onKeyDown={(e) => { if (e.key === "Escape") setMode("shut"); }}>
      <button type="button" className={shown !== null ? "rank score" : `rank ${clip.tier || "unrated"}`} aria-describedby={tip} aria-expanded={mode === "open"}
        aria-label={shown !== null ? `Score ${shown} out of 100. Show the numbers behind it.` : undefined}
        onClick={() => setMode(mode === "open" ? "shut" : "open")} onBlur={() => setMode("")}>
        {shown !== null ? <><b>{shown}</b><small>/100</small></>
          : <><b>#{rank}</b>{clip.rank_of ? <> of {clip.rank_of}</> : null}{clip.tier && <> · {TIER_NAMES[clip.tier]}</>}</>}
      </button>
      <span role="tooltip" id={tip} className="score-tip">
        {rated
          ? <><strong>{raw !== null ? `AI rating ${raw} of 100` : "Rated by the AI"}{rank ? ` · #${rank}${clip.rank_of ? ` of ${clip.rank_of}` : ""}` : ""}</strong>
              {parts.length > 0 && <span className="parts">{parts.map(([k, n]) => <span key={k}>{scoreLabel(k)} <b>{n}</b></span>)}</span>}</>
          : <strong>Ranked by how strongly this moment stood out in the video. It has no AI rating.</strong>}
        {shown !== null && <span>The {shown} on the card is the AI rating scaled across this video's clips, so the best one lands in the 90s. The order is the AI's own.</span>}
        {signals.length > 0 && <span>Picked for: {signals.map(([k, share]) => `${SIGNAL_NAMES[k] || k} ${Math.round((share as number) * 100)}%`).join(", ")}</span>}
        {(clip.reason || clip.why) && <span>{clip.reason || clip.why}</span>}
        {rated && <span className="muted">The rating is the AI's opinion of the clip. It does not say how many views a clip will get.</span>}
      </span>
    </span>
  );
}
