"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { CLIP_GRID, ClipCard, ClipFilter, ClipSort, ClipToolbar } from "@/components/dash/ClipCard";
import { ProjectGrid } from "@/components/dash/ProjectCard";
import { useDash } from "@/components/dash/Shell";
import { BackTitle, PAGE_HEAD, SECTION_HEAD } from "@/components/dash/ui";
import { Tabs } from "@/components/dash/Tabs";
import { api } from "@/lib/api";

const PAGE = 24;
type View = "projects" | "clips";

// Library: everything stored on the account, as projects (one per video) or as one list of clips.
export default function Library() {
  const [view, setView] = useState<View>("projects");
  useEffect(() => { if (new URLSearchParams(window.location.search).get("view") === "clips") setView("clips"); }, []);
  function show(v: View) {
    setView(v);
    window.history.replaceState(null, "", v === "clips" ? "?view=clips" : window.location.pathname);
  }
  return (
    <div className="wide stack">
      <div className={PAGE_HEAD}>
        <BackTitle title="Library" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Library" }]} />
        <Tabs seg label="Library view" panel="library-view" value={view} onChange={show} tabs={[["projects", "Projects"], ["clips", "Clips"]]} />
      </div>
      <div id="library-view" role="tabpanel" aria-label={view === "projects" ? "Projects" : "Clips"} className="stack">
        {view === "projects" ? <AllProjects /> : <AllClips />}
      </div>
    </div>
  );
}

// Every stored video, newest first.
function AllProjects() {
  const { fail } = useDash();
  const [projects, setProjects] = useState<any[] | null>(null), [more, setMore] = useState(false), [busy, setBusy] = useState(false);

  // `quiet` refreshes the first page while something is still being worked on.
  const load = useCallback(async (offset: number, quiet = false) => {
    if (!quiet) setBusy(true);
    try {
      const r = await api(`/v1/projects?limit=${PAGE}&offset=${offset}`);
      if (quiet) setProjects((list) => (list && list.length > PAGE ? [...r.projects, ...list.slice(PAGE)] : r.projects));
      else { setMore(r.projects.length === PAGE); setProjects((list) => (offset ? [...(list || []), ...r.projects] : r.projects)); }
    } catch (e) { fail(e); } finally { if (!quiet) setBusy(false); }
  }, [fail]);
  useEffect(() => { load(0); }, [load]);
  const anyActive = !!projects?.slice(0, PAGE).some((p) => p.active);
  useEffect(() => { if (!anyActive) return; const id = setInterval(() => load(0, true), 4000); return () => clearInterval(id); }, [anyActive, load]);

  if (projects === null) return <p className="muted">Loading your projects…</p>;
  if (!projects.length) return <p className="empty-note">No projects yet. <Link href="/dashboard/">Paste a link or upload a recording</Link> to start one.</p>;
  return (
    <>
      <p className="muted small">Each video is a project. Videos and their clips are kept for 7 days.</p>
      <ProjectGrid projects={projects}
        onDeleted={(id) => setProjects((list) => (list || []).filter((p) => p.upload_id !== id))} />
      {more && <div><button className="btn ghost" disabled={busy} onClick={() => load(projects.length)}>{busy ? "Loading…" : "Show more"}</button></div>}
    </>
  );
}

// Every clip on the account, newest first.
function AllClips() {
  const { fail } = useDash();
  const [clips, setClips] = useState<any[] | null>(null), [total, setTotal] = useState(0), [busy, setBusy] = useState(false);
  const [sort, setSort] = useState<ClipSort>("newest"), [filter, setFilter] = useState<ClipFilter>("all");

  const more = useCallback(async (offset: number) => {
    setBusy(true);
    try {
      const r = await api(`/v1/clips?limit=${PAGE}&offset=${offset}&sort=${sort}&filter=${filter}`);
      setTotal(r.total);
      setClips((list) => (offset ? [...(list || []), ...r.clips] : r.clips));
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [fail, sort, filter]);
  useEffect(() => { more(0); }, [more]);

  return (
    <>
      <div className={SECTION_HEAD}>
        <p className="muted small">{clips?.length ? `${total} clip${total === 1 ? "" : "s"}. Clips are kept for 7 days.` : ""}</p>
        <ClipToolbar sort={sort} filter={filter} sorts={["newest", "score", "time"]} onSort={setSort} onFilter={setFilter} />
      </div>
      {clips === null ? <p className="muted">Loading your clips…</p>
        : !clips.length ? <p className="empty-note">{filter === "all" ? "No clips yet. Open a project and make some." : "No clips match this filter."}</p>
        : <>
            <div className={CLIP_GRID}>
              {clips.map((c) => <ClipCard key={c.id} clip={c} project={{ id: c.upload_id, name: c.filename }}
                onChange={(n) => setClips((list) => list!.map((x) => (x.id === n.id ? n : x)))} />)}
            </div>
            {clips.length < total && <div><button className="btn ghost" disabled={busy} onClick={() => more(clips.length)}>{busy ? "Loading…" : "Show more"}</button></div>}
          </>}
    </>
  );
}
