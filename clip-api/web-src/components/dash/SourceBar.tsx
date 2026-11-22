"use client";
// Home's start card. Its tabs sit on its top edge: Clip long video (built), Auto-edit footage (Coming soon: the API
// has no job that polishes a whole video without clipping it) and, on the right, Open editor (the editor opens on a
// clip, so it goes to the list of clips).
// Clip long video is one row: a public link (Twitch, Kick, YouTube best effort, a Google Drive or Dropbox share
// link) with its button, and under it Upload. A file can also be dropped anywhere on the card. Either way the
// job-setup screen opens next: a link on /dashboard/start/, an upload on its project page, with every built polish
// option switched on (`polish=` in the address); that screen can change them.
// Data: GET /v1/imports/sources (which link sources are on), POST /v1/uploads (useUpload), POST /v1/imports/bulk.
import Link from "next/link";
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
type Tab = "clip" | "auto";
const TABS: [Tab, IconName, string][] = [["clip", "scissors", "Clip long video"], ["auto", "wand", "Auto-edit footage"]];
// Share-link sources beside Upload. Each is offered only when GET /v1/imports/sources lists it.
const FROM: { platform: string; icon: IconName; name: string; hint: string }[] = [
  { platform: "gdrive", icon: "cloud", name: "Google Drive", hint: "Paste a Google Drive share link set to “Anyone with the link”" },
  { platform: "dropbox", icon: "folder", name: "Dropbox", hint: "Paste a Dropbox share link to one file" },
];
const LINK_HINT = `Paste ${linkPhrase()}`;
// Every built polish option on: what a new project starts with.
const ALL_POLISH = Object.fromEntries(POLISH.filter((p) => p.built).map((p) => [p.id, true])) as Polish;
const TAB = "relative inline-flex h-[47px] min-w-0 cursor-pointer items-center gap-2 border-0 px-5 text-left font-sans text-[16px] font-medium leading-[1.2] no-underline narrow:gap-[6px] narrow:px-3 narrow:text-[13px]";
const QUIET = "inline-flex h-9 cursor-pointer items-center gap-2 rounded-control border-0 bg-transparent px-[10px] font-sans text-[15px] font-medium text-text transition-colors duration-base hover:bg-control disabled:cursor-default disabled:opacity-45 narrow:text-[14px]";

// `pending` is a file picked on the public home page before signing up: it is uploaded as soon as this appears.
// `onUploaded` gets the new upload's id and the query that opens its job-setup screen.
export function SourceBar({ onUploaded, pending }: { onUploaded: (uploadId: string, query: string) => void; pending?: File | null }) {
  const { me } = useDash();
  const router = useRouter();
  const sources = useImportSources();            // undefined while asking, null when this API has no link import
  const links = !!sources?.enabled;
  const has = (platform: string) => !!sources?.sources.some((s) => s.platform === platform);
  const [tab, setTab] = useState<Tab>("clip");
  const [text, setText] = useState(""), [hint, setHint] = useState(LINK_HINT), [problem, setProblem] = useState(""), [over, setOver] = useState(false);
  const [box, setBox] = useState<{ mode: "one" | "many"; url?: string; n: number } | null>(null);
  const [removing, setRemoving] = useState(false);
  const file = useRef<HTMLInputElement>(null), field = useRef<HTMLInputElement>(null);
  const query = `&tool=clips&${polishQuery(ALL_POLISH)}`;
  const { up, start, cancel } = useUpload((u) => onUploaded(u.upload_id, query));
  useEffect(() => { if (pending) start(pending); }, [pending]);   // eslint-disable-line react-hooks/exhaustive-deps

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
    router.push(`/dashboard/start/?url=${encodeURIComponent(text.trim())}&${polishQuery(ALL_POLISH)}`);
  }
  const askLink = (h: string) => { setHint(h); setTimeout(() => field.current?.focus(), 0); };

  return (
    <div className="grid w-full min-w-0 max-w-[590px] grid-cols-[minmax(0,1fr)]">
      <div className="flex min-w-0 items-end">
        <div role="tablist" aria-label="What to do" className="flex min-w-0 items-end">
          {TABS.map(([id, icon, name]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} aria-controls="start-card" onClick={() => setTab(id)}
              className={`${TAB} rounded-t-[20px] ${tab === id ? "start-tab bg-card text-text" : "bg-transparent text-fg-2 hover:text-text"}`}>
              <Icon name={icon} size={19} className={tab === id ? "text-lime" : ""} />{name}{id === "auto" && <ComingSoonBadge short className="narrow:hidden" />}</button>))}
        </div>
        <Link href="/dashboard/library/?view=clips" title="Pick a clip and open it in the editor" className={`${TAB} ml-auto text-fg-2 hover:text-text`}>
          <Icon name="sliders" size={19} />Open editor</Link>
      </div>
      <div id="start-card" role="tabpanel" aria-label={TABS.find(([id]) => id === tab)![2]}
        className={`rounded-[24px] bg-card p-4 transition-shadow duration-base ${tab === "clip" ? "rounded-tl-none" : ""} ${over ? "shadow-[inset_0_0_0_1px_theme(colors.lime)]" : ""}`}
        onDragOver={(e) => { if (tab !== "clip") return; e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { if (tab !== "clip") return; e.preventDefault(); setOver(false); if (!up) take(e.dataTransfer.files[0]); }}>
        {tab !== "clip" ? <div className="grid min-h-[117px] place-items-center content-center gap-3 px-6 py-4 text-center">
            <ComingSoonBadge />
            <p className="m-0 max-w-[460px] text-[14px] leading-[1.45] text-fg-2">Polish a short video without cutting it into clips: captions, cleaner speech and a hook. Today, Captions and Reframe work on any part of a video.</p>
          </div>
        : <>
            <input ref={file} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
            {up ? <div className="px-2 py-3"><UploadProgress up={up} onCancel={cancel} /></div>
              : <form onSubmit={go} className="flex h-[62px] w-full items-center gap-3 rounded-[16px] border border-solid border-line-soft bg-panel pl-5 pr-[7px] transition-colors duration-base focus-within:border-line-strong narrow:h-14 narrow:pl-4">
                  <Icon name="link" size={18} className="flex-none text-fg-3" />
                  <label htmlFor="source-input" className="sr-only">Video link</label>
                  <input ref={field} id="source-input" value={text} onChange={(e) => setText(e.target.value)} disabled={!links} inputMode="url" autoComplete="off" spellCheck={false}
                    className="h-full min-w-0 flex-1 !rounded-none !border-0 !bg-transparent !p-0 font-sans text-[16px] text-text placeholder:text-fg-3 focus:outline-none disabled:opacity-100"
                    placeholder={links ? hint : "Link import is off: upload a file"} />
                  <button className="btn primary h-[47px] flex-none !rounded-[12px] px-6 text-[15px] narrow:h-10 narrow:px-4" disabled={!me.email_verified}>Get clips</button>
                </form>}
            {problem && <p className="error mx-0 mb-0 mt-3" role="alert">{problem}</p>}
            <div className="mt-[19px] flex flex-wrap items-center gap-x-4 gap-y-1">
              <button type="button" className={QUIET} disabled={!me.email_verified || !!up} onClick={() => file.current?.click()}><Icon name="upload" size={18} />Upload</button>
              {links && FROM.filter((s) => has(s.platform)).map((s) => (
                <button key={s.platform} type="button" className={QUIET} onClick={() => askLink(s.hint)}><Icon name={s.icon} size={18} />{s.name}</button>))}
              {links && <button type="button" className={`${QUIET} ml-auto !font-normal !text-fg-2 hover:!text-text`} disabled={!!up}
                onClick={() => setBox((b) => ({ mode: "many", n: (b?.n || 0) + 1 }))}>Several links</button>}
            </div>
          </>}
      </div>
      <p className="mx-0 mb-0 mt-[10px] text-center text-[13px] leading-[20px] text-fg-3">Upload only videos you own or have permission to clip. <a className="text-fg-2 underline" href="/terms/#rights">Terms</a><span aria-hidden="true"> · </span>
        <button type="button" className="cursor-pointer border-0 bg-transparent p-0 font-sans text-[13px] text-fg-2 underline" aria-expanded={removing} onClick={() => setRemoving(!removing)}>Remove an import</button></p>
      {box && sources && <div className="relative mt-4 w-full rounded-16 bg-card px-[18px] pb-[18px] pt-1 [&_.import-head]:pr-10 [&_.import]:border-t-0">
        <button type="button" className="icon-btn absolute right-3 top-3 h-8 w-8 border-0" aria-label="Close the import box" onClick={() => setBox(null)}><Icon name="close" size={18} /></button>
        <ImportBox key={box.n} sources={sources} start={box} onReady={(u) => onUploaded(u.upload_id, query)} />
      </div>}
      {removing && <div className="mt-4 w-full rounded-16 bg-card p-4"><ImportTakedown /></div>}
      {!box && sources && <div className="mt-4 w-full empty:hidden [&_.import-recent_h3]:text-[14px] [&_.import-recent_h3]:text-muted"><RecentImports reload={0} /></div>}
    </div>
  );
}
