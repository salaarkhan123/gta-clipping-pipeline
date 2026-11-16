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

// One clip: preview, title, score, times, and its actions. `project` links back to where it came from (Library).
export function ClipCard({ clip, onChange, project }: { clip: any; onChange: (c: any) => void; project?: { id: string; name: string } }) {
  const { fail } = useDash();
  // Pressing the active choice again clears it.
  const send = (body: Record<string, unknown>) => api(`/v1/clips/${clip.id}/feedback`, { body }).then((r) => onChange({ ...clip, ...r })).catch(fail);
  const keep = (kept: boolean) => send({ kept: clip.kept === kept ? null : kept });
  const react = (reaction: "like" | "dislike") => send({ reaction: clip.reaction === reaction ? null : reaction });
  return (
    <figure className={`clip ${clip.kept === false ? "dropped" : ""}`}>
      <video controls preload="none" poster={clip.thumb_url || undefined} src={clip.video_url} />
      <figcaption>
        <strong>{clip.title || `Clip ${clip.index}`}</strong>
        <ScoreBadge clip={clip} />
        <span className="muted">{clock(clip.start_sec)} to {clock(clip.end_sec)}</span>
        {project && <Link className="muted" href={`/dashboard/project/?id=${project.id}`}>From {project.name}</Link>}
        {clip.description && <p>{clip.description}</p>}
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
export function arrange(clips: any[], sort: ClipSort, filter: ClipFilter): any[] {
  const out = clips.filter(MATCH[filter]);
  if (sort === "time") out.sort((a, b) => a.start_sec - b.start_sec);
  else if (sort === "score") out.sort((a, b) => b.score - a.score);
  return out;
}

const TIER_NAMES: Record<string, string> = { top: "Top pick", strong: "Strong", solid: "Solid", long_shot: "Long shot" };
const PART_NAMES: [string, string][] = [["hook", "Hook"], ["flow", "Flow"], ["value", "Value"], ["trend", "Trend"]];
const SIGNAL_NAMES: Record<string, string> = { audio: "Loud reaction", chat_motion: "Chat activity", transcript: "What was said" };

// Rank and tier on the card; the numbers behind them only on hover, focus or tap.
export function ScoreBadge({ clip }: { clip: any }) {
  if (!clip.rank) return null;
  const v = clip.virality, tip = `score-${clip.id}`;
  const signals = Object.entries(clip.signals || {}).filter(([, share]) => (share as number) >= 0.05).sort((a, b) => (b[1] as number) - (a[1] as number));
  return (
    <span className="score-badge">
      <button type="button" className={`rank ${clip.tier || "unrated"}`} aria-describedby={tip}>
        <b>#{clip.rank}</b> of {clip.rank_of}{clip.tier && <> · {TIER_NAMES[clip.tier]}</>}
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
