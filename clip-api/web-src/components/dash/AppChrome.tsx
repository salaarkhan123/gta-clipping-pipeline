"use client";
// The app's frame: the icon rail on the left (a tab bar along the bottom on a phone) and the top bar.
// Styles: app/app-shell.css (`.rail`, `.topbar`, `.menu`).
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

export function Rail({ path }: { path: string }) {
  return (
    <nav className="rail" aria-label="App">
      <ul>
        {SECTIONS.map((s) => (
          <li key={s.label} className={s.href ? "" : "rail-soon"}>
            {s.href
              ? <Link href={s.href} aria-current={isHere(path, s.href, s.under) ? "page" : undefined}><Icon name={s.icon} size={20} /><span>{s.label}</span></Link>
              : <span aria-disabled="true" title={`${s.label}: coming soon`}><Icon name={s.icon} size={20} /><span>{s.label}</span><small>Soon</small></span>}
          </li>))}
      </ul>
    </nav>
  );
}

// A button that opens a small panel under it. Escape or a click elsewhere closes it; focus goes back to the button.
function Menu({ label, button, className = "", children }: { label: string; button: React.ReactNode; className?: string; children: React.ReactNode }) {
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
    <div ref={box} className={`menu ${className}`}>
      <button ref={btn} type="button" className="menu-btn" aria-label={label} aria-expanded={open} onClick={() => setOpen(!open)}>{button}</button>
      {open && <div className="menu-pop" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) setOpen(false); }}>{children}</div>}
    </div>
  );
}

export function TopBar({ me, onLogout }: { me: any; onLogout: () => void }) {
  const on = useLanguageSwitches();
  const plan = me.plan[0].toUpperCase() + me.plan.slice(1);
  return (
    <header className="topbar">
      <Logo />
      <nav className="topbar-right" aria-label="Account">
        <Menu label="Language" className="wide-only" button={<><Icon name="globe" size={18} />English<Icon name="chevron" size={16} /></>}>
          <p className="menu-item on"><Icon name="check" size={16} />English</p>
          <p className="muted small menu-note">The app is in English for now. Other languages are coming. Captions follow the language spoken in your video.</p>
        </Menu>
        <Menu label="Tools" className="wide-only" button={<>Tools<Icon name="chevron" size={16} /></>}>
          <ul className="menu-list">
            {TOOLS.map((t) => (
              <li key={t.id}>{isBuilt(t, on)
                ? <Link className="menu-item" href={toolHref(t)}><Icon name={t.icon} size={18} />{t.name}</Link>
                : <span className="menu-item soon" aria-disabled="true"><Icon name={t.icon} size={18} />{t.name}<small className="soon-tag">Soon</small></span>}</li>))}
          </ul>
        </Menu>
        <a className="topbar-link wide-only" href={`${API}/docs`} target="_blank" rel="noreferrer">API</a>
        <Link className="credit-pill" href="/dashboard/billing/" title="Your credits. One credit is one minute of video.">
          <Icon name="bolt" size={16} /><b>{me.credits.toLocaleString()}</b><span className="sr-only"> credits</span></Link>
        <Link href="/dashboard/pricing/" className="btn small primary">{me.plan === "free" ? "Upgrade" : "Add credits"}</Link>
        <Menu label="Account" className="account-menu-wrap" button={<span className="avatar" aria-hidden="true">{(me.email[0] || "?").toUpperCase()}</span>}>
          <p className="menu-who"><b title={me.email}>{me.email}</b><span className="muted">{plan} plan · {me.credits.toLocaleString()} credits</span></p>
          <Link className="menu-item" href="/dashboard/billing/"><Icon name="card" size={18} />Billing and credits</Link>
          <Link className="menu-item" href="/dashboard/keys/"><Icon name="code" size={18} />API keys</Link>
          <a className="menu-item narrow-only" href={`${API}/docs`} target="_blank" rel="noreferrer"><Icon name="external" size={18} />API docs</a>
          <button type="button" className="menu-item" onClick={onLogout}><Icon name="logout" size={18} />Log out</button>
        </Menu>
      </nav>
    </header>
  );
}
