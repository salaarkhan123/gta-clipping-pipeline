"use client";
// Dashboard-wide Find palette (Cmd+K / Ctrl+K). Instant transcript search when the video is indexed;
// otherwise starts Video Finder (POST /v1/find) with the same defaults as Find moments.
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, clock } from "@/lib/api";
import {
  defaultFindBody, findProjectHref, filterProjects, GlobalFindPhase, projectIdFromLocation,
  searchPath, shortcutLabel,
} from "@/lib/globalFind";
import { Icon } from "../Icon";
import { useDash } from "../Shell";

type Project = { upload_id: string; filename: string; duration_sec: number; clips: number; thumb_url?: string };

export function GlobalFind({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { fail, reloadMe } = useDash();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [uploadId, setUploadId] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [phase, setPhase] = useState<GlobalFindPhase>({ status: "idle" });
  const label = shortcutLabel();

  useEffect(() => {
    if (!open) return;
    const box = dialog.current;
    if (box && !box.open) box.showModal();
    const fromPage = projectIdFromLocation(window.location.search);
    setUploadId(fromPage || "");
    setQuery("");
    setFilter("");
    setPhase({ status: "idle" });
    api<{ projects: Project[] }>("/v1/projects").then((r) => {
      setProjects(r.projects);
      if (!fromPage && r.projects[0]) setUploadId(r.projects[0].upload_id);
    }).catch(fail);
    queueMicrotask(() => input.current?.focus());
  }, [open, fail]);

  const close = useCallback(() => {
    dialog.current?.close();
    onClose();
  }, [onClose]);

  async function search(ev?: FormEvent) {
    ev?.preventDefault();
    const q = query.trim();
    if (!uploadId) { setPhase({ status: "error", message: "Pick a project to search." }); return; }
    if (!q) { setPhase({ status: "error", message: "Type what you're looking for first." }); return; }
    setPhase({ status: "searching" });
    try {
      const r = await api<{ matches: { start: number; text: string; kind?: string }[] }>(searchPath(uploadId, q));
      setPhase(r.matches.length
        ? { status: "matches", query: q, uploadId, matches: r.matches }
        : { status: "empty", query: q, uploadId });
    } catch (e) {
      if (e instanceof ApiError && e.code === "not_transcribed")
        setPhase({ status: "needs_index", query: q, uploadId });
      else setPhase({ status: "error", message: e instanceof Error ? e.message : "Search failed." });
    }
  }

  async function startFind(makeClips: boolean) {
    const q = ("query" in phase ? phase.query : query).trim();
    const id = ("uploadId" in phase ? phase.uploadId : uploadId);
    if (!id || !q) return;
    setPhase({ status: "starting", query: q, uploadId: id });
    try {
      await api("/v1/find", { body: defaultFindBody(id, q, makeClips) });
      await reloadMe();
      close();
      router.push(findProjectHref(id, q));
    } catch (e) {
      fail(e);
      setPhase({ status: "error", message: e instanceof Error ? e.message : "Could not start Video Finder." });
    }
  }

  const listed = filterProjects(projects || [], filter);
  const chosen = projects?.find((p) => p.upload_id === uploadId);

  if (!open) return null;

  return (
    <dialog ref={dialog} className="picker wide" aria-labelledby="global-find-title"
      onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current) close(); }}>
      <form className="picker-body" onSubmit={search}>
        <div className="picker-head">
          <h2 id="global-find-title">Find moments</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={close}><Icon name="close" /></button>
        </div>
        <p className="m-0 text-[14px] text-soft">Search what was said in a project. Press {label} anytime. Matches are free once a video is indexed; the first index uses credits like Find moments.</p>

        <label className="grid gap-1 text-[13px] text-fg-2">Project
          <select value={uploadId} onChange={(e) => { setUploadId(e.target.value); setPhase({ status: "idle" }); }}
            className="min-h-10 rounded-12 border border-solid border-line bg-card px-3 text-[14px] text-text"
            disabled={!projects?.length}>
            {!projects?.length && <option value="">No projects yet</option>}
            {(projects || []).map((p) => (
              <option key={p.upload_id} value={p.upload_id}>{p.filename}</option>))}
          </select>
        </label>

        {(projects?.length || 0) > 8 && (
          <label className="grid gap-1 text-[13px] text-fg-2">Filter projects
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Type a filename"
              className="min-h-10 rounded-12 border border-solid border-line bg-card px-3 text-[14px] text-text" />
          </label>
        )}

        {filter && listed.length > 0 && listed.length < (projects?.length || 0) && (
          <ul className="picker-list max-h-40 overflow-y-auto" aria-label="Matching projects">
            {listed.slice(0, 8).map((p) => (
              <li key={p.upload_id}>
                <button type="button" onClick={() => { setUploadId(p.upload_id); setFilter(""); setPhase({ status: "idle" }); }}>
                  <span className="picker-thumb" aria-hidden="true">{p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" /> : <Icon name="film" />}</span>
                  <span><strong>{p.filename}</strong><span className="muted">{clock(p.duration_sec)} · {p.clips} clip{p.clips === 1 ? "" : "s"}</span></span>
                </button>
              </li>))}
          </ul>
        )}

        <label className="grid gap-1 text-[13px] text-fg-2">What are you looking for?
          <input ref={input} value={query} maxLength={200} placeholder="police chase, or something that was said"
            onChange={(e) => { setQuery(e.target.value); if (phase.status !== "idle" && phase.status !== "searching") setPhase({ status: "idle" }); }}
            className="min-h-10 rounded-12 border border-solid border-line bg-card px-3 text-[14px] text-text" />
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className="btn small primary" disabled={phase.status === "searching" || phase.status === "starting" || !projects?.length}>
            {phase.status === "searching" ? "Searching…" : "Search"}</button>
          {chosen && <button type="button" className="btn small ghost"
            onClick={() => { close(); router.push(findProjectHref(chosen.upload_id, query)); }}>
            Open Find moments</button>}
        </div>

        {phase.status === "error" && <p className="error" role="alert">{phase.message}</p>}
        {phase.status === "empty" && <p className="muted" role="status">No matches for “{phase.query}”. Try different words, or open Find moments to cut clips with visual search too.</p>}
        {phase.status === "needs_index" && (
          <div className="grid gap-2 rounded-16 border border-solid border-line-soft bg-card p-4" role="status">
            <p className="m-0 text-[14px] text-soft">This video has not been transcribed yet. Run Find once to index it (same credit price as Find moments), then searches are free.</p>
            <button type="button" className="btn small primary" onClick={() => startFind(true)}>Index and find clips</button>
          </div>
        )}
        {phase.status === "starting" && <p className="muted" role="status">Starting Video Finder…</p>}
        {phase.status === "matches" && (
          <div className="grid gap-3">
            <ul className="matches m-0" aria-label="Matches">
              {phase.matches.map((m, i) => (
                <li key={`${m.start}-${i}`}><b>{clock(m.start)}</b> {m.kind === "visual" ? "On screen" : "Said"}: {m.text}</li>))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn small primary" onClick={() => startFind(true)}>Cut clips of matches</button>
              <button type="button" className="btn small ghost"
                onClick={() => { close(); router.push(findProjectHref(phase.uploadId, phase.query)); }}>
                Open in Find moments</button>
            </div>
          </div>
        )}
      </form>
    </dialog>
  );
}
