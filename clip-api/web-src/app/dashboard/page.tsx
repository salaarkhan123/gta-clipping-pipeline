"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/dash/Icon";
import { ProjectGrid } from "@/components/dash/ProjectCard";
import { useDash } from "@/components/dash/Shell";
import { SourceBar } from "@/components/dash/SourceBar";
import { useVideoChooser } from "@/components/dash/Upload";
import { api, takePendingFile } from "@/lib/api";
import { useLanguageSwitches } from "@/lib/languages";
import { isBuilt, ToolEntry, TOOLS } from "@/lib/tools";

const RECENT = 10;
// One literal per class: Tailwind finds classes by reading the source, so a class may not be split across strings.
const HERO = "w-[min(100%,560px)] rounded-16 border border-solid border-[rgba(184,255,60,.16)] px-6 py-[26px] text-center narrow:px-4 narrow:py-5 [background:radial-gradient(ellipse_at_15%_0%,rgba(184,255,60,.22),transparent_60%),radial-gradient(ellipse_at_95%_110%,rgba(60,240,255,.16),transparent_55%),repeating-linear-gradient(115deg,transparent_0_22px,rgba(255,255,255,.018)_22px_44px),#0b0f0c]";
const TILE = "relative grid w-full cursor-pointer content-start justify-items-center gap-2 rounded-12 border-0 bg-transparent px-[2px] py-[6px] text-center text-text [font:inherit]";
const BADGE = "absolute left-[calc(50%+10px)] top-0 rounded-full border border-solid px-[7px] py-px font-body text-[10px] font-bold leading-[1.5]";

// Home: one input for a link or a file, the tools, and the latest projects.
// useSearchParams needs a Suspense boundary in a static export.
export default function HomePage() { return <Suspense><Home /></Suspense>; }

function Home() {
  const router = useRouter(), query = useSearchParams();
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
  const on = useLanguageSwitches();
  const choose = (t: ToolEntry) => chooser.choose(t.page ? { title: t.name, query: "", path: t.page } : { title: t.name, query: `tool=${t.tool}` });
  useEffect(() => {
    if (projects === null) return;
    const want = TOOLS.find((t) => (t.tool || t.page) && t.id === query.get("tool"));
    if (!want) return;
    window.history.replaceState(null, "", window.location.pathname);
    choose(want);
  }, [projects === null, query]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mx-auto grid w-full max-w-home justify-items-center gap-11 pt-[18px] narrow:gap-8 narrow:pt-1">
      <h1 className="sr-only">Home</h1>
      <section className="grid w-full justify-items-center gap-[22px]" aria-label="Start a project">
        <div className={HERO}>
          <p className="font-display text-[24px] font-bold leading-[1.2] narrow:text-[20px]">Drop the stream. <span className="text-lime">Keep the clutch.</span></p>
          <p className="mt-[6px] text-[14px] text-soft">Ranked clips with your facecam and captions, ready to post.</p>
        </div>
        <SourceBar onUploaded={open} pending={pending} />
      </section>

      <section aria-labelledby="tools-title" className="w-full">
        <h2 id="tools-title" className="sr-only">Tools</h2>
        <ul className="mx-auto grid max-w-[720px] list-none grid-cols-6 gap-x-2 gap-y-[18px] narrow:grid-cols-4 narrow:gap-x-1 narrow:gap-y-4">
          {TOOLS.map((t) => {
            const built = isBuilt(t, on);
            const body = <>
              <span className={`grid h-[52px] w-[52px] place-items-center rounded-full border border-solid transition-[border-color,color,background,transform] duration-200 ease-[ease] narrow:h-12 narrow:w-12 ${built
                ? "border-line bg-card text-text group-hover:-translate-y-[2px] group-hover:border-lime group-hover:bg-lime-wash group-hover:text-lime"
                : "border-dashed border-line bg-transparent text-dim"}`}><Icon name={t.icon} size={22} /></span>
              <span className={`max-w-[11ch] font-body text-[13px] font-medium leading-[1.25] narrow:text-[12px] ${built ? "" : "text-muted"}`}>{t.name}</span>
              {built ? t.badge === "new" && <small className={`${BADGE} border-[rgba(184,255,60,.35)] bg-[#1c2a0e] text-lime`}>New</small>
                : <small className={`${BADGE} border-line bg-card-2 text-muted`}>Soon</small>}
            </>;
            return (
              <li key={t.id} className="grid">
                {t.href ? <Link className={`group ${TILE}`} href={t.href} title={t.text}>{body}</Link>
                  : built ? <button type="button" className={`group ${TILE}`} title={t.text} onClick={() => choose(t)}>{body}</button>
                  : <span className={`${TILE} cursor-default`} aria-disabled="true" title={`${t.text} Coming soon.`}>{body}<span className="sr-only">, coming soon</span></span>}
              </li>);
          })}
        </ul>
      </section>

      <section aria-labelledby="recent-title" className="w-full">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 id="recent-title" className="m-0 text-[16px]">Recent projects</h2>
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
