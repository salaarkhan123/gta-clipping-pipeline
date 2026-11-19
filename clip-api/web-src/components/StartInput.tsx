"use client";
// The public site's one way in: paste a link or upload a file. A link opens the link chooser (/dashboard/start/?url=:
// what to make, the price, consent, one button); a file is handed to the dashboard, which uploads it. Signed out,
// the sign-up dialog comes first and the same step follows. Used by the hero and by the sticky bar (StartBar).
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AuthDialog } from "@/components/Auth";
import { Icon } from "@/components/dash/Icon";
import { getToken, setPendingFile, VIDEO_TYPES, videoFileProblem } from "@/lib/api";
import { pastePrompt } from "@/lib/platforms";

const isLink = (v: string) => /^https?:\/\/\S+\.\S+/i.test(v.trim());

// What to do with a link or a file, plus the sign-up dialog to render once on the page.
export function useStart() {
  const router = useRouter();
  const [next, setNext] = useState<string | null>(null);        // where to go once signed in
  const go = (path: string) => (getToken() ? router.push(path) : setNext(path));
  return {
    link: (url: string) => go(`/dashboard/start/?url=${encodeURIComponent(url.trim())}`),
    file: (f: File) => { setPendingFile(f); go("/dashboard/"); },
    dialog: <AuthDialog open={!!next} onClose={() => setNext(null)} onDone={() => { const p = next!; setNext(null); router.push(p); }}
      note="Create an account and we'll pick up your video straight away." />,
  };
}

type Start = ReturnType<typeof useStart>;

export function StartInput({ start, variant = "hero", id }: { start: Start; variant?: "hero" | "bar"; id?: string }) {
  const [text, setText] = useState(""), [problem, setProblem] = useState(""), [over, setOver] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const bar = variant === "bar";

  function take(f: File | null | undefined) {
    if (!f) return;
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start.file(f);
  }
  function submit(e: React.FormEvent) {
    e.preventDefault();
    setProblem("");
    if (!text.trim()) { file.current?.click(); return; }
    if (!isLink(text)) { setProblem("That doesn't look like a link. Paste the full address, starting with https://"); return; }
    start.link(text);
  }
  useEffect(() => { if (!text) setProblem(""); }, [text]);

  return (
    <form id={id} onSubmit={submit} noValidate className={`relative grid w-full gap-2 ${bar ? "" : "max-w-[520px]"}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]); }}>
      <input ref={file} type="file" accept={VIDEO_TYPES + ",video/*"} hidden onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      <div className={`flex h-16 w-full items-center gap-1 rounded-pill pr-[6px] transition-[box-shadow,background-color] duration-200 narrow:h-14
        ${bar ? "bg-[rgba(26,26,26,.92)] shadow-bar backdrop-blur-md" : "bg-card-2 shadow-card"}
        ${over ? "shadow-[inset_0_0_0_1px_theme(colors.lime)]" : "focus-within:shadow-[inset_0_0_0_1px_rgba(255,255,255,.3)]"}`}>
        <button type="button" onClick={() => file.current?.click()} aria-label="Upload a video file"
          className="ml-[6px] grid h-11 w-11 flex-none cursor-pointer place-items-center rounded-pill border-0 bg-transparent text-fg-2 transition-colors hover:bg-[rgba(255,255,255,.06)] hover:text-fg narrow:h-10 narrow:w-10">
          <Icon name="plus" size={20} />
        </button>
        <label htmlFor={`${id || variant}-link`} className="sr-only">Video link</label>
        <input id={`${id || variant}-link`} value={text} onChange={(e) => setText(e.target.value)} inputMode="url" autoComplete="off" spellCheck={false}
          placeholder={pastePrompt()}
          className="h-full min-w-0 flex-1 truncate rounded-none border-0 bg-transparent p-0 font-sans text-[16px] text-label placeholder:text-fg-2 focus:outline-none" />
        <button type="submit" className="btn btn-primary h-[52px] flex-none narrow:h-11 narrow:px-4 narrow:text-[15px]">
          Get clips
        </button>
      </div>
      {problem && <p role="alert" className={`px-5 text-left text-[14px] text-danger ${bar ? "absolute bottom-full mb-2 rounded-12 bg-card px-4 py-2 shadow-pop" : ""}`}>{problem}</p>}
    </form>
  );
}

// The same input, pinned to the bottom of the screen once the hero's input has scrolled away, and out of the way
// again over the footer. `after`: the id of the element it waits to leave the screen; `before`: the footer's id.
export function StartBar({ start, after, before }: { start: Start; after: string; before: string }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const seen: Record<string, boolean> = { [after]: true, [before]: false };
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) seen[e.target.id] = e.isIntersecting;
      setShown(!seen[after] && !seen[before]);
    });
    for (const id of [after, before]) { const el = document.getElementById(id); if (el) io.observe(el); }
    return () => io.disconnect();
  }, [after, before]);
  return (
    <div aria-hidden={!shown} inert={!shown}
      className={`fixed bottom-6 left-1/2 z-40 w-[min(560px,calc(100%-32px))] -translate-x-1/2 transition-[opacity,transform] duration-300 ease-out narrow:bottom-4
        ${shown ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-6 opacity-0"}`}>
      <StartInput start={start} variant="bar" id="start-bar" />
    </div>
  );
}
