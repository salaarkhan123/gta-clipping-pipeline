"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { CLIP_GRID, CLIP_LIST, ClipCard, ClipFilter, ClipSort, ClipToolbar, LayoutToggle, useClipLayout } from "@/components/dash/ClipCard";
import { Icon } from "@/components/dash/Icon";
import { ProjectGrid } from "@/components/dash/ProjectCard";
import { useDash } from "@/components/dash/Shell";
import { SECTION_HEAD } from "@/components/dash/ui";
import { ACCEPT, UploadProgress, useUpload } from "@/components/dash/Upload";
import { Tabs } from "@/components/ui/Pill";
import { api, videoFileProblem } from "@/lib/api";

const PAGE = 24, DAY = 24 * 3600 * 1000;
type View = "all" | "collections" | "projects" | "clips";
const VIEWS: View[] = ["all", "collections", "projects", "clips"];
const GROUP_LABEL = "m-0 px-2 font-sans text-[16px] font-normal leading-[24px] tracking-normal text-fg-2";
const COLLECTION = "flex h-[63px] min-w-0 items-center gap-4 rounded-16 px-5 font-sans no-underline";

// My projects: everything stored on the account. Collections are saved sets of clips (Favorites is the clips you
// bookmarked); projects are the stored videos, one each; Clips is every clip in one list.
// The address keeps the view (`?view=`) and, for Clips, the filter (`&filter=bookmarked` is Favorites).
export default function Library() {
  const { fail } = useDash();
  const [view, setView] = useState<View>("all"), [filter, setFilter] = useState<ClipFilter>("all");
  const [count, setCount] = useState<number | null>(null), [favorites, setFavorites] = useState<number | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search), v = q.get("view") as View;
    if (VIEWS.includes(v)) setView(v);
    if (q.get("filter") === "bookmarked") setFilter("bookmarked");
    api("/v1/clips?limit=1&filter=bookmarked").then((r) => setFavorites(r.total)).catch(fail);
  }, [fail]);
  function show(v: View, f: ClipFilter = "all") {
    setView(v); setFilter(f);
    window.history.replaceState(null, "", v === "all" ? window.location.pathname : `?view=${v}${f === "all" ? "" : `&filter=${f}`}`);
  }
  const n = (x: number | null) => (x === null ? "" : ` (${x})`);
  return (
    <div className="grid w-full grid-cols-[minmax(0,1fr)] pt-[3px]">
      <h1 className="m-0 px-2 font-sans text-[24px] font-semibold leading-[30px] tracking-[-0.01em] text-fg narrow:text-[22px]">My projects</h1>
      <Tabs label="My projects view" panel="library-view" className="mt-[25px]" value={view} onChange={(v) => show(v)}
        options={[{ value: "all", label: "All" }, { value: "collections", label: "Collections (1)" }, { value: "projects", label: `Projects${n(count)}` }, { value: "clips", label: "Clips" }]} />
      <div id="library-view" role="tabpanel" aria-label={view} className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-9">
        {(view === "all" || view === "collections") && <section aria-labelledby="collections-title" className="grid gap-[35px]">
          <h2 id="collections-title" className={GROUP_LABEL}>Collections</h2>
          <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(188px,1fr))] gap-4 p-0 narrow:grid-cols-1">
            <li><span className={`${COLLECTION} relative cursor-default border border-dashed border-line-strong text-fg-3`} aria-disabled="true" title="Your own collections: coming soon">
              <Icon name="plus" size={20} className="flex-none" /><span className="min-w-0 flex-1 truncate text-[14.5px]">New collection</span><ComingSoonBadge short className="absolute -top-[10px] right-3" /></span></li>
            <li><button type="button" onClick={() => show("clips", "bookmarked")} className={`${COLLECTION} w-full cursor-pointer border-0 bg-card text-left text-text transition-colors duration-base hover:bg-control`}>
              <Icon name="heart" size={24} className="flex-none [&_path]:fill-current" />
              <span className="grid min-w-0 gap-[2px]"><b className="truncate text-[15px] font-medium leading-[1.3]">Favorites</b>
                <span className="text-[13px] leading-[1.3] text-fg-2">{favorites === null ? "Bookmarked clips" : `${favorites} clip${favorites === 1 ? "" : "s"}`}</span></span>
            </button></li>
          </ul>
        </section>}
        {(view === "all" || view === "projects") && <AllProjects onCount={setCount} />}
        {view === "clips" && <AllClips key={filter} start={filter} />}
      </div>
    </div>
  );
}

// The dashed tile at the start of the projects grid: pick a file, watch it upload, land on its job-setup screen.
function UploadTile() {
  const router = useRouter(), { me } = useDash();
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState("");
  const { up, start, cancel } = useUpload((u) => router.push(`/dashboard/project/?id=${u.upload_id}&tool=clips`));
  function take(f: File | undefined) {
    if (!f) return;
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start(f);
  }
  return (
    <li className="grid h-[144px] min-w-0 self-start">
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      {up ? <div className="grid content-center rounded-16 border border-dashed border-line-strong p-3 text-[13px]"><UploadProgress up={up} onCancel={cancel} /></div>
        : <button type="button" disabled={!me.email_verified} onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); take(e.dataTransfer.files[0]); }}
            className="grid cursor-pointer place-content-center justify-items-center gap-2 rounded-16 border border-dashed border-line-strong bg-white/[.03] px-3 font-sans text-[14.5px] text-fg-2 transition-colors duration-base hover:bg-card hover:text-text disabled:cursor-default disabled:opacity-45">
            <Icon name="plus" size={22} />Upload new video
            {problem && <span role="alert" className="text-[12px] text-danger">{problem}</span>}
          </button>}
    </li>
  );
}

// Every stored video, newest first. `onCount` gets how many are loaded (the tab's number).
function AllProjects({ onCount }: { onCount: (n: number) => void }) {
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
  useEffect(() => { if (projects && !more) onCount(projects.length); }, [projects, more, onCount]);
  const anyActive = !!projects?.slice(0, PAGE).some((p) => p.active);
  useEffect(() => { if (!anyActive) return; const id = setInterval(() => load(0, true), 4000); return () => clearInterval(id); }, [anyActive, load]);

  // How long a video is kept, read from the first project's own dates rather than assumed.
  const first = projects?.[0];
  const days = first?.expires_at ? Math.round((Date.parse(first.expires_at) - Date.parse(first.created_at)) / DAY) : 0;
  return (
    <section aria-labelledby="projects-title" className="grid gap-[37px]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="projects-title" className={GROUP_LABEL}>Projects</h2>
        {days > 0 && <p className="m-0 font-sans text-[14.5px] text-fg-2" title="A video and its clips are deleted when it expires. Download the clips you want to keep.">Kept for {days} days</p>}
      </div>
      {projects === null ? <p className="muted">Loading your projects…</p>
        : <ProjectGrid projects={projects} lead={<UploadTile />}
            onDeleted={(id) => setProjects((list) => (list || []).filter((p) => p.upload_id !== id))} />}
      {more && projects && <div><button className="btn ghost" disabled={busy} onClick={() => load(projects.length)}>{busy ? "Loading…" : "Show more"}</button></div>}
    </section>
  );
}

// Every clip on the account, newest first.
function AllClips({ start }: { start: ClipFilter }) {
  const { fail } = useDash();
  const [clips, setClips] = useState<any[] | null>(null), [total, setTotal] = useState(0), [busy, setBusy] = useState(false);
  const [sort, setSort] = useState<ClipSort>("newest"), [filter, setFilter] = useState<ClipFilter>(start);
  const [layout, setLayout] = useClipLayout();

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
    <div className="stack">
      <div className={SECTION_HEAD}>
        <p className="muted small">{clips?.length ? `${total} clip${total === 1 ? "" : "s"}. Clips are kept for 7 days.` : ""}</p>
        <div className="flex flex-wrap items-center gap-[10px]">
          <ClipToolbar sort={sort} filter={filter} sorts={["newest", "score", "time"]} onSort={setSort} onFilter={setFilter} />
          <LayoutToggle value={layout} onChange={setLayout} />
        </div>
      </div>
      {clips === null ? <p className="muted">Loading your clips…</p>
        : !clips.length ? <p className="empty-note">{filter === "all" ? "No clips yet. Open a project and make some." : "No clips match this filter."}</p>
        : <>
            <div className={layout === "list" ? CLIP_LIST : CLIP_GRID}>
              {clips.map((c) => <ClipCard key={c.id} clip={c} layout={layout} project={{ id: c.upload_id, name: c.filename }}
                onChange={(n) => setClips((list) => list!.map((x) => (x.id === n.id ? n : x)))} />)}
            </div>
            {clips.length < total && <div><button className="btn ghost" disabled={busy} onClick={() => more(clips.length)}>{busy ? "Loading…" : "Show more"}</button></div>}
          </>}
    </div>
  );
}
