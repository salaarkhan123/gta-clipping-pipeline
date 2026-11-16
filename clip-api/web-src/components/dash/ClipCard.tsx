"use client";
import Link from "next/link";
import { Stars } from "@/components/Chrome";
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
  const keep = (kept: boolean) => api(`/v1/clips/${clip.id}/feedback`, { body: { kept } }).then(() => onChange({ ...clip, kept })).catch(fail);
  return (
    <figure className={`clip ${clip.kept === false ? "dropped" : ""}`}>
      <video controls preload="none" poster={clip.thumb_url || undefined} src={clip.video_url} />
      <figcaption>
        <strong>{clip.title || `Clip ${clip.index}`}</strong>
        {clip.virality && <Stars score={clip.virality.score} />}
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
      </figcaption>
    </figure>
  );
}
