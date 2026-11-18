"use client";
// Home's one input: paste a public link or upload a file. A link opens the import box (ImportBox.tsx: consent,
// progress, the API's own refusal messages) already filled in; Bulk import opens it on several links.
// Styles: app/app-shell.css (`.source-bar`).
import { useEffect, useRef, useState } from "react";
import { videoFileProblem } from "@/lib/api";
import { Icon } from "./Icon";
import { ImportBox, RecentImports, useImportSources } from "./ImportBox";
import { useDash } from "./Shell";
import { ACCEPT, UploadProgress, useUpload } from "./Upload";

const isLink = (v: string) => /^https?:\/\/\S+\.\S+/i.test(v.trim());
const GLOW = "shadow-[0_0_0_4px_rgba(184,255,60,.18),0_0_40px_rgba(184,255,60,.2)]";
const CHIP = "inline-flex min-h-[32px] cursor-pointer items-center gap-[6px] rounded-8 border-0 bg-transparent px-3 font-body text-[13px] font-medium leading-[normal] text-label "
  + "enabled:hover:bg-chip enabled:hover:text-text disabled:cursor-default disabled:opacity-50";

// `pending` is a file picked on the public home page before signing up: it is uploaded as soon as this appears.
export function SourceBar({ onUploaded, pending }: { onUploaded: (uploadId: string) => void; pending?: File | null }) {
  const { me } = useDash();
  const sources = useImportSources();            // undefined while asking, null when this API has no link import
  const links = !!sources?.enabled;
  const [text, setText] = useState(""), [problem, setProblem] = useState(""), [over, setOver] = useState(false);
  const [box, setBox] = useState<{ mode: "one" | "many"; url?: string; n: number } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const { up, start, cancel } = useUpload((u) => onUploaded(u.upload_id));
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
    setBox((b) => ({ mode: "one", url: text.trim(), n: (b?.n || 0) + 1 }));
  }

  const names = sources?.sources.map((s) => s.name) || [];
  return (
    <div className="grid w-[min(100%,620px)] justify-items-center gap-[10px]"
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!up) take(e.dataTransfer.files[0]); }}>
      <input ref={file} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      {up ? <div className="w-full rounded-16 border border-solid border-line bg-card px-5 py-4"><UploadProgress up={up} onCancel={cancel} /></div>
        : <form className="grid w-full gap-[10px]" onSubmit={go}>
            <div className={`flex w-full items-center gap-2 rounded-full border-2 border-solid border-lime bg-[#0b0d0f] py-[5px] pl-5 pr-[5px] transition-shadow duration-200 ease-[ease] narrow:pl-4
              ${over ? GLOW : "shadow-[0_0_36px_rgba(184,255,60,.12)]"} focus-within:shadow-[0_0_0_4px_rgba(184,255,60,.18),0_0_40px_rgba(184,255,60,.2)]`}>
              <label htmlFor="source-input" className="sr-only">{links ? "Video link" : "Video"}</label>
              <input id="source-input" value={text} onChange={(e) => setText(e.target.value)} disabled={!links} inputMode="url" autoComplete="off"
                className="min-w-0 flex-1 border-0 bg-transparent px-0 py-[10px] text-[15px] focus:outline-none disabled:opacity-100 narrow:text-[16px]"
                placeholder={links ? "Paste a Twitch or Kick link, or upload a recording" : "Upload a stream recording to start"} />
              <button className="grid h-[42px] w-16 flex-none cursor-pointer place-items-center rounded-full border-0 bg-[linear-gradient(90deg,theme(colors.lime),theme(colors.lime-2))] text-ink
                transition-[box-shadow,transform] duration-200 ease-[ease] enabled:hover:translate-x-[2px] enabled:hover:shadow-[0_0_22px_rgba(184,255,60,.5)] disabled:cursor-default disabled:opacity-50 narrow:w-[52px]"
                aria-label={text.trim() ? "Import this link" : "Choose a file to upload"} disabled={!me.email_verified}>
                <Icon name="arrow" size={22} /></button>
            </div>
          </form>}
      {problem && <p className="error w-full" role="alert">{problem}</p>}
      <div className="flex flex-wrap justify-center gap-1 rounded-12 border border-solid border-line-soft bg-panel p-1">
        <button type="button" className={CHIP} disabled={!!up} onClick={() => file.current?.click()}><Icon name="upload" size={16} />Upload</button>
        <button type="button" className={CHIP} disabled={!links || !!up} onClick={() => setBox((b) => ({ mode: "many", n: (b?.n || 0) + 1 }))}>
          <Icon name="stack" size={16} />Bulk import</button>
        {names.length > 2 && <span className={`${CHIP} cursor-help text-muted`} title={sources!.sources.map((s) => `${s.name}: ${s.accepts}${s.note ? ` ${s.note}` : ""}`).join("\n")}>
          <Icon name="link" size={16} />{names.slice(0, 2).join(", ")} + {names.length - 2} more</span>}
      </div>
      {box && sources && <div className="relative w-full rounded-16 border border-solid border-line bg-panel px-[18px] pb-[18px] pt-1 [&_.import-head]:pr-10 [&_.import]:border-t-0">
        <button type="button" className="icon-btn absolute right-3 top-3 h-8 w-8 border-0" aria-label="Close the import box" onClick={() => setBox(null)}><Icon name="close" size={18} /></button>
        <ImportBox key={box.n} sources={sources} start={box} onReady={(u) => onUploaded(u.upload_id)} />
      </div>}
      {!box && sources && <div className="w-full [&_.import-recent_h3]:text-[14px] [&_.import-recent_h3]:text-muted"><RecentImports reload={0} /></div>}
    </div>
  );
}
