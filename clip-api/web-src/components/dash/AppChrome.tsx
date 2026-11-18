"use client";
// The app's frame: the icon rail on the left (a tab bar along the bottom on a phone) and the top bar. Tailwind
// utilities; tokens in tailwind.config.ts.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Logo } from "@/components/Chrome";
import { API } from "@/lib/api";
import { useLanguageSwitches } from "@/lib/languages";
import { isBuilt, toolHref, TOOLS } from "@/lib/tools";
import { Icon, IconName } from "./Icon";

// Sections that are not built yet are listed but never linked. `under` lists the routes that light an item up.
const SECTIONS: { href?: string; label: string; icon: IconName; under?: string[] }[] = [
  { href: "/dashboard/", label: "Home", icon: "home", under: ["/dashboard/project", "/dashboard/templates"] },
  { href: "/dashboard/library/", label: "Library", icon: "library" },
  { label: "Scheduler", icon: "calendar" },
  { label: "Brand kit", icon: "brand" },
  { href: "/dashboard/pricing/", label: "Pricing", icon: "tag", under: ["/dashboard/billing"] },
  { href: "/dashboard/keys/", label: "API", icon: "code" },
];

const isHere = (path: string, href: string, under: string[] = []) =>
  path === href || (href !== "/dashboard/" && path.startsWith(href)) || under.some((u) => path.startsWith(u));

const RAIL_ITEM = "grid justify-items-center gap-1 rounded-12 px-[2px] pb-2 pt-[9px] text-center font-body text-[11.5px] font-medium leading-[1.15] narrow:pb-[6px] narrow:pt-[7px]";

// The frame around every signed-in page: `main` is the page's own column.
export function AppBody({ path, children }: { path: string; children: React.ReactNode }) {
  return (
    <div className="min-h-[calc(100vh-theme(spacing.topbar))] pl-rail narrow:pb-[calc(theme(spacing.tabbar)+env(safe-area-inset-bottom))] narrow:pl-0">
      <Rail path={path} />
      {children}
    </div>
  );
}

function Rail({ path }: { path: string }) {
  return (
    <nav aria-label="App" className="fixed bottom-0 left-0 top-topbar z-40 w-rail overflow-y-auto border-0 border-r border-solid border-line-soft bg-bg px-2 py-3
      narrow:right-0 narrow:top-auto narrow:h-[calc(theme(spacing.tabbar)+env(safe-area-inset-bottom))] narrow:w-auto narrow:overflow-visible narrow:border-r-0 narrow:border-t
      narrow:px-[6px] narrow:pb-[env(safe-area-inset-bottom)] narrow:pt-[6px]">
      <ul className="grid list-none gap-[6px] narrow:auto-cols-fr narrow:grid-flow-col narrow:gap-1">
        {SECTIONS.map((s) => (
          <li key={s.label} className={s.href ? "" : "narrow:hidden"}>
            {s.href
              ? <Link href={s.href} aria-current={isHere(path, s.href, s.under) ? "page" : undefined}
                  className={`group ${RAIL_ITEM} text-muted hover:bg-card hover:text-text aria-[current=page]:bg-chip aria-[current=page]:text-text`}>
                  <Icon name={s.icon} size={20} className="group-aria-[current=page]:text-lime" /><span>{s.label}</span></Link>
              : <span aria-disabled="true" title={`${s.label}: coming soon`} className={`${RAIL_ITEM} cursor-default text-muted`}>
                  <Icon name={s.icon} size={20} /><span>{s.label}</span>
                  <small className="font-body text-[9px] font-semibold uppercase leading-[normal] tracking-[.04em] text-dim">Soon</small></span>}
          </li>))}
      </ul>
    </nav>
  );
}

const BAR_BUTTON = "inline-flex h-9 cursor-pointer items-center gap-[6px] rounded-8 border-0 bg-transparent font-body text-[14px] font-medium leading-[normal] text-label hover:bg-chip hover:text-text";
const MENU_ITEM = "flex min-h-[38px] w-full cursor-pointer items-center gap-[10px] rounded-8 border-0 bg-transparent px-[10px] py-[6px] text-left font-body text-[14px] font-medium leading-[normal] text-text";

// A button that opens a small panel under it. Escape or a click elsewhere closes it; focus goes back to the button.
function Menu({ label, button, className = "", buttonClass = "px-[10px]", children }: { label: string; button: React.ReactNode; className?: string; buttonClass?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open]);
  return (
    <div ref={box} className={`relative ${className}`}>
      <button ref={btn} type="button" className={`${BAR_BUTTON} aria-expanded:bg-chip aria-expanded:text-text ${buttonClass}`} aria-label={label} aria-expanded={open} onClick={() => setOpen(!open)}>{button}</button>
      {open && <div className="absolute right-0 top-[calc(100%+8px)] z-[60] grid min-w-[240px] gap-[2px] rounded-12 border border-solid border-line bg-card-2 p-2 shadow-[0_24px_48px_rgba(0,0,0,.55)]"
        onClick={(e) => { if ((e.target as HTMLElement).closest("a")) setOpen(false); }}>{children}</div>}
    </div>
  );
}

export function TopBar({ me, onLogout }: { me: any; onLogout: () => void }) {
  const on = useLanguageSwitches();
  const plan = me.plan[0].toUpperCase() + me.plan.slice(1);
  return (
    <header className="sticky top-0 z-50 flex h-topbar items-center justify-between gap-4 border-0 border-b border-solid border-line-soft bg-[rgba(7,8,10,.92)] pl-[18px] pr-4 [backdrop-filter:blur(12px)]
      narrow:gap-2 narrow:pl-[14px] narrow:pr-[10px]">
      <Logo small />
      <nav className="flex items-center gap-[6px] narrow:gap-1" aria-label="Account">
        <Menu label="Language" className="narrow:hidden" button={<><Icon name="globe" size={18} />English<Icon name="chevron" size={16} /></>}>
          <p className={MENU_ITEM}><Icon name="check" size={16} className="text-lime" />English</p>
          <p className="muted small max-w-[240px] px-[10px] pb-[6px] pt-1">The app is in English for now. Other languages are coming. Captions follow the language spoken in your video.</p>
        </Menu>
        <Menu label="Tools" className="narrow:hidden" button={<>Tools<Icon name="chevron" size={16} /></>}>
          <ul className="grid list-none gap-[2px]">
            {TOOLS.map((t) => (
              <li key={t.id}>{isBuilt(t, on)
                ? <Link className={`${MENU_ITEM} hover:bg-chip-hover`} href={toolHref(t)}><Icon name={t.icon} size={18} className="text-muted" />{t.name}</Link>
                : <span className={`${MENU_ITEM} cursor-default text-muted`} aria-disabled="true"><Icon name={t.icon} size={18} className="text-muted" />{t.name}
                    <small className="soon-tag ml-auto">Soon</small></span>}</li>))}
          </ul>
        </Menu>
        <a className={`${BAR_BUTTON} px-[10px] narrow:hidden`} href={`${API}/docs`} target="_blank" rel="noreferrer">API</a>
        <Link className="ml-[6px] inline-flex h-8 items-center gap-[5px] rounded-full bg-chip px-3 tabular-nums text-lime hover:bg-chip-hover narrow:ml-0" href="/dashboard/billing/"
          title="Your credits. One credit is one minute of video.">
          <Icon name="bolt" size={16} /><b className="font-body text-[14px] font-semibold leading-[normal] text-text">{me.credits.toLocaleString()}</b><span className="sr-only"> credits</span></Link>
        <Link href="/dashboard/pricing/" className="btn small primary px-[14px] py-[7px] shadow-none narrow:min-h-[40px]">{me.plan === "free" ? "Upgrade" : "Add credits"}</Link>
        <Menu label="Account" buttonClass="px-[4px]" button={<span className="grid h-8 w-8 place-items-center rounded-full bg-[linear-gradient(135deg,theme(colors.lime),theme(colors.cyan))] font-display text-[14px] font-bold leading-[normal] text-ink" aria-hidden="true">
          {(me.email[0] || "?").toUpperCase()}</span>}>
          <p className="mb-1 grid gap-[2px] border-0 border-b border-solid border-line px-[10px] pb-[10px] pt-[6px] text-[13px] [overflow-wrap:anywhere]">
            <b title={me.email}>{me.email}</b><span className="muted">{plan} plan · {me.credits.toLocaleString()} credits</span></p>
          <Link className={`${MENU_ITEM} hover:bg-chip-hover`} href="/dashboard/billing/"><Icon name="card" size={18} className="text-muted" />Billing and credits</Link>
          <Link className={`${MENU_ITEM} hover:bg-chip-hover`} href="/dashboard/keys/"><Icon name="code" size={18} className="text-muted" />API keys</Link>
          <a className={`${MENU_ITEM} hidden hover:bg-chip-hover narrow:flex`} href={`${API}/docs`} target="_blank" rel="noreferrer"><Icon name="external" size={18} className="text-muted" />API docs</a>
          <button type="button" className={`${MENU_ITEM} hover:bg-chip-hover`} onClick={onLogout}><Icon name="logout" size={18} className="text-muted" />Log out</button>
        </Menu>
      </nav>
    </header>
  );
}
