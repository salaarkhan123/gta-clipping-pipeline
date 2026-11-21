"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, clock } from "@/lib/api";
import { Routes } from "@/lib/routes";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { downloadSubtitles } from "@/components/dash/ClipCard";
import { Icon, IconName } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { PublishPanel } from "@/components/publish/PublishPanel";
import { Feedback } from "./ClipTile";
import { ExportPanel } from "./ExportPanel";
import { RatingParts } from "./Rating";
import {
  ASPECT_FRAME, AspectRatio, Cue, cueAt, aspectFromOptions, isLowResPreview, kindName, lengthOf,
  OVERLAY_ASPECTS, parseVtt, ratingOf, Shape,
} from "./model";

// Still planned: shown so people know they are coming, never clickable.
const SOON: [IconName, string][] = [["image", "AI B-roll"]];
type Tab = "transcript" | "rating" | "export";

// The clip's words with clip times (GET /v1/clips/{id}/subtitles?format=vtt), asked once per clip per visit.
const said = new Map<string, Promise<Cue[] | string>>();
function transcriptOf(clipId: string): Promise<Cue[] | string> {
  if (!said.has(clipId)) said.set(clipId, api<string>(`/v1/clips/${clipId}/subtitles?format=vtt`)
    .then((t) => parseVtt(typeof t === "string" ? t : ""))
    .catch((e) => { said.delete(clipId); return e instanceof ApiError && e.status === 404 ? "This clip has no transcript: it was made with captions off, or nobody speaks in it." : "The transcript could not be loaded."; }));
  return said.get(clipId)!;
}

export type PlayerProps = {
  clips: any[]; at: number; onAt: (i: number) => void; onClose: () => void;
  nameOf: (c: any) => string; shapeOf: (c: any) => Shape; gameOf: (c: any) => string | null; jobOf: (c: any) => any;
  uploadId: string; sourceSide: number | null; cap: number | null; resolutions: string[]; known: Routes | null;
  onFeedback: (c: any, f: Feedback) => void; onRenamed: (c: any) => void; onReload: () => void;
};

// The clip player: the clip large with its captions, the transcript beside it (the line being said is lit; a click
// jumps there), the AI rating, rename, export, download and the editor. Previous and next walk the grid's order
// (also the arrow keys); Escape closes.
export function ClipPlayer(p: PlayerProps) {
  const { fail } = useDash();
  const dialog = useRef<HTMLDialogElement>(null), video = useRef<HTMLVideoElement>(null);
  const clip = p.clips[p.at];
  const [tab, setTab] = useState<Tab>("transcript");
  const [cues, setCues] = useState<Cue[] | string | null>(null), [now, setNow] = useState(0);
  const [cc, setCc] = useState(false), [track, setTrack] = useState<string | null>(null);
  const [naming, setNaming] = useState<string | null>(null);
  const [frame, setFrame] = useState<AspectRatio | null>(null);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    if (!clip) return;
    let on = true;
    setCues(null); setNow(0); setNaming(null); setFrame(null);
    if (clip.captions_url) transcriptOf(clip.id).then((r) => on && setCues(r));
    else setCues("This clip has no transcript: it was made with captions off, or nobody speaks in it.");
    return () => { on = false; };
  }, [clip?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  // The same words as a subtitle track, for the CC button (the captions burned into the video are always there).
  useEffect(() => {
    if (!Array.isArray(cues) || !cues.length) { setTrack(null); return; }
    const t = (s: number) => new Date(s * 1000).toISOString().slice(11, 23);
    const url = URL.createObjectURL(new Blob([`WEBVTT\n\n${cues.map((c) => `${t(c.start)} --> ${t(c.end)}\n${c.text}\n`).join("\n")}`], { type: "text/vtt" }));
    setTrack(url);
    return () => URL.revokeObjectURL(url);
  }, [cues]);
  useEffect(() => {
    const tt = video.current?.textTracks?.[0];
    if (tt) tt.mode = cc ? "showing" : "hidden";
  }, [cc, track]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [role=radiogroup]")) return;
      if (e.key === "ArrowRight" && p.at < p.clips.length - 1) { e.preventDefault(); p.onAt(p.at + 1); }
      if (e.key === "ArrowLeft" && p.at > 0) { e.preventDefault(); p.onAt(p.at - 1); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [p]);
  if (!clip) return null;

  const r = ratingOf(clip), name = p.nameOf(clip), game = p.gameOf(clip);
  const job = p.jobOf(clip);
  // A link imported with a range: clip times count from the start of the imported part (job `import.range`).
  const start = job?.import?.range?.start_sec, offset = typeof start === "number" ? start : 0;
  const lit = Array.isArray(cues) ? cueAt(cues, now) : -1;
  const titles: string[] = Array.isArray(clip.titles) ? clip.titles.filter((t: string) => t && t !== clip.title) : [];
  const aspect = frame ?? aspectFromOptions(job?.options?.aspect, job?.options?.vertical);
  const preview = isLowResPreview(clip);
  const rename = (title: string) => {
    const t = title.trim();
    if (!t || t === clip.title) { setNaming(null); return; }
    api(`/v1/clips/${clip.id}`, { method: "PATCH", body: { title: t } })
      .then((n) => { p.onRenamed({ ...clip, ...n, video_url: clip.video_url, preview_url: clip.preview_url, thumb_url: clip.thumb_url || n.thumb_url }); setNaming(null); })
      .catch(fail);
  };
  const seek = (s: number) => { if (video.current) { video.current.currentTime = s; video.current.play().catch(() => {}); } };
  const tall = aspect !== "16:9";

  return (
    <dialog ref={dialog} aria-label={name} onCancel={(e) => { e.preventDefault(); p.onClose(); }}
      onClick={(e) => { if (e.target === dialog.current) p.onClose(); }}
      className="m-0 h-[100dvh] max-h-none w-screen max-w-none border-0 bg-transparent p-0 text-text backdrop:bg-[rgba(0,0,0,.82)] backdrop:[backdrop-filter:blur(8px)]">
      <div className="mx-auto flex h-full w-full max-w-[1400px] flex-col gap-3 p-5 narrow:gap-2 narrow:p-0">
        <header className="flex flex-none items-center justify-between gap-3 narrow:px-4 narrow:pt-3">
          <span className="font-mono text-[13px] tabular-nums text-fg-2" aria-live="polite">{p.at + 1} / {p.clips.length}</span>
          <div className="flex items-center gap-2">
            <RoundBtn icon="back" label="Previous clip" disabled={p.at === 0} onClick={() => p.onAt(p.at - 1)} />
            <RoundBtn icon="arrow" label="Next clip" disabled={p.at >= p.clips.length - 1} onClick={() => p.onAt(p.at + 1)} />
            <RoundBtn icon="close" label="Close" onClick={p.onClose} />
          </div>
        </header>
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_420px] gap-5 mid:grid-cols-[minmax(0,1fr)_360px] narrow:flex narrow:flex-col narrow:gap-0 narrow:overflow-y-auto">
          <div className="grid min-h-0 place-items-center rounded-24 bg-[#050505] p-4 narrow:flex-none narrow:rounded-none narrow:p-0">
            <div className={`relative ${ASPECT_FRAME[aspect]} ${tall ? "h-full max-h-[calc(100dvh-120px)] narrow:h-[62dvh] narrow:max-h-none narrow:w-auto" : "w-full max-w-full"} max-w-full overflow-hidden rounded-16 bg-black narrow:rounded-none`}>
              {preview && <span className="pointer-events-none absolute left-3 top-3 z-[2] rounded-8 border border-solid border-line-strong bg-[rgba(0,0,0,.72)] px-2.5 py-1 font-sans text-[11px] font-semibold uppercase tracking-[.06em] text-text">Low-res preview</span>}
              {clip.video_url ? (
                <video key={clip.id} ref={video} controls autoPlay playsInline preload="auto" src={clip.video_url} poster={clip.thumb_url || undefined}
                  onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} className="absolute inset-0 h-full w-full bg-black object-contain">
                  {track && <track kind="subtitles" src={track} srcLang={job?.options?.source_lang || "und"} label="Transcript" />}
                </video>
              ) : <p className="absolute inset-0 m-0 grid place-items-center p-6 text-center text-[14px] text-fg-2">This clip has no video yet. Export it to render it.</p>}
            </div>
          </div>

          <aside className="flex min-h-0 flex-col gap-4 narrow:flex-none overflow-y-auto rounded-24 border border-solid border-line bg-card p-5 narrow:overflow-visible narrow:rounded-none narrow:border-x-0 narrow:border-b-0 narrow:p-4">
            <div className="grid gap-[10px]">
              <div className="flex items-start gap-3">
                {r.shown !== null && <div className="grid flex-none place-items-center rounded-16 bg-lime-wash px-3 py-2 text-center" title="AI rating">
                  <b className="font-sans text-[26px] font-semibold leading-none tabular-nums tracking-[-0.03em] text-lime">{r.shown}</b>
                  <span className="mt-[3px] text-[10px] font-medium uppercase tracking-[.06em] text-lime">AI rating</span></div>}
                <div className="grid min-w-0 flex-1 gap-1">
                  {naming === null ? (
                    <h2 className="m-0 flex items-start gap-2 text-[18px] font-semibold leading-[1.3] tracking-[-0.015em]">
                      <span className="min-w-0 [overflow-wrap:anywhere]">{name}</span>
                      <button type="button" aria-label="Rename" title="Rename" onClick={() => setNaming(clip.title || name)}
                        className="mt-[1px] grid h-7 w-7 flex-none cursor-pointer place-items-center rounded-full border-0 bg-transparent text-fg-2 hover:bg-chip-hover hover:text-text"><Icon name="pencil" size={15} /></button>
                    </h2>
                  ) : (
                    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); rename(naming); }}>
                      <input autoFocus value={naming} maxLength={80} aria-label="Clip title" onChange={(e) => setNaming(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); setNaming(null); } }}
                        className="min-w-0 flex-1 rounded-12 border border-solid border-line-strong bg-bg-2 px-3 py-2 font-sans text-[14px] text-text focus:border-lime focus:outline-none" />
                      <button type="submit" className="btn small primary">Save</button>
                    </form>
                  )}
                  <p className="m-0 flex flex-wrap gap-x-[6px] text-[12.5px] text-fg-2">
                    <span className="tabular-nums">{clock(lengthOf(clip))}</span>
                    {game && <><span aria-hidden="true">·</span><span>{game}</span></>}
                    {clip.kind && <><span aria-hidden="true">·</span><span>{kindName(clip.kind)}</span></>}
                    <span aria-hidden="true">·</span><span>From {clock(clip.start_sec + offset)} in {offset ? "the original stream" : "the video"}</span>
                  </p>
                </div>
              </div>
              {naming !== null && titles.length > 0 && <div className="grid gap-[6px]">
                <span className="text-[12px] text-fg-2">The AI's other titles</span>
                {titles.map((t) => <button key={t} type="button" onClick={() => rename(t)}
                  className="cursor-pointer rounded-12 border border-solid border-line bg-transparent px-3 py-2 text-left font-sans text-[13px] text-soft hover:border-line-strong hover:text-text">{t}</button>)}
              </div>}
            </div>

            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Clip actions">
              <Link className="btn small primary" href={`/dashboard/edit/?project=${p.uploadId}&clip=${clip.id}`}><Icon name="sliders" size={15} />Open in editor</Link>
              {clip.video_url && <a className="btn small ghost" href={clip.video_url} download title="The file as it is now. Free, as often as you like."><Icon name="download" size={15} />Download</a>}
              <button type="button" className="btn small ghost" onClick={() => setPublishing((v) => !v)} title="Publish or schedule to connected accounts">
                <Icon name="send" size={15} />Publish
              </button>
              {cues && Array.isArray(cues) && <button type="button" className="btn small ghost" aria-pressed={cc} onClick={() => setCc(!cc)} title="Show the transcript as subtitles on the player"><Icon name="captions" size={15} />CC</button>}
            </div>
            {publishing && <PublishPanel clipId={clip.id} onClose={() => setPublishing(false)} />}
            <div role="radiogroup" aria-label="Aspect" className="flex flex-wrap items-center gap-[6px]">
              <span className="text-[12px] text-fg-2">Aspect</span>
              {OVERLAY_ASPECTS.map((a) => (
                <button key={a} type="button" role="radio" aria-checked={aspect === a} onClick={() => setFrame(a)}
                  title={`Show the player as ${a}. Does not re-render the file; export or the editor changes the real shape.`}
                  className={`min-h-[32px] cursor-pointer rounded-pill border border-solid px-3 font-sans text-[12.5px] font-medium tabular-nums
                    ${aspect === a ? "border-lime bg-lime text-ink" : "border-line-strong bg-transparent text-soft hover:bg-[rgba(255,255,255,.06)] hover:text-text"}`}>{a}</button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-[6px]" role="group" aria-label="Your feedback">
              <Pill on={clip.kept === true} onClick={() => p.onFeedback(clip, { kept: clip.kept === true ? null : true })}>Keep</Pill>
              <Pill on={clip.kept === false} onClick={() => p.onFeedback(clip, { kept: clip.kept === false ? null : false })}>Discard</Pill>
              <Pill icon="like" label="Like" on={clip.reaction === "like"} onClick={() => p.onFeedback(clip, { reaction: clip.reaction === "like" ? null : "like" })} />
              <Pill icon="dislike" label="Dislike" on={clip.reaction === "dislike"} onClick={() => p.onFeedback(clip, { reaction: clip.reaction === "dislike" ? null : "dislike" })} />
              <Pill icon="bookmark" label="Bookmark" on={!!clip.bookmarked} onClick={() => p.onFeedback(clip, { bookmarked: !clip.bookmarked })} />
            </div>

            <div role="tablist" aria-label="Clip details" className="flex gap-1 border-0 border-b border-solid border-line">
              {([["transcript", "Transcript"], ["rating", "AI rating"], ["export", "Export"]] as [Tab, string][]).map(([t, label]) => (
                <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={`-mb-px cursor-pointer border-0 border-b-2 border-solid bg-transparent px-3 pb-[10px] pt-1 font-sans text-[13px] font-medium ${tab === t ? "border-text text-text" : "border-transparent text-fg-2 hover:text-text"}`}>{label}</button>))}
            </div>
            <div role="tabpanel" className="min-h-[120px]">
              {tab === "transcript" && (cues === null ? <p className="m-0 text-[13px] text-fg-2">Loading the transcript…</p>
                : typeof cues === "string" ? <p className="m-0 text-[13px] text-fg-2">{cues}</p>
                : !cues.length ? <p className="m-0 text-[13px] text-fg-2">Nobody speaks in this clip.</p>
                : <ol className="m-0 grid list-none gap-[2px] p-0" aria-label="Transcript">
                    {cues.map((c, i) => (
                      <li key={i}><button type="button" onClick={() => seek(c.start)} aria-current={i === lit ? "true" : undefined}
                        className={`grid w-full cursor-pointer grid-cols-[44px_1fr] gap-2 rounded-8 border-0 px-2 py-[6px] text-left font-sans text-[13.5px] leading-[1.45]
                          ${i === lit ? "bg-lime-wash text-text" : "bg-transparent text-soft hover:bg-[rgba(255,255,255,.04)]"}`}>
                        <span className="font-mono text-[11.5px] tabular-nums text-fg-3">{clock(c.start)}</span><span>{c.text}</span></button></li>))}
                  </ol>)}
              {tab === "rating" && (r.shown !== null ? <RatingParts r={r} />
                : <p className="m-0 text-[13px] leading-[1.5] text-fg-2">The AI did not rate this clip. It is #{r.rank ?? "?"}{r.of ? ` of ${r.of}` : ""} in its run, placed by how strongly the moment stood out (loudness, chat, speech).</p>)}
              {tab === "export" && (p.known?.exportQuote && p.known.exportRoute
                ? <ExportPanel clip={clip} job={job} sourceSide={p.sourceSide} cap={p.cap} resolutions={p.resolutions} known={p.known} onDone={p.onReload} />
                : <p className="m-0 text-[13px] text-fg-2">{p.known ? "Export isn't available on this server yet." : "Loading…"}</p>)}
            </div>

            {clip.captions_url && <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-fg-2">Captions file
              {["srt", "vtt", "txt"].map((f) => <button key={f} type="button" className="link text-[12.5px] text-soft" onClick={() => downloadSubtitles(clip.id, f).catch(fail)}>{f.toUpperCase()}</button>)}
            </div>}
            <div className="mt-auto grid gap-2 border-0 border-t border-solid border-line pt-4">
              {SOON.map(([icon, label]) => (
                <div key={label} aria-disabled="true" className="flex cursor-default items-center gap-[10px] text-[13px] text-fg-3">
                  <Icon name={icon} size={15} />{label}<ComingSoonBadge short className="ml-auto" /></div>))}
            </div>
          </aside>
        </div>
      </div>
    </dialog>
  );
}

function RoundBtn({ icon, label, disabled, onClick }: { icon: IconName; label: string; disabled?: boolean; onClick: () => void }) {
  return <button type="button" aria-label={label} title={label} disabled={disabled} onClick={onClick}
    className={`grid h-10 w-10 cursor-pointer place-items-center rounded-full border border-solid border-line-strong bg-[rgba(20,20,20,.9)] text-text enabled:hover:bg-raised disabled:cursor-default disabled:opacity-30`}>
    <Icon name={icon} size={18} /></button>;
}

function Pill({ on, onClick, icon, label, children }: { on: boolean; onClick: () => void; icon?: IconName; label?: string; children?: React.ReactNode }) {
  return <button type="button" aria-pressed={on} aria-label={label} title={label} onClick={onClick}
    className={`inline-flex min-h-[32px] cursor-pointer items-center gap-[6px] rounded-pill border border-solid px-3 font-sans text-[12.5px] font-medium
      ${on ? "border-lime bg-lime text-ink" : "border-line-strong bg-transparent text-soft hover:bg-[rgba(255,255,255,.06)] hover:text-text"}`}>
    {icon && <Icon name={icon} size={15} />}{children}</button>;
}
