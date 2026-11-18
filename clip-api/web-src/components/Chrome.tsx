"use client";
// The public site's frame (the blur sits on the bar, not the header, so the phone menu can be position: fixed): announcement bar (only when there is news), sticky nav with a Tools menu, footer.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon } from "@/components/dash/Icon";
import { getToken } from "@/lib/api";
import { useLanguageSwitches } from "@/lib/languages";
import { isBuilt, toolHref, TOOLS } from "@/lib/tools";

const DOCS = "https://api.clutchclips.io/docs";
// Shown above the nav when set. Only for something real that has shipped; null hides the bar.
const ANNOUNCEMENT: { text: string; href: string; cta: string } | null = null;

// The ClutchClips logo everywhere (header, footer, phone menu, app top bar): the mark is app/icon.svg, the same file
// as the favicon, next to the wordmark in Geist. A new logo is a one-file change: replace app/icon.svg.
// `small`: the app's top bar size; the name hides on a phone there.
export function Logo({ small }: { small?: boolean }) {
  const size = small ? 28 : 32;
  return (
    <Link href="/" aria-label="ClutchClips home" className={`flex flex-none items-center font-sans font-bold tracking-[-0.03em] text-fg ${small ? "gap-2 text-[17px]" : "gap-[10px] text-[20px]"}`}>
      <img src="/icon.svg" alt="" width={size} height={size} className="block flex-none" />
      <span className={small ? "narrow:hidden" : undefined}>ClutchClips</span>
    </Link>
  );
}

const NAV_LINK = "inline-flex items-center gap-1 rounded-8 border-0 bg-transparent px-4 py-[10px] font-sans text-[14px] font-medium leading-[18px] text-fg-2 transition-colors duration-200 hover:text-fg cursor-pointer";

function useTools() {
  const on = useLanguageSwitches();
  return TOOLS.map((t) => ({ ...t, built: isBuilt(t, on) }));
}

function ToolsMenu() {
  const tools = useTools();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open]);
  return (
    <div ref={box} className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className={`${NAV_LINK} ${open ? "text-fg" : ""}`} aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(!open)}>
        Tools<Icon name="chevron" size={16} className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="absolute left-1/2 top-full z-[60] w-[600px] -translate-x-1/2 pt-2">
        <ul className="m-0 grid list-none grid-cols-2 gap-1 rounded-16 border border-solid border-line bg-card p-2 shadow-pop animate-rise [animation-duration:.2s]">
          {tools.map((t) => {
            const body = <>
              <span className="grid h-9 w-9 flex-none place-items-center rounded-12 bg-[rgba(255,255,255,.06)] text-fg"><Icon name={t.icon} size={18} /></span>
              <span className="grid min-w-0 gap-[2px]">
                <span className="flex items-center gap-2 text-[14px] font-medium text-fg">{t.name}{!t.built && <ComingSoonBadge short />}</span>
                <span className="text-[13px] leading-[1.35] text-fg-2">{t.text}</span>
              </span>
            </>;
            const row = "flex items-start gap-3 rounded-12 p-3";
            return <li key={t.id}>{t.built
              ? <Link href={toolHref(t)} className={`${row} transition-colors hover:bg-[rgba(255,255,255,.05)]`} onClick={() => setOpen(false)}>{body}</Link>
              : <div className={`${row} opacity-70`}>{body}</div>}</li>;
          })}
        </ul>
      </div>}
    </div>
  );
}

export function Nav() {
  const [authed, setAuthed] = useState(false);
  const [open, setOpen] = useState(false);
  const tools = useTools();
  useEffect(() => setAuthed(!!getToken()), []);
  useEffect(() => { document.body.style.overflow = open ? "hidden" : ""; return () => { document.body.style.overflow = ""; }; }, [open]);
  const cta = authed ? { href: "/dashboard/", text: "Open dashboard" } : { href: "/login/?new=1", text: "Start free" };
  return (
    <header className="sticky top-0 z-50">
      {ANNOUNCEMENT && <a href={ANNOUNCEMENT.href} className="flex h-10 items-center justify-center gap-2 bg-[linear-gradient(90deg,#0b0f14,#16202b,#0b0f14)] px-gutter text-center text-[14px] font-medium text-text">
        <span className="truncate">{ANNOUNCEMENT.text}</span><span className="flex-none underline-offset-4 hover:underline">{ANNOUNCEMENT.cta} →</span></a>}
      <div className="flex h-nav items-center justify-between gap-5 bg-[rgba(0,0,0,.82)] px-5 backdrop-blur-md narrow:h-16 narrow:px-gutter">
        <Logo />
        <nav aria-label="Main" className="flex flex-1 items-center justify-center narrow:hidden">
          <ToolsMenu />
          <Link href="/pricing/" className={NAV_LINK}>Pricing</Link>
          <a href={DOCS} className={NAV_LINK}>API</a>
          <Link href="/contact/" className={NAV_LINK}>Contact</Link>
        </nav>
        <div className="flex flex-none items-center gap-2">
          {!authed && <Link href="/login/" className={`${NAV_LINK} narrow:hidden`}>Log in</Link>}
          <Link href={cta.href} className="inline-flex items-center rounded-8 bg-btn px-4 py-[10px] text-[14px] font-medium leading-[18px] text-btn-ink transition-colors hover:bg-btn-hover narrow:hidden">{cta.text}</Link>
          <button type="button" className="hidden h-10 w-10 cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-fg narrow:grid" aria-label={open ? "Close menu" : "Menu"}
            aria-expanded={open} aria-controls="site-menu" onClick={() => setOpen(!open)}><Icon name={open ? "close" : "menu"} size={24} /></button>
        </div>
      </div>
      {open && <div id="site-menu" className="fixed inset-x-0 bottom-0 top-16 z-50 hidden overflow-y-auto bg-bg px-gutter pb-8 pt-2 narrow:block">
        <nav aria-label="Main" className="grid gap-1 border-0 border-b border-solid border-line pb-4" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) setOpen(false); }}>
          <p className="px-1 pb-1 pt-2 text-caption font-medium uppercase tracking-[.04em] text-fg-3">Tools</p>
          {tools.map((t) => t.built
            ? <Link key={t.id} href={toolHref(t)} className="flex min-h-[44px] items-center gap-3 rounded-12 px-1 text-[16px] text-fg"><Icon name={t.icon} size={18} className="text-fg-2" />{t.name}</Link>
            : <div key={t.id} className="flex min-h-[44px] items-center gap-3 px-1 text-[16px] text-fg-2"><Icon name={t.icon} size={18} />{t.name}<ComingSoonBadge short /></div>)}
          <p className="px-1 pb-1 pt-4 text-caption font-medium uppercase tracking-[.04em] text-fg-3">ClutchClips</p>
          <Link href="/pricing/" className="flex min-h-[44px] items-center px-1 text-[16px] text-fg">Pricing</Link>
          <a href={DOCS} className="flex min-h-[44px] items-center px-1 text-[16px] text-fg">API</a>
          <Link href="/contact/" className="flex min-h-[44px] items-center px-1 text-[16px] text-fg">Contact</Link>
        </nav>
        <div className="grid gap-3 pt-5">
          <Link href={cta.href} className="btn btn-primary w-full" onClick={() => setOpen(false)}>{cta.text}</Link>
          {!authed && <Link href="/login/" className="btn btn-ghost w-full" onClick={() => setOpen(false)}>Log in</Link>}
        </div>
      </div>}
    </header>
  );
}

const FOOT_HEAD = "mb-4 text-[14px] font-medium text-text";
const FOOT_LINK = "mb-3 block text-[14px] text-fg-2 transition-colors hover:text-fg";

// `id` lets the sticky start bar step aside over the footer.
export function Footer() {
  return (
    <footer id="site-footer" className="mt-10 border-0 border-t border-solid border-line px-gutter pb-10 pt-16">
      <div className="mx-auto grid max-w-site grid-cols-[2fr_repeat(3,1fr)] gap-8 narrow:grid-cols-2 narrow:gap-y-10">
        <div className="narrow:col-span-2">
          <Logo />
          <p className="mt-4 max-w-[320px] text-[14px] leading-[1.5] text-fg-2">AI clipping for gaming streams. Clip your own streams, or ones you have permission to clip.</p>
        </div>
        <nav aria-label="Product">
          <h3 className={FOOT_HEAD}>Product</h3>
          <Link href="/#features" className={FOOT_LINK}>Features</Link>
          <Link href="/pricing/" className={FOOT_LINK}>Pricing</Link>
          <a href={DOCS} className={FOOT_LINK}>API docs</a>
        </nav>
        <nav aria-label="Company">
          <h3 className={FOOT_HEAD}>Company</h3>
          <Link href="/contact/" className={FOOT_LINK}>Contact</Link>
          <a href="mailto:support@clutchclips.io" className={FOOT_LINK}>support@clutchclips.io</a>
        </nav>
        <nav aria-label="Legal">
          <h3 className={FOOT_HEAD}>Legal</h3>
          <a href="mailto:support@clutchclips.io?subject=Takedown%20request" className={FOOT_LINK}>Takedown requests</a>
        </nav>
      </div>
      <p className="mx-auto mt-12 max-w-site border-0 border-t border-solid border-line pt-6 text-[13px] text-fg-3">© {new Date().getFullYear()} ClutchClips</p>
    </footer>
  );
}
