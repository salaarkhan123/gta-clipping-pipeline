"use client";
// Asset library: what an account keeps for its clips. Wired today: the built-in swear list (switched on per brand
// kit), your own fonts (GET / POST / DELETE /v1/fonts) and the videos you uploaded (GET /v1/projects, POST
// /v1/uploads). Planned, marked Soon and saving nothing: your own censor list, brand vocabulary, images and audio.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon, IconName } from "@/components/dash/Icon";
import { ProjectGrid } from "@/components/dash/ProjectCard";
import { useDash } from "@/components/dash/Shell";
import { ACCEPT, UploadProgress, useUpload } from "@/components/dash/Upload";
import { Badge } from "@/components/ui/Badge";
import { Info } from "@/components/ui/Info";
import { Pills } from "@/components/ui/Pill";
import { API, api, ApiError, getToken, videoFileProblem } from "@/lib/api";

type Video = { upload_id: string; size_bytes: number };
type Font = { id: string; family: string; filename: string; bytes: number };
type Fonts = { fonts: Font[]; max: number; max_bytes: number; licence: string };
type Kind = "all" | "images" | "videos" | "audio";
const PAGE = 24;

const H2 = "m-0 flex flex-wrap items-center gap-2 font-sans text-[15px] font-semibold leading-[24px] tracking-normal text-text";
const BUTTON = "inline-flex h-[37px] min-w-[211px] items-center gap-2 rounded-8 bg-panel px-3 font-sans text-[15px] narrow:min-w-0";
const DROP = "grid h-[118px] w-[211px] max-w-full cursor-pointer place-content-center justify-items-center gap-2 rounded-12 border border-dashed border-line-strong bg-transparent px-3 text-center font-sans text-[14.5px] text-fg-2 transition-colors duration-base hover:bg-card hover:text-text disabled:cursor-default disabled:opacity-45";
const CAPTION = "m-0 font-sans text-[14px] font-medium leading-[20px] text-text";
const bytes = (n: number) => n >= 1e9 ? `${(n / 1e9).toFixed(2)} GB` : n >= 1e6 ? `${Math.round(n / 1e6)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;

// A compact button for something not built yet: never clickable.
function SoonAdd({ icon = "plus", text }: { icon?: IconName; text: string }) {
  return <span aria-disabled="true" className={`${BUTTON} cursor-default text-fg-3`}><Icon name={icon} size={17} />{text}<ComingSoonBadge short className="ml-auto" /></span>;
}

// Your own caption fonts. The API wants the licence confirmed with every upload, so a picked file waits for the tick.
function FontSection() {
  const { fail } = useDash();
  const [data, setData] = useState<Fonts | null>(null), [picked, setPicked] = useState<File | null>(null);
  const [agreed, setAgreed] = useState(false), [busy, setBusy] = useState(false), [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => api<Fonts>("/v1/fonts").then(setData).catch(fail), [fail]);
  useEffect(() => { load(); }, [load]);

  function pick(f: File | undefined) {
    if (!f || !data) return;
    setProblem(!/\.(ttf|otf)$/i.test(f.name) ? "Choose a .ttf or .otf font file." : f.size > data.max_bytes ? `A font file may be at most ${bytes(data.max_bytes)}.` : "");
    setPicked(f); setAgreed(false);
  }
  async function upload() {
    if (!picked || !agreed) return;
    setBusy(true); setProblem("");
    try {
      const res = await fetch(`${API}/v1/fonts?filename=${encodeURIComponent(picked.name)}&licence_confirmed=true`,
        { method: "POST", headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/octet-stream" }, body: picked });
      const out = await res.json().catch(() => null);
      if (!res.ok) throw new ApiError(res.status, out?.error?.code || "error", out?.error?.message || "The font could not be uploaded.");
      setPicked(null); await load();
    } catch (e) { setProblem(e instanceof Error ? e.message : "The font could not be uploaded."); } finally { setBusy(false); }
  }
  async function remove(f: Font) {
    if (!window.confirm(`Delete the font "${f.family}"? Kits and clips that use it fall back to the built-in font.`)) return;
    try { await api(`/v1/fonts/${encodeURIComponent(f.id)}`, { method: "DELETE" }); await load(); } catch (e) { fail(e); }
  }
  const full = !!data && data.fonts.length >= data.max;

  return (
    <section className="grid gap-[18px]" aria-labelledby="fonts-title">
      <h2 id="fonts-title" className={H2}>Fonts{data ? ` (${data.fonts.length}/${data.max})` : ""}
        <Info label="About fonts">Your own TTF or OTF files for captions, up to {data ? bytes(data.max_bytes) : "5 MB"} each. Until you add one, captions use our built-in fonts.</Info></h2>
      {!!data?.fonts.length && <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
        {data.fonts.map((f) => <li key={f.id} className={`${BUTTON} text-text`} title={`${f.filename} · ${bytes(f.bytes)}`}>
          <Icon name="font" size={17} className="text-fg-2" /><span className="min-w-0 flex-1 truncate">{f.family}</span>
          <button type="button" aria-label={`Delete the font ${f.family}`} title="Delete" onClick={() => remove(f)}
            className="grid h-7 w-7 cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-fg-2 hover:bg-control hover:text-danger"><Icon name="trash" size={15} /></button></li>)}
      </ul>}
      <div className="grid gap-[14px]">
        <input ref={input} type="file" accept=".ttf,.otf,font/ttf,font/otf" hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
        <button type="button" className={DROP} disabled={!data || full || busy} onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}>
          <Icon name="upload" size={22} />{full ? "Font limit reached" : "Add or drag file here"}</button>
        <p className={CAPTION}>Upload font</p>
      </div>
      {picked && <div className="grid max-w-[560px] gap-3 rounded-12 bg-card p-4">
        <p className="m-0 text-[14px] text-text">{picked.name} <span className="text-fg-2">· {bytes(picked.size)}</span></p>
        {!problem && data && <label className="m-0 flex cursor-pointer items-start gap-3 text-[13.5px] font-normal leading-[1.45] text-fg-2">
          <input type="checkbox" className="mt-[3px]" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />{data.licence}</label>}
        {problem && <p className="m-0 text-[14px] text-danger" role="alert">{problem}</p>}
        <div className="flex gap-2">
          <button type="button" className="btn small primary" disabled={!agreed || busy || !!problem && !agreed} onClick={upload}>{busy ? "Uploading…" : "Upload font"}</button>
          <button type="button" className="btn small ghost" disabled={busy} onClick={() => { setPicked(null); setProblem(""); }}>Cancel</button>
        </div>
      </div>}
    </section>
  );
}

// Uploaded videos, with the one tile that adds another. `onTotal` gets the bytes stored once every page is loaded.
function Media({ kind, onTotal }: { kind: Kind; onTotal: (n: number | null) => void }) {
  const router = useRouter(), { fail, me } = useDash();
  const [list, setList] = useState<Video[] | null>(null), [more, setMore] = useState(false), [busy, setBusy] = useState(false), [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { up, start, cancel } = useUpload((u) => router.push(`/dashboard/project/?id=${u.upload_id}&tool=clips`));
  const load = useCallback(async (from: number) => {
    setBusy(true);
    try {
      const r = await api<{ projects: Video[] }>(`/v1/projects?limit=${PAGE}&offset=${from}`);
      setList((old) => [...(from ? old || [] : []), ...r.projects]);
      setMore(r.projects.length === PAGE);
    } catch (e) { fail(e); setList((old) => old || []); } finally { setBusy(false); }
  }, [fail]);
  useEffect(() => { load(0); }, [load]);
  useEffect(() => { onTotal(list && !more ? list.reduce((n, v) => n + (v.size_bytes || 0), 0) : null); }, [list, more, onTotal]);
  function take(f: File | undefined) {
    if (!f) return;
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start(f);
  }
  const soon = kind === "images" ? "Logos, overlays and stickers" : kind === "audio" ? "Music and sound effects" : "";

  return (
    <div id="media" role="tabpanel" className="grid gap-8">
      {soon ? <p className="m-0 flex flex-wrap items-center gap-2 text-[14.5px] text-fg-2">{soon} for your clips<ComingSoonBadge short /></p> : <>
        <div className="grid gap-[14px]">
          <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
          {up ? <div className="grid max-w-[420px] rounded-12 bg-card p-4 text-[13.5px]"><UploadProgress up={up} onCancel={cancel} /></div>
            : <button type="button" className={DROP} disabled={!me.email_verified} onClick={() => input.current?.click()}
                onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); take(e.dataTransfer.files[0]); }}>
                <Icon name="upload" size={22} />Add or drag file here</button>}
          <p className={`${CAPTION} flex flex-wrap items-center gap-2`}>Upload video<span className="font-normal text-fg-3">Images and audio</span><ComingSoonBadge short /></p>
          {problem && <p className="m-0 text-[14px] text-danger" role="alert">{problem}</p>}
        </div>
        {list === null ? <p className="muted">Loading…</p> : !!list.length && <ProjectGrid projects={list} size="home"
          onDeleted={(id) => setList((old) => (old || []).filter((x) => x.upload_id !== id))} />}
        {more && list && <button type="button" className="btn small ghost justify-self-start" disabled={busy} onClick={() => load(list.length)}>{busy ? "Loading…" : "Load more"}</button>}
      </>}
    </div>
  );
}

export default function Assets() {
  const [kind, setKind] = useState<Kind>("all"), [total, setTotal] = useState<number | null>(null);
  return (
    <div className="grid w-full grid-cols-[minmax(0,1fr)] gap-12 pt-[29px] narrow:pt-2">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="m-0 font-sans text-[26px] font-semibold leading-[32px] tracking-[-0.01em] text-fg narrow:text-[22px]">Asset library</h1>
        {total !== null && total > 0 && <span className="inline-flex items-center gap-1 text-[14.5px] text-fg-2">{bytes(total)} of video stored
          <Info label="About storage">The size of the videos you have uploaded. Each video and its clips are deleted when it expires; download the clips you want to keep.</Info></span>}
      </div>

      <section className="-mt-[14px] grid gap-[18px]" aria-labelledby="censor-title">
        <h2 id="censor-title" className={H2}>Censored words
          <Info label="About censored words">Swears are masked in burned captions and in SRT, VTT and TXT downloads (f***ing), keeping the first letter.
            Turn it on with <b className="font-medium">Censor swears</b> in a <Link href="/dashboard/brand-kit/">brand kit</Link> or when you start a job.</Info></h2>
        <div className="flex flex-wrap gap-x-[14px] gap-y-3">
          <SoonAdd text="Add my list" />
          <span className={`${BUTTON} text-text`}><Icon name="list" size={17} className="text-fg-2" />Swear words<Badge className="ml-1">Default</Badge></span>
        </div>
      </section>

      <section className="grid gap-[18px]" aria-labelledby="vocab-title">
        <h2 id="vocab-title" className={H2}>Brand vocabulary
          <Info label="About brand vocabulary">Streamer names, crews, places and items, so captions spell them the way your community does.</Info></h2>
        <div className="flex"><SoonAdd text="Add proper nouns" /></div>
      </section>

      <FontSection />

      <section className="grid gap-7" aria-labelledby="media-title">
        <h2 id="media-title" className={H2}>Media</h2>
        <Pills tone="quiet" label="Media type" value={kind} onChange={setKind} className="-ml-px justify-self-start"
          options={[{ value: "all", label: "All" }, { value: "images", label: "Images" }, { value: "videos", label: "Videos" }, { value: "audio", label: "Audio" }]} />
        <Media kind={kind} onTotal={setTotal} />
      </section>
    </div>
  );
}
