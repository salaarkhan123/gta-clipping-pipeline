"use client";
import { useRef, useState } from "react";
import { VIDEO_TYPES } from "@/lib/api";

export function DropZone({ onFile, busy, compact }: { onFile: (f: File) => void; busy?: boolean; compact?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState("");

  function take(files: FileList | null) {
    const f = files?.[0];
    if (!f) return;
    const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
    if (!VIDEO_TYPES.split(",").includes(ext)) { setError(`${f.name} isn't a video file we can read. Use MP4, MOV, MKV or WebM.`); return; }
    setError("");
    onFile(f);
  }

  return (
    <div className={`drop ${over ? "over" : ""} ${compact ? "compact" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files); }}>
      <input ref={input} type="file" accept={VIDEO_TYPES + ",video/*"} hidden onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
      <p className="drop-title">{compact ? "Drop another video here" : "Drop a stream recording here"}</p>
      <button type="button" className="btn primary" disabled={busy} onClick={() => input.current?.click()}>Choose a video</button>
      <p className="drop-hint">MP4, MOV, MKV or WebM, up to 8 GB and 6 hours.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
