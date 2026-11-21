"use client";
// Home's start card. Three tabs: Clip long video (built), Auto-edit footage and Open editor (Coming soon: the API
// has no job that polishes a whole video without clipping it, and the editor opens on a clip, not on its own).
// Clip long video takes a file (drop, or Choose video) or a public link (Twitch, Kick, YouTube best effort, a
// Google Drive or Dropbox share link), then opens the job-setup screen: a link on /dashboard/start/, an upload on
// its project page. The polish chips preset that screen (`polish=` in the address); it can still change them.
// Data: GET /v1/imports/sources (which link sources are on), POST /v1/uploads (useUpload), POST /v1/imports/bulk.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { videoFileProblem } from "@/lib/api";
import { POLISH, Polish, polishQuery } from "@/lib/polish";
import { Icon, IconName } from "./Icon";
import { ImportBox, RecentImports, useImportSources } from "./ImportBox";
import { ImportTakedown } from "./ImportTakedown";
import { useDash } from "./Shell";
import { ACCEPT, UploadProgress, useUpload } from "./Upload";
import { linkPhrase } from "@/lib/platforms";

const isLink = (v: string) => /^https?:\/\/\S+\.\S+/i.test(v.trim());
type Tab = "clip" | "auto" | "editor";
const TABS: [Tab, IconName, string][] = [["clip", "scissors", "Clip long video"], ["auto", "wand", "Auto-edit footage"], ["editor", "sliders", "Open editor"]];
// Where a link can come from, and what to paste for it. Each is offered only when GET /v1/imports/sources lists it.
const FROM: { platform: string; icon: IconName; name: string; hint: string }[] = [
  { platform: "twitch", icon: "link", name: "Paste a link", hint: `Paste ${linkPhrase()}` },
  { platform: "gdrive", icon: "cloud", name: "Google Drive", hint: "Paste a Google Drive share link set to “Anyone with the link”" },
  { platform: "dropbox", icon: "folder", name: "Dropbox", hint: "Paste a Dropbox share link to one file" },
];
const MENU_ITEM = "flex min-h-[42px] w-full cursor-pointer items-center gap-3 rounded-12 border-0 bg-transparent px-3 text-left font-sans text-[14px] text-text hover:bg-chip-hover disabled:cursor-default disabled:opacity-50";
const CHIP = "inline-flex min-h-[34px] items-center gap-[6px] rounded-full border border-solid px-3 font-sans text-[13px] font-medium leading-[normal]";

// `pending` is a file picked on the public home page before signing up: it is uploaded as soon as this appears.
// `onUploaded` gets the new upload's id and the query that opens its job-setup screen.
export function SourceBar({ onUploaded, pending }: { onUploaded: (uploadId: string, query: string) => void; pending?: File | null }) {
  const { me } = useDash();
  const router = useRouter();
  const sources = useImportSources();            // undefined while asking, null when this API has no link import
  const links = !!sources?.enabled;
  const has = (platform: string) => !!sources?.sources.some((s) => s.platform === platform);
  const [tab, setTab] = useState<Tab>("clip");
  const [polish, setPolish] = useState<Polish>(() => Object.fromEntries(POLISH.filter((p) => p.built).map((p) => [p.id, true])) as Polish);
  const [text, setText] = useState(""), [hint, setHint] = useState(FROM[0].hint), [problem, setProblem] = useState(""), [over, setOver] = useState(false);
  const [menu, setMenu] = useState(false);
  const [box, setBox] = useState<{ mode: "one" | "many"; url?: string; n: number } | null>(null);
  const file = useRef<HTMLInputElement>(null), field = useRef<HTMLInputElement>(null), menuBox = useRef<HTMLDivElement>(null);
  const query = `&tool=clips&${polishQuery(polish)}`;
  const { up, start, cancel } = useUpload((u) => onUploaded(u.upload_id, query));
  useEffect(() => { if (pending) start(pending); }, [pending]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!menu) return;
    const away = (e: Event) => { if (!menuBox.current?.contains(e.target as Node)) setMenu(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    document.addEventListener("pointerdown", away); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [menu]);

  function take(f: File | null | undefined) {
    if (!f) return;
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start(f);
  }
  function go(e: React.FormEvent) {
    e.preventDefault();
    setProblem("");
    if (!text.trim()) { file.current?.click(); return; }
    if (!links) { setProblem("Link import is switched off right now. Upload the file instead."); return; }
    if (!isLink(text)) { setProblem("That doesn't look like a link. Paste the full address, starting with https://"); return; }
    router.push(`/dashboard/start/?url=${encodeURIComponent(text.trim())}&${polishQuery(polish)}`);
  }
  const askLink = (h: string) => { setMenu(false); setHint(h); setTimeout(() => field.current?.focus(), 0); };

  return (
    <div className="grid w-[min(100%,820px)] min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
      <div role="tablist" aria-label="What to do" className="flex min-w-0 items-end gap-1 px-2 narrow:px-0">
        {TABS.map(([id, icon, name]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} aria-controls="start-card" onClick={() => setTab(id)}
            className={`relative inline-flex min-h-[48px] min-w-0 cursor-pointer items-center gap-2 rounded-t-[20px] border-0 px-5 text-left font-sans text-[15px] font-medium leading-[1.2] narrow:gap-[6px] narrow:px-[10px] narrow:text-[12.5px]
              ${id === "editor" ? "ml-auto" : ""} ${tab === id ? "bg-surface text-text" : "bg-transparent text-muted hover:text-text"}`}>
            <Icon name={icon} size={19} className={tab === id ? "text-lime" : ""} />{name}</button>))}
      </div>
      <div id="start-card" role="tabpanel" aria-label={TABS.find(([id]) => id === tab)![2]}
        className={`-mt-3 rounded-[24px] bg-surface p-3 ${tab === "clip" ? "rounded-tl-[24px]" : ""} ${tab === "clip" ? "[border-top-left-radius:0]" : tab === "editor" ? "[border-top-right-radius:0]" : ""}`}
        onDragOver={(e) => { if (tab !== "clip") return; e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { if (tab !== "clip") return; e.preventDefault(); setOver(false); if (!up) take(e.dataTransfer.files[0]); }}>
        {tab !== "clip" ? <div className="grid min-h-[200px] place-items-center content-center gap-3 rounded-[18px] border-2 border-dashed border-line px-6 py-8 text-center">
            <ComingSoonBadge />
            <p className="m-0 max-w-[460px] text-[15px] text-label">{tab === "auto"
              ? "Polish a short video without cutting it into clips: captions, cleaner speech and a hook. Coming soon. Today, AI Captions and AI Reframe work on any part of a video."
              : "Open the editor on any video. Coming soon. Today, open a clip's Edit button to trim it, cut by transcript and restyle it."}</p>
          </div>
        : <div className={`grid gap-4 rounded-[18px] border-2 border-dashed px-6 pb-5 pt-7 transition-colors narrow:px-3 ${over ? "border-lime bg-lime-wash" : "border-line"}`}>
            <input ref={file} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
            {up ? <UploadProgress up={up} onCancel={cancel} /> : <>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <span className="text-[16px] text-text narrow:text-[15px]">Drag and drop a video or</span>
                <div ref={menuBox} className="relative">
                  <button type="button" className="btn primary gap-2 px-5 py-[10px]" aria-expanded={menu} aria-haspopup="menu" disabled={!me.email_verified}
                    onClick={() => setMenu(!menu)}>Choose video<Icon name="chevron" size={18} /></button>
                  {menu && <div role="menu" className="absolute left-1/2 top-[calc(100%+8px)] z-[60] grid w-[260px] -translate-x-1/2 gap-1 rounded-16 border border-solid border-line bg-raised p-2 shadow-pop">
                    <button type="button" role="menuitem" className={MENU_ITEM} onClick={() => { setMenu(false); file.current?.click(); }}><Icon name="upload" size={18} />Upload from device</button>
                    {FROM.map((s) => <button key={s.platform} type="button" role="menuitem" className={MENU_ITEM} disabled={!links || !has(s.platform)}
                      onClick={() => askLink(s.hint)}><Icon name={s.icon} size={18} />{s.name}</button>)}
                    {!links && sources !== undefined && <p className="m-0 px-3 pb-1 text-[12px] text-muted">Link import is switched off for now. Upload the file instead.</p>}
                  </div>}
                </div>
              </div>
              <form className="mx-auto w-full max-w-[600px]" onSubmit={go}>
                <div className="flex w-full items-center gap-2 rounded-full border border-solid border-line bg-bg py-[5px] pl-4 pr-[5px] focus-within:border-line-strong">
                  <Icon name="link" size={18} className="flex-none text-muted" />
                  <label htmlFor="source-input" className="sr-only">Video link</label>
                  <input ref={field} id="source-input" value={text} onChange={(e) => setText(e.target.value)} disabled={!links} inputMode="url" autoComplete="off"
                    className="min-w-0 flex-1 border-0 bg-transparent px-0 py-[9px] text-[15px] focus:outline-none disabled:opacity-100 narrow:text-[16px]"
                    placeholder={links ? hint : "Link import is off: upload a file"} />
                  <button className="btn small primary flex-none" disabled={!me.email_verified || !links || !text.trim()}>Get clips</button>
                </div>
              </form>
            </>}
            {problem && <p className="error m-0" role="alert">{problem}</p>}
            <div className="flex flex-wrap items-center justify-center gap-2" role="group" aria-label="Polish the clips with">
              <span className="text-[13px] text-muted">Polish clips with:</span>
              {POLISH.map((p) => p.built
                ? <button key={p.id} type="button" aria-pressed={!!polish[p.id]} onClick={() => setPolish((x) => ({ ...x, [p.id]: !x[p.id] }))}
                    className={`${CHIP} cursor-pointer ${polish[p.id] ? "border-line-strong bg-chip-hover text-text" : "border-line-soft bg-transparent text-muted line-through decoration-1"}`}>
                    <Icon name={p.icon} size={15} />{p.name}</button>
                : <span key={p.id} className={`${CHIP} border-line-soft text-fg-3`} aria-disabled="true"><Icon name={p.icon} size={15} />{p.name}<ComingSoonBadge short /></span>)}
            </div>
          </div>}
      </div>
      <p className="muted small text-center">Upload only videos you own or have permission to clip. See the <a href="/terms/#rights">Terms</a>.</p>
      {tab === "clip" && <div className="flex flex-wrap items-center justify-center gap-3 text-[13px] text-muted">
        <button type="button" className="link small" disabled={!links || !!up} onClick={() => setBox((b) => ({ mode: "many", n: (b?.n || 0) + 1 }))}>Import several links at once</button>
      </div>}
      {box && sources && <div className="relative w-full rounded-16 border border-solid border-line bg-panel px-[18px] pb-[18px] pt-1 [&_.import-head]:pr-10 [&_.import]:border-t-0">
        <button type="button" className="icon-btn absolute right-3 top-3 h-8 w-8 border-0" aria-label="Close the import box" onClick={() => setBox(null)}><Icon name="close" size={18} /></button>
        <ImportBox key={box.n} sources={sources} start={box} onReady={(u) => onUploaded(u.upload_id, query)} />
      </div>}
      {!box && sources && <div className="w-full [&_.import-recent_h3]:text-[14px] [&_.import-recent_h3]:text-muted"><RecentImports reload={0} /></div>}
      <details className="w-full rounded-16 border border-solid border-line bg-panel px-4 py-2">
        <summary className="cursor-pointer py-2 text-[14px] font-medium text-label">Remove an imported video from this account</summary>
        <div className="pb-3 pt-1"><ImportTakedown /></div>
      </details>
    </div>
  );
}
