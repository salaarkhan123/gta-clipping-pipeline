"use client";
import { useId, useRef, useState } from "react";
import { Icon } from "@/components/dash/Icon";

// A labelled text input. The label sits above, 14 px; the control is a grey block.
export function Field({ label, hint, className = "", ...rest }: React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: React.ReactNode }) {
  const id = useId();
  return (
    <div className={`grid gap-2 ${className}`}>
      <label htmlFor={id} className="flex items-baseline gap-2 text-[14px] font-medium text-text">{label}{hint && <span className="text-[12px] font-normal text-fg-2">{hint}</span>}</label>
      <input id={id} {...rest} className="h-11 w-full rounded-12 border border-solid border-transparent bg-control px-4 font-sans text-[14px] text-text placeholder:text-fg-3 transition-colors duration-base focus:border-line-strong focus:outline-none" />
    </div>
  );
}

// The import field: one pill with the action inside it. Paste a link, or drop or pick a file.
// It only collects; what happens to the link or file is the caller's.
export function ImportField({ id, placeholder, cta, onLink, onFile, accept, problem, size = "lg", tone = "site", className = "" }: {
  id: string; placeholder: string; cta: string; onLink: (text: string) => void; onFile: (f: File) => void; accept: string;
  problem?: string; size?: "md" | "lg" | "xl"; tone?: "site" | "bar"; className?: string;
}) {
  const [text, setText] = useState(""), [over, setOver] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  // xl is the public hero's field: 64 px tall with a 52 px button inside, measured from the reference.
  const h = size === "xl" ? "h-16 narrow:h-14" : size === "lg" ? "h-14 narrow:h-[52px]" : "h-12";
  const type = size === "xl" ? "text-[17px] narrow:text-[16px]" : "text-[15px]";
  const cta_ = size === "xl" ? "!h-[52px] !px-6 !text-[17px] narrow:!h-11 narrow:!px-4 narrow:!text-[15px]" : size === "lg" ? "!h-11 !px-5" : "small";
  return (
    <form id={id} noValidate className={`relative grid w-full gap-2 ${className}`}
      onSubmit={(e) => { e.preventDefault(); if (text.trim()) onLink(text); else file.current?.click(); }}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}>
      <input ref={file} type="file" accept={accept} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      <div className={`flex ${h} w-full items-center gap-1 rounded-pill pl-[6px] pr-[6px] transition-[box-shadow,background-color] duration-base
        ${tone === "bar" ? "bg-[#222222] shadow-bar" : "bg-[#222222]"}
        ${over ? "shadow-[inset_0_0_0_1px_theme(colors.lime)]" : "focus-within:shadow-[inset_0_0_0_1px_rgba(255,255,255,.28)]"}`}>
        <button type="button" onClick={() => file.current?.click()} aria-label="Upload a video file" title="Upload a video file"
          className={`grid flex-none cursor-pointer place-items-center rounded-pill border-0 bg-transparent text-fg-2 transition-colors duration-base hover:bg-white/[.07] hover:text-fg ${size === "xl" ? "h-12 w-12 narrow:h-10 narrow:w-10" : "h-10 w-10"}`}>
          <Icon name="plus" size={size === "xl" ? 22 : 18} /></button>
        <label htmlFor={`${id}-link`} className="sr-only">Video link</label>
        {/* w-0: the field's width comes from flex-1 alone. Without it WebKit counts the input's default width in
            the page's minimum width and the hero field runs past the gutter on a phone. */}
        <input id={`${id}-link`} value={text} onChange={(e) => setText(e.target.value)} inputMode="url" autoComplete="off" spellCheck={false} placeholder={placeholder}
          className={`h-full w-0 min-w-0 flex-1 truncate rounded-none border-0 bg-transparent p-0 font-sans ${type} text-text placeholder:text-fg-2 focus:outline-none`} />
        <button type="submit" className={`btn primary flex-none !rounded-pill ${cta_}`}>{cta}</button>
      </div>
      {problem && <p role="alert" className={`m-0 px-5 text-left text-[13px] text-danger ${tone === "bar" ? "absolute bottom-full mb-2 rounded-12 bg-card px-4 py-2 shadow-pop" : ""}`}>{problem}</p>}
    </form>
  );
}
