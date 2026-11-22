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

const RECENT = 8;
// A tool as a pill: outlined, grey until hovered. One literal per class: Tailwind finds classes by reading the source.
const CHIP = "inline-flex h-[37px] items-center gap-2 whitespace-nowrap rounded-pill border border-solid border-line bg-transparent px-[14px] font-sans text-[14.5px] font-normal leading-none no-underline transition-colors duration-base";
const CHIP_ON = "cursor-pointer text-fg-2 hover:border-line-strong hover:text-text";

// Home: one input for a link or a file, the tools that work today, and the latest projects.
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
    <div className="grid w-full grid-cols-[minmax(0,1fr)] pt-[38px] narrow:pt-2">
      <h1 className="sr-only">Home</h1>
      <section className="grid w-full justify-items-center mid:justify-items-start narrow:justify-items-center" aria-label="Start a project">
        <SourceBar onUploaded={open} pending={pending} />
      </section>

      <section aria-labelledby="tools-title" className="mt-4 w-full max-w-[590px] justify-self-center mid:justify-self-start narrow:justify-self-center">
        <h2 id="tools-title" className="sr-only">Tools</h2>
        <ul className="m-0 flex list-none flex-wrap justify-center gap-x-2 gap-y-[9px] p-0">
          {TOOLS.map((t) => (
            <li key={t.id}>
              {!isBuilt(t, on) ? <span className={`${CHIP} cursor-default text-fg-3`} aria-disabled="true" title={`${t.text} Coming soon.`}><Icon name={t.icon} size={17} />{t.name}<ComingSoonBadge short /></span>
                : t.href ? <Link className={`${CHIP} ${CHIP_ON}`} href={t.href} title={t.text}><Icon name={t.icon} size={17} />{t.name}</Link>
                : <button type="button" className={`${CHIP} ${CHIP_ON}`} title={t.text} onClick={() => choose(t)}><Icon name={t.icon} size={17} />{t.name}</button>}
            </li>))}
        </ul>
      </section>

      <section aria-labelledby="recent-title" className="mt-[72px] w-full narrow:mt-12">
        <div className="mb-5 flex items-center gap-5">
          <h2 id="recent-title" className="m-0 font-sans text-[16px] font-normal leading-[24px] tracking-normal text-fg-2">Recent projects</h2>
          {!!projects?.length && <Link className="inline-flex items-center gap-1 font-sans text-[15px] font-medium text-text no-underline hover:underline" href="/dashboard/library/">View all <Icon name="chevron" size={16} className="-rotate-90" /></Link>}
        </div>
        {projects === null ? <p className="muted">Loading your projects…</p>
          : !projects.length ? <p className="empty-note">No projects yet. Paste a link or upload a recording above; it shows up here with its clips.</p>
          : <ProjectGrid projects={projects.slice(0, RECENT)} size="home"
              onDeleted={(id) => setProjects((list) => (list || []).filter((p) => p.upload_id !== id))} />}
      </section>
      {chooser.element}
    </div>
  );
}
