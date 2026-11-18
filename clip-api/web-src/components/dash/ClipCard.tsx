"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API, api, ApiError, clock, getToken } from "@/lib/api";
import { Icon, IconName } from "./Icon";
import { useDash } from "./Shell";

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

const SOON: [IconName, string][] = [["calendar", "Schedule"], ["scissors", "Trim"], ["reframe", "Reframe"]];

// One clip as a card: tick box, rank and title, the preview with its time range, the score, and its actions.
// `project` links back to where it came from (Library). `lit` marks the card the timeline just jumped to.
// `onSelect` adds the tick box (the project page's bulk actions).
export function ClipCard({ clip, onChange, project, lit, number, selected, onSelect }: { clip: any; onChange: (c: any) => void;
  project?: { id: string; name: string }; lit?: boolean; number?: number; selected?: boolean; onSelect?: (id: string, on: boolean) => void }) {
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
  return (
    <article id={`clip-${clip.id}`} tabIndex={-1} aria-label={name}
      className={`clip ${clip.kept === false ? "dropped" : ""} ${lit ? "lit" : ""} ${selected ? "picked" : ""}`}>
      <header className="clip-top">
        {onSelect && <input type="checkbox" checked={!!selected} aria-label={`Select ${name}`} onChange={(e) => onSelect(clip.id, e.target.checked)} />}
        <h3 title={name}>{rank && <b>#{rank}</b>} {name}</h3>
      </header>
      <div className="clip-media">
        <video controls preload="none" poster={clip.thumb_url || undefined} src={clip.video_url} />
        <span className="clip-time">{clock(clip.start_sec)} – {clock(clip.end_sec)}</span>
        {clip.edited === true && <span className="clip-edited">Edited</span>}
        <div className="clip-rate" role="group" aria-label="Rate this clip">
          <IconToggle icon="like" label="Like" on={clip.reaction === "like"} onClick={() => react("like")} />
          <IconToggle icon="dislike" label="Dislike" on={clip.reaction === "dislike"} onClick={() => react("dislike")} />
          <IconToggle icon="bookmark" label="Bookmark" on={!!clip.bookmarked} onClick={() => send({ bookmarked: !clip.bookmarked })} />
        </div>
      </div>
      <div className="clip-bar">
        <ScoreBadge clip={clip} />
        <div className="clip-icons" role="group" aria-label="Clip actions">
          <a className="icon-btn go" href={clip.video_url} download aria-label={`Download ${name}`} title="Download"><Icon name="download" size={18} /></a>
          <button type="button" className="icon-btn" disabled={!clip.captions_url} aria-label={clip.captions_url ? `Download the captions file for ${name}` : "No captions file: this clip has no captions"}
            title={clip.captions_url ? "Captions file (SRT)" : "This clip has no captions"} onClick={() => downloadSubtitles(clip.id).catch(fail)}><Icon name="captions" size={18} /></button>
        </div>
      </div>
      <p className="clip-desc" title={clip.description || undefined}>{clip.description || <span className="muted">No description for this clip.</span>}</p>
      {project && <Link className="muted clip-from" href={`/dashboard/project/?id=${project.id}`}>From {project.name}</Link>}
      <details className="clip-more">
        <summary>More</summary>
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
          <p className="muted small">Coming soon: {SOON.map(([, label]) => label.toLowerCase()).join(", ")}.</p>
          {clip.captions_url && <div className="clip-actions" role="group" aria-label="Captions file">
            <span className="muted">Captions file</span>
            {["srt", "vtt", "txt"].map((f) => <button key={f} className="btn small ghost" onClick={() => downloadSubtitles(clip.id, f).catch(fail)}>{f.toUpperCase()}</button>)}
          </div>}
        </div>
      </details>
    </article>
  );
}

function IconToggle({ icon, label, on, onClick }: { icon: IconName; label: string; on: boolean; onClick: () => void }) {
  return <button type="button" className="icon-btn" aria-pressed={on} aria-label={label} title={label} onClick={onClick}><Icon name={icon} size={18} /></button>;
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
const PART_NAMES: Record<string, string> = { hook: "Hook", flow: "Flow", story: "Story", value: "Value", trend: "Trend", engagement: "Engagement", reach: "Reach" };
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
          ? <><strong>{raw !== null ? `AI score ${raw} of 100` : "Rated by the AI"}{rank ? ` · #${rank}${clip.rank_of ? ` of ${clip.rank_of}` : ""}` : ""}</strong>
              {parts.length > 0 && <span className="parts">{parts.map(([k, n]) => <span key={k}>{PART_NAMES[k] || k} <b>{n}</b></span>)}</span>}</>
          : <strong>Ranked by how strongly this moment stood out in the video. It has no AI rating.</strong>}
        {shown !== null && <span>The {shown} on the card is the AI score scaled across this video's clips, so the best one lands in the 90s. The order is the AI's own.</span>}
        {signals.length > 0 && <span>Picked for: {signals.map(([k, share]) => `${SIGNAL_NAMES[k] || k} ${Math.round((share as number) * 100)}%`).join(", ")}</span>}
        {(clip.reason || clip.why) && <span>{clip.reason || clip.why}</span>}
        {rated && <span className="muted">The score is an AI opinion of the clip, not a forecast of views.</span>}
      </span>
    </span>
  );
}
