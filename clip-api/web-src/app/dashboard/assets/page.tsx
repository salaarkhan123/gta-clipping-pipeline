"use client";
// Asset library: what an account keeps for its clips. Wired today: the built-in swear list (switched on per brand
// kit) and the videos you uploaded (GET /v1/projects). Planned, marked Coming soon and saving nothing: storage
// limits, your own censor list, brand vocabulary, fonts, images and audio.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon, IconName } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { Tabs } from "@/components/dash/Tabs";
import { PAGE_TITLE } from "@/components/dash/ui";
import { api, clock } from "@/lib/api";

type Video = { upload_id: string; filename: string; size_bytes: number; duration_sec: number; width: number | null; height: number | null;
  created_at: string; expires_at: string; thumb_url: string | null; clips: number };
type Kind = "all" | "images" | "videos" | "audio";
const PAGE = 24;

const H2 = "m-0 flex flex-wrap items-center gap-2 text-[18px] font-semibold";
const bytes = (n: number) => n >= 1e9 ? `${(n / 1e9).toFixed(2)} GB` : n >= 1e6 ? `${Math.round(n / 1e6)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
const date = (s: string) => { const d = new Date(s); return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }); };

// A dashed "add" box for something not built yet: never clickable.
function SoonAdd({ icon = "plus", text, className = "" }: { icon?: IconName; text: string; className?: string }) {
  return (
    <span aria-disabled="true" className={`inline-flex min-h-[48px] cursor-default items-center gap-2 rounded-12 border border-dashed border-line px-4 text-[14.5px] text-fg-3 ${className}`}>
      <Icon name={icon} size={18} />{text}<ComingSoonBadge short className="ml-1" /></span>
  );
}

function VideoCard({ v }: { v: Video }) {
  return (
    <li className="grid content-start gap-2">
      <Link href={`/dashboard/project/?id=${encodeURIComponent(v.upload_id)}`} className="group grid gap-2 no-underline">
        <span className="relative grid aspect-video place-items-center overflow-hidden rounded-16 border border-solid border-line-soft bg-[linear-gradient(160deg,#1d2230,#0c0e13)]">
          {v.thumb_url ? <img src={v.thumb_url} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
            : <Icon name="film" size={28} className="text-fg-3" />}
          <span className="absolute bottom-2 right-2 rounded-[6px] bg-[rgba(0,0,0,.75)] px-[6px] py-[2px] font-mono text-[11.5px] text-text">{clock(v.duration_sec)}</span>
        </span>
        <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[14px] font-medium text-text" title={v.filename}>{v.filename}</span>
      </Link>
      <span className="text-[12.5px] text-muted">{[v.height ? `${v.height}p` : "", bytes(v.size_bytes), v.clips ? `${v.clips} clips` : "", date(v.created_at) && `Added ${date(v.created_at)}`].filter(Boolean).join(" · ")}</span>
    </li>
  );
}

function Videos() {
  const { fail } = useDash();
  const [list, setList] = useState<Video[] | null>(null), [more, setMore] = useState(false), [busy, setBusy] = useState(false);
  const load = useCallback(async (from: number) => {
    setBusy(true);
    try {
      const r = await api<{ projects: Video[] }>(`/v1/projects?limit=${PAGE}&offset=${from}`);
      setList((old) => [...(from ? old || [] : []), ...r.projects]);
      setMore(r.projects.length === PAGE);
    } catch (e) { fail(e); setList((old) => old || []); } finally { setBusy(false); }
  }, [fail]);
  useEffect(() => { load(0); }, [load]);
  if (!list) return <p className="muted">Loading…</p>;
  if (!list.length) return (
    <div className="grid justify-items-center gap-3 rounded-20 border border-dashed border-line p-10 text-center">
      <Icon name="film" size={28} className="text-fg-3" />
      <p className="m-0 text-muted">Videos you upload or import show up here.</p>
      <Link href="/dashboard/" className="btn small primary">Upload a video</Link>
    </div>
  );
  return (
    <div className="grid gap-4">
      <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4 p-0 narrow:grid-cols-2 narrow:gap-3">{list.map((v) => <VideoCard key={v.upload_id} v={v} />)}</ul>
      <p className="m-0 text-[12.5px] text-fg-3">Uploaded videos are kept until their expiry date, then deleted with their clips.</p>
      {more && <button type="button" className="btn small ghost justify-self-center" disabled={busy} onClick={() => load(list.length)}>{busy ? "Loading…" : "Load more"}</button>}
    </div>
  );
}

function SoonMedia({ icon, what }: { icon: IconName; what: string }) {
  return (
    <div className="grid justify-items-center gap-3 rounded-20 border border-dashed border-line p-10 text-center">
      <Icon name={icon} size={28} className="text-fg-3" />
      <p className="m-0 flex flex-wrap items-center justify-center gap-2 text-muted">{what} for your clips<ComingSoonBadge /></p>
    </div>
  );
}

export default function Assets() {
  const [kind, setKind] = useState<Kind>("all");
  return (
    <div className="grid gap-9">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <h1 className={PAGE_TITLE}>Asset library</h1>
        <span className="inline-flex items-center gap-2 text-[14px] text-muted" title="How much storage you use and your plan's limit">
          <Icon name="folder" size={16} />Storage used<ComingSoonBadge short /></span>
      </div>

      <section className="grid gap-3" aria-labelledby="censor-title">
        <h2 id="censor-title" className={H2}>Censored words</h2>
        <p className="m-0 max-w-[620px] text-[14px] leading-[1.5] text-muted">Swears are masked in burned captions and in SRT, VTT and TXT downloads (f***ing), keeping the first letter.
          Turn it on with <b className="font-medium text-text">Censor swears</b> in a <Link href="/dashboard/brand-kit/">brand kit</Link> or when you start a job.</p>
        <div className="flex flex-wrap gap-3">
          <div className="inline-flex min-h-[48px] items-center gap-2 rounded-12 border border-solid border-line-soft bg-card px-4 text-[14.5px] text-text">
            <Icon name="shield" size={18} className="text-muted" />Swear words
            <span className="rounded-[6px] bg-raised px-[6px] py-[2px] text-[11.5px] text-label">Default</span></div>
          <SoonAdd text="Add my list" />
        </div>
      </section>

      <section className="grid gap-3" aria-labelledby="vocab-title">
        <h2 id="vocab-title" className={H2}>Brand vocabulary</h2>
        <p className="m-0 max-w-[620px] text-[14px] leading-[1.5] text-muted">Streamer names, crews, places and items, so captions spell them the way your community does.</p>
        <div><SoonAdd text="Add proper nouns" /></div>
      </section>

      <section className="grid gap-3" aria-labelledby="fonts-title">
        <h2 id="fonts-title" className={H2}>Fonts</h2>
        <p className="m-0 max-w-[620px] text-[14px] leading-[1.5] text-muted">Two font files of your own for captions and hooks. Until then, captions use our built-in fonts.</p>
        <div className="grid grid-cols-[repeat(2,minmax(0,220px))] gap-3 narrow:grid-cols-2">
          {[1, 2].map((n) => (
            <div key={n} aria-disabled="true" className="grid aspect-[16/11] cursor-default place-items-center content-center gap-2 rounded-16 border border-dashed border-line text-center text-fg-3">
              <Icon name="upload" size={22} /><span className="text-[13.5px]">Font slot {n}</span><ComingSoonBadge short />
            </div>))}
        </div>
      </section>

      <section className="grid gap-4" aria-labelledby="media-title">
        <h2 id="media-title" className={H2}>Media</h2>
        <div className="justify-self-start"><Tabs seg label="Media type" panel="media" value={kind} onChange={setKind} tabs={[["all", "All"], ["images", "Images"], ["videos", "Videos"], ["audio", "Audio"]]} /></div>
        <div id="media" role="tabpanel">
          {kind === "images" ? <SoonMedia icon="image" what="Logos, overlays and stickers" />
            : kind === "audio" ? <SoonMedia icon="music" what="Music and sound effects" />
            : <Videos />}
        </div>
      </section>
    </div>
  );
}
