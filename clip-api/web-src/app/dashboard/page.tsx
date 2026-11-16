"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Icon, IconName, Soon } from "@/components/dash/Icon";
import { ProjectGrid } from "@/components/dash/ProjectCard";
import { useDash } from "@/components/dash/Shell";
import { ACCEPT, UploadProgress, useUpload, useVideoChooser } from "@/components/dash/Upload";
import { api, takePendingFile, videoFileProblem } from "@/lib/api";

// The tool grid. A tile with `tool` opens that tool on a video the user picks; `href` goes to a page.
// Everything else is planned but not built: shown as "Coming soon" and never a link.
type Tile = { icon: IconName; name: string; text: string; tool?: string; href?: string };
const TILES: Tile[] = [
  { icon: "scissors", name: "AI Clipping", text: "Clip Maker finds the best moments in a stream and cuts them into ready-to-post clips.", tool: "clips" },
  { icon: "search", name: "Find Moments", text: "Video Finder: type what was said or shown and jump straight to it.", tool: "find" },
  { icon: "gamepad", name: "Game Templates", text: "Presets tuned to a game. One pick sets the length, captions and editing.", href: "/dashboard/templates/" },
  { icon: "captions", name: "AI Captions", text: "Burn word-by-word captions into any part of a video.", tool: "captions" },
  { icon: "reframe", name: "AI Reframe", text: "Reshape wide footage to vertical, portrait or square.", tool: "reframe" },
  { icon: "sliders", name: "Video Editor", text: "Trim and restyle a clip after it's made." },
  { icon: "bolt", name: "One-Click Highlights", text: "One montage from the best parts of a stream." },
  { icon: "transcript", name: "Video Transcripts", text: "Everything that was said, with timestamps." },
  { icon: "summary", name: "Video Summary", text: "The short version of a long stream." },
  { icon: "image", name: "AI Thumbnail", text: "Cover images made for each clip." },
  { icon: "sparkle", name: "Video Enhancer", text: "Sharper, higher-resolution footage." },
  { icon: "live", name: "Live Clipping", text: "Clips cut while the stream is still live." },
];
const RECENT = 8;

// Home: start a project, pick a tool, or go back to a recent project.
export default function Home() {
  const router = useRouter();
  const { fail } = useDash();
  const [projects, setProjects] = useState<any[] | null>(null);
  const [over, setOver] = useState(false), [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { up, start, cancel } = useUpload((u) => router.push(`/dashboard/project/?id=${u.upload_id}`));
  const chooser = useVideoChooser(projects);

  const load = useCallback(() => api("/v1/projects").then((r) => setProjects(r.projects)).catch(fail), [fail]);
  function take(file: File | null | undefined) {
    if (!file) return;
    const bad = videoFileProblem(file);
    setProblem(bad || "");
    if (!bad) start(file);
  }

  useEffect(() => { load(); const f = takePendingFile(); if (f) start(f); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const anyActive = !!projects?.some((p) => p.active);
  useEffect(() => { if (!anyActive) return; const id = setInterval(load, 4000); return () => clearInterval(id); }, [anyActive, load]);

  return (
    <>
      <h1 className="dash-title">Home</h1>
      <section className={`start ${over ? "over" : ""}`} aria-label="Start a project"
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); if (!up) take(e.dataTransfer.files[0]); }}>
        <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
        {up ? <UploadProgress up={up} onCancel={cancel} /> : <>
          <button type="button" className="start-drop" onClick={() => input.current?.click()}>
            <span className="start-ico"><Icon name="upload" size={28} /></span>
            <strong>Start with a stream recording</strong>
            <span className="muted">Drop the file here, or click to choose one. MP4, MOV, MKV or WebM, up to 8 GB and 6 hours.</span>
          </button>
          {problem && <p className="error" role="alert">{problem}</p>}
          <div className="start-actions">
            <button type="button" className="btn primary" onClick={() => input.current?.click()}><Icon name="upload" />Upload</button>
            <button type="button" className="btn ghost" disabled><Icon name="stack" />Bulk import <Soon /></button>
            <button type="button" className="btn ghost" disabled><Icon name="link" />Paste a link <Soon /></button>
          </div>
        </>}
      </section>

      <section aria-labelledby="tools-title">
        <h2 id="tools-title">Tools</h2>
        <ul className="tiles">
          {TILES.map((t) => {
            const body = <><span className="tile-top"><span className="tile-ico"><Icon name={t.icon} size={22} /></span>{!t.tool && !t.href && <Soon />}</span>
              <strong>{t.name}</strong><span className="muted">{t.text}</span></>;
            return (
              <li key={t.name}>
                {t.href ? <Link className="tile" href={t.href}>{body}</Link>
                  : t.tool ? <button type="button" className="tile" onClick={() => chooser.choose({ title: t.name, query: `tool=${t.tool}` })}>{body}</button>
                  : <div className="tile soon" aria-disabled="true">{body}</div>}
              </li>);
          })}
        </ul>
      </section>

      <section aria-labelledby="recent-title">
        <div className="clips-head">
          <h2 id="recent-title">Recent projects</h2>
          {!!projects && projects.length > RECENT && <Link className="more" href="/dashboard/library/">See all projects</Link>}
        </div>
        {projects === null ? <p className="muted">Loading your projects…</p>
          : !projects.length ? <p className="muted">No projects yet. Upload a stream recording and it shows up here with its clips.</p>
          : <ProjectGrid projects={projects.slice(0, RECENT)} />}
        {!!projects?.length && <p className="muted small">Videos and clips are kept for 7 days.</p>}
      </section>
      {chooser.element}
    </>
  );
}
