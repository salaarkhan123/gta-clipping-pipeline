"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, clock, uploadFile, VIDEO_TYPES, videoFileProblem } from "@/lib/api";
import { Icon } from "./Icon";
import { ImportBox, useImportSources } from "./ImportBox";
import { useDash } from "./Shell";

export const ACCEPT = VIDEO_TYPES + ",video/*";
type Progress = { name: string; pct: number };

// One upload at a time, with progress and cancel. `onDone` gets the new upload.
export function useUpload(onDone: (upload: any) => void) {
  const { fail } = useDash();
  const [up, setUp] = useState<Progress | null>(null);
  const abort = useRef<(() => void) | null>(null), run = useRef(0), done = useRef(onDone);
  done.current = onDone;

  const start = useCallback(async (file: File) => {
    const mine = ++run.current;                        // a cancelled upload must not touch the one that replaced it
    setUp({ name: file.name, pct: 0 });
    const { promise, abort: a } = uploadFile(file, (f) => mine === run.current && setUp({ name: file.name, pct: Math.round(f * 100) }));
    abort.current = a;
    try { done.current(await promise); }
    catch (e) {
      if (!(e instanceof ApiError && e.code === "aborted")) fail(e);
      if (mine === run.current) setUp(null);
    }
    finally { if (mine === run.current) abort.current = null; }
  }, [fail]);
  const cancel = useCallback(() => abort.current?.(), []);
  return { up, start, cancel };
}

export function UploadProgress({ up, onCancel }: { up: Progress; onCancel: () => void }) {
  return (
    <div className="uploading">
      <p>Uploading {up.name}</p>
      <progress max={100} value={up.pct} aria-label={`Uploading ${up.name}`} />
      <p className="muted">{up.pct}% <button className="link" onClick={onCancel}>Cancel</button></p>
    </div>
  );
}

// What the chosen video is for: the dialog's heading, and the query that opens the right tool on the project page.
// `path`: the page that opens with the chosen video (default: its project page).
export type VideoTarget = { title: string; query: string; path?: string };

// "Which video?" for a tool tile or a template. With no projects it goes straight to the file chooser; otherwise
// one dialog lists the stored videos next to an upload button. Either way the project opens with `target.query`.
export function useVideoChooser(projects: any[] | null) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null), waiting = useRef<VideoTarget | null>(null);
  const [picking, setPicking] = useState<{ target: VideoTarget; file: File | null } | null>(null);

  const choose = (target: VideoTarget) => {
    if (projects && !projects.length) { waiting.current = target; input.current?.click(); }
    else setPicking({ target, file: null });
  };
  const element = (
    <>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => {
        const file = e.target.files?.[0]; e.target.value = "";
        if (file && waiting.current) setPicking({ target: waiting.current, file });
      }} />
      {picking && <VideoPicker title={picking.target.title} projects={projects} file={picking.file} onClose={() => setPicking(null)}
        onPick={(id) => router.push(`${picking.target.path || "/dashboard/project/"}?id=${id}${picking.target.query ? `&${picking.target.query}` : ""}`)} />}
    </>
  );
  return { choose, element };
}

function VideoPicker({ title, projects, file, onPick, onClose }: { title: string; projects: any[] | null; file: File | null;
  onPick: (uploadId: string) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState("");
  const { up, start, cancel } = useUpload((u) => onPick(u.upload_id));
  const sources = useImportSources();

  function take(f: File | null | undefined) {
    if (!f) return;
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start(f);
  }
  useEffect(() => {
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
    take(file);
    return cancel;                                     // closing the dialog stops its upload
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <dialog ref={dialog} className="picker" aria-labelledby="picker-title" onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}>
      <div className="picker-body">
        <div className="picker-head">
          <h2 id="picker-title">{title}</h2>
          <button className="icon-btn" aria-label="Close" onClick={() => dialog.current?.close()}><Icon name="close" /></button>
        </div>
        {up ? <UploadProgress up={up} onCancel={cancel} /> : <>
          <p className="muted">Pick one of your videos, or upload a new one.</p>
          <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
          <div><button className="btn primary" onClick={() => input.current?.click()}><Icon name="upload" />Upload a video</button></div>
          {problem && <p className="error" role="alert">{problem}</p>}
          {sources && <ImportBox sources={sources} compact onReady={(u) => onPick(u.upload_id)} />}
          {projects === null ? <p className="muted">Loading your videos…</p> : projects.length > 0 && (
            <ul className="picker-list" aria-label="Your videos">
              {projects.map((p) => (
                <li key={p.upload_id}>
                  <button onClick={() => onPick(p.upload_id)}>
                    <span className="picker-thumb" aria-hidden="true">{p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" /> : <Icon name="film" />}</span>
                    <span><strong>{p.filename}</strong><span className="muted">{clock(p.duration_sec)} · {p.clips} clip{p.clips === 1 ? "" : "s"}</span></span>
                  </button>
                </li>))}
            </ul>)}
        </>}
      </div>
    </dialog>
  );
}
