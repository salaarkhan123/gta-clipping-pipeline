"use client";
// Home's one input: paste a public link or upload a file. A link goes to the chooser (/dashboard/start/): what to
// make, the price, consent, one button. Bulk import opens the import box (ImportBox.tsx) on several links.
// Styles: app/app-shell.css (`.source-bar`).
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { videoFileProblem } from "@/lib/api";
import { Icon } from "./Icon";
import { ImportBox, RecentImports, useImportSources } from "./ImportBox";
import { useDash } from "./Shell";
import { ACCEPT, UploadProgress, useUpload } from "./Upload";

const isLink = (v: string) => /^https?:\/\/\S+\.\S+/i.test(v.trim());

// `pending` is a file picked on the public home page before signing up: it is uploaded as soon as this appears.
export function SourceBar({ onUploaded, pending }: { onUploaded: (uploadId: string) => void; pending?: File | null }) {
  const { me } = useDash();
  const router = useRouter();
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
    router.push(`/dashboard/start/?url=${encodeURIComponent(text.trim())}`);
  }

  const names = sources?.sources.map((s) => s.name) || [];
  return (
    <div className={`source-bar ${over ? "over" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!up) take(e.dataTransfer.files[0]); }}>
      <input ref={file} type="file" accept={ACCEPT} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      {up ? <div className="source-status"><UploadProgress up={up} onCancel={cancel} /></div>
        : <form className="source-form" onSubmit={go}>
            <div className="source-field">
              <label htmlFor="source-input" className="sr-only">{links ? "Video link" : "Video"}</label>
              <input id="source-input" value={text} onChange={(e) => setText(e.target.value)} disabled={!links} inputMode="url" autoComplete="off"
                placeholder={links ? "Paste a Twitch or Kick link, or upload a recording" : "Upload a stream recording to start"} />
              <button className="source-go" aria-label={text.trim() ? "Import this link" : "Choose a file to upload"} disabled={!me.email_verified}>
                <Icon name="arrow" size={22} /></button>
            </div>
          </form>}
      {problem && <p className="error" role="alert">{problem}</p>}
      <div className="source-row">
        <button type="button" className="source-chip" disabled={!!up} onClick={() => file.current?.click()}><Icon name="upload" size={16} />Upload</button>
        <button type="button" className="source-chip" disabled={!links || !!up} onClick={() => setBox((b) => ({ mode: "many", n: (b?.n || 0) + 1 }))}>
          <Icon name="stack" size={16} />Bulk import</button>
        {names.length > 2 && <span className="source-chip plain" title={sources!.sources.map((s) => `${s.name}: ${s.accepts}${s.note ? ` ${s.note}` : ""}`).join("\n")}>
          <Icon name="link" size={16} />{names.slice(0, 2).join(", ")} + {names.length - 2} more</span>}
      </div>
      {box && sources && <div className="source-import">
        <button type="button" className="icon-btn source-close" aria-label="Close the import box" onClick={() => setBox(null)}><Icon name="close" size={18} /></button>
        <ImportBox key={box.n} sources={sources} start={box} onReady={(u) => onUploaded(u.upload_id)} />
      </div>}
      {!box && sources && <div className="source-recent"><RecentImports reload={0} /></div>}
    </div>
  );
}
