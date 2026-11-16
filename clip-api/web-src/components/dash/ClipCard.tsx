"use client";
import Link from "next/link";
import { API, api, ApiError, clock, getToken } from "@/lib/api";
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
export const nameOf = (c: any): string => c.title || `Clip ${numberOf(c)}`;

// One clip: preview, title, score, times, and its actions. `project` links back to where it came from (Library).
// `lit` marks the card the timeline just jumped to.
export function ClipCard({ clip, onChange, project, lit }: { clip: any; onChange: (c: any) => void; project?: { id: string; name: string }; lit?: boolean }) {
  const { fail } = useDash();
  // Pressing the active choice again clears it.
  const send = (body: Record<string, unknown>) => api(`/v1/clips/${clip.id}/feedback`, { body }).then((r) => onChange({ ...clip, ...r })).catch(fail);
  const keep = (kept: boolean) => send({ kept: clip.kept === kept ? null : kept });
  const react = (reaction: "like" | "dislike") => send({ reaction: clip.reaction === reaction ? null : reaction });
  // The AI offers a few titles; picking one changes the clip's title everywhere. Nothing is re-rendered.
  const titles: string[] = clip.titles?.length ? (clip.titles.includes(clip.title) ? clip.titles : [clip.title, ...clip.titles]) : [];
  const retitle = (title: string) => api(`/v1/clips/${clip.id}`, { method: "PATCH", body: { title } }).then((r) => onChange({ ...clip, ...r })).catch(fail);
  return (
    <figure id={`clip-${clip.id}`} tabIndex={-1} className={`clip ${clip.kept === false ? "dropped" : ""} ${lit ? "lit" : ""}`}>
      <video controls preload="none" poster={clip.thumb_url || undefined} src={clip.video_url} />
      <figcaption>
        <strong>{nameOf(clip)}</strong>
        {titles.length > 1 && <label className="title-pick">Title
          <select value={clip.title} onChange={(e) => retitle(e.target.value)}>
            {titles.map((x) => <option key={x} value={x}>{x}</option>)}
          </select></label>}
        <ScoreBadge clip={clip} />
        <span className="muted">{clock(clip.start_sec)} to {clock(clip.end_sec)}</span>
        {project && <Link className="muted" href={`/dashboard/project/?id=${project.id}`}>From {project.name}</Link>}
        {clip.hook && <p className="muted">{clip.hook_on_screen ? "On-screen hook" : "Hook idea (not on the video)"}: “{clip.hook}”</p>}
        {clip.description && <p>{clip.description}</p>}
        {clip.suggestion?.text && <p className="tip"><b>Tip</b> {clip.suggestion.text}</p>}
        {clip.hashtags?.length > 0 && <p className="tags">{clip.hashtags.map((t: string) => `#${t}`).join(" ")}</p>}
        <div className="clip-actions">
          <a className="btn small primary" href={clip.video_url} download>Download</a>
          {clip.captions_url && <button className="btn small ghost" onClick={() => downloadSubtitles(clip.id).catch(fail)}>Subtitles</button>}
          <button className="btn small ghost" aria-pressed={clip.kept === true} onClick={() => keep(true)}>Keep</button>
          <button className="btn small ghost" aria-pressed={clip.kept === false} onClick={() => keep(false)}>Discard</button>
        </div>
        <div className="clip-actions" role="group" aria-label="Rate this clip">
          <button className="btn small ghost" aria-pressed={clip.reaction === "like"} onClick={() => react("like")}>Like</button>
          <button className="btn small ghost" aria-pressed={clip.reaction === "dislike"} onClick={() => react("dislike")}>Dislike</button>
          <button className="btn small ghost" aria-pressed={!!clip.bookmarked} onClick={() => send({ bookmarked: !clip.bookmarked })}>
            {clip.bookmarked ? "Bookmarked" : "Bookmark"}</button>
        </div>
      </figcaption>
    </figure>
  );
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

const TIER_NAMES: Record<string, string> = { top: "Top pick", strong: "Strong", solid: "Solid", long_shot: "Long shot" };
const PART_NAMES: [string, string][] = [["hook", "Hook"], ["flow", "Flow"], ["value", "Value"], ["trend", "Trend"]];
const SIGNAL_NAMES: Record<string, string> = { audio: "Loud reaction", chat_motion: "Chat activity", transcript: "What was said" };

// Rank and tier on the card; the numbers behind them only on hover, focus or tap.
export function ScoreBadge({ clip }: { clip: any }) {
  const rank = rankOf(clip);
  if (!rank) return null;
  const v = clip.virality || {}, tip = `score-${clip.id}`;
  const signals = Object.entries(clip.signals || {}).filter(([, share]) => (share as number) >= 0.05).sort((a, b) => (b[1] as number) - (a[1] as number));
  return (
    <span className="score-badge">
      <button type="button" className={`rank ${clip.tier || "unrated"}`} aria-describedby={tip}>
        <b>#{rank}</b>{clip.rank_of ? <> of {clip.rank_of}</> : null}{clip.tier && <> · {TIER_NAMES[clip.tier]}</>}
      </button>
      <span role="tooltip" id={tip} className="score-tip">
        {clip.tier
          ? <><strong>AI score {v.score} of 100</strong>
              <span className="parts">{PART_NAMES.filter(([k]) => typeof v[k] === "number").map(([k, name]) => <span key={k}>{name} <b>{v[k]}</b></span>)}</span></>
          : <strong>Ranked by how strongly this moment stood out in the video. It has no AI rating.</strong>}
        {signals.length > 0 && <span>Picked for: {signals.map(([k, share]) => `${SIGNAL_NAMES[k] || k} ${Math.round((share as number) * 100)}%`).join(", ")}</span>}
        {clip.reason && <span>{clip.reason}</span>}
        {clip.tier && <span className="muted">The score is an AI opinion of the clip, not a forecast of views.</span>}
      </span>
    </span>
  );
}
