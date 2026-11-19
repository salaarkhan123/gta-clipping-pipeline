"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
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
const HERO = "grid w-[min(100%,760px)] justify-items-center pt-6 text-center narrow:pt-2";
const TILE = "relative grid w-full cursor-pointer content-start justify-items-center gap-[10px] rounded-16 border-0 bg-transparent px-[2px] pb-2 pt-[6px] text-center text-text [font:inherit]";
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
  const open = (id: string, query = "") => router.push(`/dashboard/project/?id=${id}${query}`);

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
    <div className="mx-auto grid w-full max-w-home grid-cols-[minmax(0,1fr)] justify-items-center gap-12 pt-[18px] narrow:gap-9 narrow:pt-1">
      <h1 className="sr-only">Home</h1>
      <section className="grid w-full justify-items-center gap-[22px]" aria-label="Start a project">
        <div className={HERO}>
          <p className="font-display text-[44px] font-semibold leading-[1.08] tracking-[-0.03em] narrow:text-[30px]">Drop the stream. Keep the clutch.</p>
          <p className="mt-3 text-[17px] text-muted narrow:text-[15px]">One long VOD in, ranked clips out, with your facecam, captions and an AI rating on each.</p>
        </div>
        <SourceBar onUploaded={open} pending={pending} />
      </section>

      <section aria-labelledby="tools-title" className="w-full">
        <h2 id="tools-title" className="sr-only">Tools</h2>
        <ul className="mx-auto grid max-w-[760px] list-none grid-cols-6 gap-x-2 gap-y-[18px] narrow:grid-cols-4 narrow:gap-x-1 narrow:gap-y-4">
          {TOOLS.map((t) => {
            const built = isBuilt(t, on);
            const body = <>
              <span className={`grid h-14 w-14 place-items-center rounded-16 border border-solid transition-[border-color,color,background,transform] duration-200 ease-[ease] narrow:h-12 narrow:w-12 ${built
                ? "border-line-soft bg-card text-text group-hover:-translate-y-[2px] group-hover:border-[rgba(255,255,255,.22)] group-hover:bg-card-2"
                : "border-dashed border-line bg-transparent text-dim"}`}><Icon name={t.icon} size={22} /></span>
              <span className={`max-w-[11ch] font-body text-[13px] font-medium leading-[1.25] narrow:text-[12px] ${built ? "" : "text-muted"}`}>{t.name}</span>
              {built ? t.badge === "new" && <small className={`${BADGE} border-[rgba(184,255,60,.35)] bg-[#1c2a0e] text-lime`}>New</small>
                : <ComingSoonBadge short className="absolute left-[calc(50%+6px)] top-[-4px] bg-bg" />}
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
