"use client";
// The public site's frame (the blur sits on the bar, not the header, so the phone menu can be position: fixed): a slim bar saying what a new account starts with, sticky nav with a Tools menu, footer.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon, IconName } from "@/components/dash/Icon";
import { Badge } from "@/components/ui/Badge";
import { getToken } from "@/lib/api";
import { POLICIES } from "@/lib/legal";
import { useLanguageSwitches } from "@/lib/languages";
import { freeCredits, useSignupCredits } from "@/lib/plans";
import { isBuilt, toolHref, TOOLS } from "@/lib/tools";

const DOCS = "https://api.clutchclips.io/docs";

// The ClutchClips logo everywhere (header, footer, phone menu, app top bar): the mark is app/icon.svg, the same file
// as the favicon, next to the wordmark in Geist. A new logo is a one-file change: replace app/icon.svg.
// `small`: the app's top bar size; the name hides on a phone there.
export function Logo({ small }: { small?: boolean }) {
  const size = small ? 28 : 36;
  return (
    <Link href="/" aria-label="ClutchClips home" className={`flex flex-none items-center font-sans font-semibold tracking-[-0.02em] text-fg ${small ? "gap-2 text-[16px]" : "gap-[11px] text-[21px]"}`}>
      <img src="/icon.svg" alt="" width={size} height={size} className="block flex-none" />
      <span className={small ? "narrow:hidden" : undefined}>ClutchClips</span>
    </Link>
  );
}

const NAV_LINK = "inline-flex h-[46px] items-center gap-[6px] rounded-[10px] border-0 bg-transparent px-[18px] font-sans text-[17px] font-medium leading-none text-fg-2 transition-colors duration-base hover:text-fg cursor-pointer mid:px-3 mid:text-[15px]";

function useTools() {
  const on = useLanguageSwitches();
  return TOOLS.map((t) => ({ ...t, built: isBuilt(t, on) }));
}

// For developers: what the product really has for them today.
const DEV: { icon: IconName; name: string; text: string; href: string; external?: boolean }[] = [
  { icon: "code", name: "API", text: "Every tool on this site as an HTTP API, with the same credits.", href: DOCS, external: true },
  { icon: "key", name: "API keys", text: "Create and revoke keys for your own scripts.", href: "/dashboard/keys/" },
];

// One row of the Tools panel: an icon tile, the name with its tag, one or two lines about it. The whole row is the target.
function MenuItem({ icon, name, text, tag, href, external, onPick }: { icon: IconName; name: string; text: string; tag?: React.ReactNode; href?: string; external?: boolean; onPick: () => void }) {
  const body = <>
    <span className="grid h-12 w-12 flex-none place-items-center rounded-[10px] bg-white/10 text-fg"><Icon name={icon} size={22} /></span>
    <span className="grid min-w-0 gap-[5px] pt-[1px]">
      <span className="flex items-center gap-2 text-[17px] font-semibold leading-[1.2] tracking-[-0.01em] text-fg">{name}{tag}</span>
      <span className="text-[14px] leading-[1.4] text-fg-2">{text}</span>
    </span>
  </>;
  const row = "flex min-h-[86px] items-start gap-4 rounded-[14px] p-[10px] text-left no-underline";
  if (!href) return <div aria-disabled="true" className={`${row} opacity-60`}>{body}</div>;
  const cls = `${row} transition-colors duration-base hover:bg-white/[.07] focus-visible:bg-white/[.07]`;
  return external ? <a href={href} className={cls} onClick={onPick}>{body}</a> : <Link href={href} className={cls} onClick={onPick}>{body}</Link>;
}

// The Tools panel: one wide panel centred under the nav. Its fill is nearly opaque on purpose: the nav bar above it
// already blurs the page, and a blur nested inside another does not reach the page, so the fill alone must hide it. Three columns of tools, then what there is for
// developers behind a divider. Opens on hover and on click; Escape or a click outside closes it.
// The trigger, an invisible bridge over the gap under it, and the panel are one hover region: the menu closes only
// LEAVE_MS after the pointer has left all three, so a diagonal move to a far column does not close it.
const LEAVE_MS = 200;
function ToolsMenu() {
  const tools = useTools();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), leave = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(leave.current), []);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); box.current?.querySelector<HTMLElement>("button")?.focus(); } };
    document.addEventListener("pointerdown", away); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open]);
  const close = () => { clearTimeout(leave.current); setOpen(false); };
  // Built tools first, column by column; the planned ones last.
  const ordered = [...tools.filter((t) => t.built), ...tools.filter((t) => !t.built)];
  const perCol = Math.ceil(ordered.length / 3);
  return (
    <div ref={box} onPointerEnter={() => { clearTimeout(leave.current); setOpen(true); }}
      onPointerLeave={(e) => { if (e.pointerType !== "touch") { clearTimeout(leave.current); leave.current = setTimeout(() => setOpen(false), LEAVE_MS); } }}>
      <span className="relative inline-flex">
        <button type="button" className={`${NAV_LINK} !rounded-full outline-none focus:shadow-none focus-visible:!shadow-[0_0_0_2px_#fff] ${open ? "!bg-[#2c2c2e] !text-fg" : ""}`}
          aria-expanded={open} aria-haspopup="true" aria-controls="tools-panel" onClick={() => { clearTimeout(leave.current); setOpen((o) => !o); }}>
          Tools<Icon name="chevron" size={18} className={`transition-transform duration-base ${open ? "rotate-180" : ""}`} />
        </button>
        {open && <span aria-hidden="true" className="absolute inset-x-[-24px] top-full h-[24px]" />}
      </span>
      {open && <div className="absolute inset-x-0 top-full z-[60] px-6 pt-[6px]">
        <div id="tools-panel" className="mx-auto grid w-[min(1280px,100%)] animate-rise grid-cols-[minmax(0,3fr)_1px_minmax(0,1fr)] gap-x-8 rounded-20 bg-[#2c2c2e] p-[30px] pb-6
          shadow-[inset_0_1px_0_rgba(255,255,255,.1),0_30px_80px_rgba(0,0,0,.6)] [animation-duration:.2s] [backdrop-filter:blur(32px)_saturate(1.3)]">
          <div className="grid content-start gap-4">
            <p className="m-0 px-[10px] text-[17px] font-medium text-fg-2">Tools</p>
            <ul className="m-0 grid list-none grid-flow-col gap-x-6 gap-y-[6px] p-0" style={{ gridTemplateRows: `repeat(${perCol}, auto)`, gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
              {ordered.map((t) => <li key={t.id}><MenuItem icon={t.icon} name={t.name} text={t.text} href={t.built ? toolHref(t) : undefined} onPick={close}
                tag={!t.built ? <Badge tone="soon" /> : t.badge === "new" ? <Badge tone="neutral" className="!bg-white/10">New</Badge> : undefined} /></li>)}
            </ul>
          </div>
          <span aria-hidden="true" className="bg-white/10" />
          <div className="grid content-start gap-4">
            <p className="m-0 px-[10px] text-[17px] font-medium text-fg-2">For developers</p>
            <ul className="m-0 grid list-none gap-3 p-0">
              {DEV.map((d) => <li key={d.name}><MenuItem {...d} onPick={close} /></li>)}
            </ul>
          </div>
        </div>
      </div>}
    </div>
  );
}

export function Nav() {
  const [authed, setAuthed] = useState(false);
  const [open, setOpen] = useState(false);
  const tools = useTools();
  const signup = useSignupCredits();
  useEffect(() => setAuthed(!!getToken()), []);
  useEffect(() => { document.body.style.overflow = open ? "hidden" : ""; return () => { document.body.style.overflow = ""; }; }, [open]);
  const cta = authed ? { href: "/dashboard/", text: "My dashboard" } : { href: "/login/?new=1", text: "Start free" };
  return (
    <header className="sticky top-0 z-50">
      {/* The slim bar above the nav, in the headline pill's lime glow. It says only what is true today: what a new
          account starts with. */}
      <Link href={cta.href} className="flex h-12 items-center justify-center gap-2 px-gutter shadow-[inset_0_-1px_0_var(--glow-line)] [background:var(--glow-fill)] text-center text-[14px] font-medium text-text narrow:h-10 narrow:text-[13px]">
        <span className="truncate">{`New accounts start with ${freeCredits(signup).toLowerCase()}. No card needed.`}</span>
        <span className="flex-none underline-offset-4 hover:underline narrow:hidden">{cta.text} →</span></Link>
      <div className="relative flex h-nav items-center justify-between gap-5 bg-[rgba(0,0,0,.82)] px-8 backdrop-blur-md narrow:h-[60px] narrow:px-gutter">
        <Logo />
        <nav aria-label="Main" className="flex flex-1 items-center justify-center narrow:hidden">
          <ToolsMenu />
          <Link href="/league/" className={NAV_LINK}>Creators League</Link>
          <Link href="/pricing/" className={NAV_LINK}>Pricing</Link>
          <a href={DOCS} className={NAV_LINK}>API</a>
          <Link href="/contact/" className={NAV_LINK}>Contact</Link>
        </nav>
        <div className="flex flex-none items-center gap-2">
          {!authed && <Link href="/login/" className={`${NAV_LINK} narrow:hidden`}>Log in</Link>}
          {authed ? <Link href={cta.href} className={`${NAV_LINK} !text-fg narrow:hidden`}>{cta.text}</Link>
            : <Link href={cta.href} className="btn primary !h-[42px] !rounded-[10px] !px-5 !text-[16px] narrow:hidden">{cta.text}</Link>}
          <button type="button" className="hidden h-10 w-10 cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-fg narrow:grid" aria-label={open ? "Close menu" : "Menu"}
            aria-expanded={open} aria-controls="site-menu" onClick={() => setOpen(!open)}><Icon name={open ? "close" : "menu"} size={24} /></button>
        </div>
      </div>
      {open && <div id="site-menu" className="fixed inset-x-0 bottom-0 top-[100px] z-50 hidden overflow-y-auto bg-bg px-gutter pb-8 pt-2 narrow:block">
        <nav aria-label="Main" className="grid gap-1 border-0 border-b border-solid border-line pb-4" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) setOpen(false); }}>
          <p className="px-1 pb-1 pt-2 text-caption font-medium uppercase tracking-[.04em] text-fg-3">Tools</p>
          {tools.map((t) => t.built
            ? <Link key={t.id} href={toolHref(t)} className="flex min-h-[44px] items-center gap-3 rounded-12 px-1 text-[16px] text-fg"><Icon name={t.icon} size={18} className="text-fg-2" />{t.name}</Link>
            : <div key={t.id} className="flex min-h-[44px] items-center gap-3 px-1 text-[16px] text-fg-2"><Icon name={t.icon} size={18} />{t.name}<ComingSoonBadge short /></div>)}
          <p className="px-1 pb-1 pt-4 text-caption font-medium uppercase tracking-[.04em] text-fg-3">ClutchClips</p>
          <Link href="/league/" className="flex min-h-[44px] items-center px-1 text-[16px] text-fg">Creators League</Link>
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
          <Link href="/league/" className={FOOT_LINK}>Creators League</Link>
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
          {POLICIES.map((p) => <Link key={p.id} href={p.path} className={FOOT_LINK}>{p.title}</Link>)}
          <Link href="/takedown/" className={FOOT_LINK}>Report content</Link>
        </nav>
      </div>
      <p className="mx-auto mt-12 max-w-site border-0 border-t border-solid border-line pt-6 text-[13px] text-fg-2">© {new Date().getFullYear()} ClutchClips</p>
    </footer>
  );
}
