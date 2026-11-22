"use client";
// The public site's one way in: paste a link or upload a file. A link opens the link chooser (/dashboard/start/?url=:
// what to make, the price, consent, one button); a file is handed to the dashboard, which uploads it. Signed out,
// the sign-up dialog comes first and the same step follows. Used by the hero and by the sticky bar (StartBar).
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthDialog } from "@/components/Auth";
import { ImportField } from "@/components/ui/Field";
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
  const [problem, setProblem] = useState("");
  const bar = variant === "bar";
  function file(f: File) {
    const bad = videoFileProblem(f);
    setProblem(bad || "");
    if (!bad) start.file(f);
  }
  function link(text: string) {
    if (!isLink(text)) { setProblem("That doesn't look like a link. Paste the full address, starting with https://"); return; }
    setProblem("");
    start.link(text);
  }
  return <ImportField id={id || `start-${variant}`} placeholder={pastePrompt()} cta="Get clips" onLink={link} onFile={file} accept={VIDEO_TYPES + ",video/*"}
    problem={problem} tone={bar ? "bar" : "site"} size={bar ? "lg" : "xl"} className={bar ? "" : "max-w-[560px]"} />;
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
      className={`fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-6 pt-14 transition-[opacity,transform] duration-300 ease-out narrow:pb-4
        bg-[linear-gradient(transparent,rgba(0,0,0,.92)_55%)] ${shown ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-6 opacity-0"}`}>
      {/* The page fades to black behind the bar, so it never sits on top of readable text. */}
      <div className="w-[min(560px,100%)]"><StartInput start={start} variant="bar" id="start-bar" /></div>
    </div>
  );
}
