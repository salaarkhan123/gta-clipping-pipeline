"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { ProjectGrid } from "@/components/dash/ProjectCard";
import { useDash } from "@/components/dash/Shell";
import { SourceBar } from "@/components/dash/SourceBar";
import { useVideoChooser } from "@/components/dash/Upload";
import { api, takePendingFile } from "@/lib/api";
import { isBuilt, ToolEntry, TOOLS } from "@/lib/tools";

const RECENT = 10;

// Home: one input for a link or a file, the tools, and the latest projects.
export default function Home() {
  const router = useRouter();
  const { fail } = useDash();
  const [projects, setProjects] = useState<any[] | null>(null);
  const [pending, setPending] = useState<File | null>(null);
  const chooser = useVideoChooser(projects);
  const open = (id: string) => router.push(`/dashboard/project/?id=${id}`);

  const load = useCallback(() => api("/v1/projects").then((r) => setProjects(r.projects)).catch(fail), [fail]);
  useEffect(() => { load(); setPending(takePendingFile()); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const anyActive = !!projects?.some((p) => p.active);
  useEffect(() => { if (!anyActive) return; const id = setInterval(load, 4000); return () => clearInterval(id); }, [anyActive, load]);

  // The top bar's Tools menu lands here with ?tool=: ask which video, once the projects are known.
  const choose = (t: ToolEntry) => chooser.choose({ title: t.name, query: `tool=${t.tool}` });
  useEffect(() => {
    if (projects === null) return;
    const want = TOOLS.find((t) => t.tool && t.tool === new URLSearchParams(window.location.search).get("tool"));
    if (!want) return;
    window.history.replaceState(null, "", window.location.pathname);
    choose(want);
  }, [projects === null]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="home">
      <h1 className="sr-only">Home</h1>
      <section className="home-hero" aria-label="Start a project">
        <div className="hero-card">
          <p className="hero-title">Drop the stream. <span>Keep the clutch.</span></p>
          <p className="hero-sub">Ranked clips with your facecam and captions, ready to post.</p>
        </div>
        <SourceBar onUploaded={open} pending={pending} />
      </section>

      <section aria-labelledby="tools-title" className="home-tools">
        <h2 id="tools-title" className="sr-only">Tools</h2>
        <ul className="tool-grid">
          {TOOLS.map((t) => {
            const body = <>
              <span className="tool-ico"><Icon name={t.icon} size={22} /></span>
              <span className="tool-name">{t.name}</span>
              {isBuilt(t) ? t.badge === "new" && <small className="tool-badge">New</small> : <small className="tool-badge soon">Soon</small>}
            </>;
            return (
              <li key={t.id}>
                {t.href ? <Link className="tool-tile" href={t.href} title={t.text}>{body}</Link>
                  : t.tool ? <button type="button" className="tool-tile" title={t.text} onClick={() => choose(t)}>{body}</button>
                  : <span className="tool-tile soon" aria-disabled="true" title={`${t.text} Coming soon.`}>{body}<span className="sr-only">, coming soon</span></span>}
              </li>);
          })}
        </ul>
      </section>

      <section aria-labelledby="recent-title" className="home-recent">
        <div className="section-head">
          <h2 id="recent-title">Recent projects</h2>
          {!!projects?.length && <Link className="more" href="/dashboard/library/">See all <Icon name="arrow" size={14} /></Link>}
        </div>
        {projects === null ? <p className="muted">Loading your projects…</p>
          : !projects.length ? <p className="empty-note">No projects yet. Paste a link or upload a recording above; it shows up here with its clips.</p>
          : <ProjectGrid projects={projects.slice(0, RECENT)} row />}
      </section>
      {chooser.element}
    </div>
  );
}
