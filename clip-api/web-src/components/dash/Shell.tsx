"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Logo } from "@/components/Chrome";
import { API, api, ApiError, getToken, setToken } from "@/lib/api";
import { Icon, IconName, Soon } from "./Icon";

type Problem = { text: string; upgrade?: boolean } | null;
type Dash = { me: any; reloadMe: () => Promise<void>; fail: (e: unknown) => void; say: (text: string) => void };
const Ctx = createContext<Dash | null>(null);
export const useDash = () => useContext(Ctx)!;

// Sections that are not built yet are listed but not linked: never offer a feature that does not exist.
// `under` lists the routes that light the item up (a project and the template gallery belong to Home).
const SECTIONS: { href?: string; label: string; icon: IconName; under?: string[] }[] = [
  { href: "/dashboard/", label: "Home", icon: "home", under: ["/dashboard/project", "/dashboard/templates"] },
  { href: "/dashboard/library/", label: "Library", icon: "library" },
  { label: "Scheduler", icon: "calendar" },
  { label: "Brand kit", icon: "brand" },
  { href: "/pricing/", label: "Pricing", icon: "tag" },
  { href: "/dashboard/keys/", label: "API", icon: "code" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname() || "";
  const [me, setMe] = useState<any>(null);
  const [error, setError] = useState<Problem>(null), [notice, setNotice] = useState("");
  const [menu, setMenu] = useState(false);
  const burger = useRef<HTMLButtonElement>(null), side = useRef<HTMLElement>(null);

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) { router.push("/login/"); return; }
    setError({ text: e instanceof Error ? e.message : "Something went wrong.", upgrade: e instanceof ApiError && e.code === "insufficient_credits" });
  }, [router]);
  const reloadMe = useCallback(async () => { try { setMe(await api("/v1/me")); } catch (e) { fail(e); } }, [fail]);

  useEffect(() => {
    if (!getToken()) { router.push("/login/"); return; }
    if (new URLSearchParams(window.location.search).get("purchase") === "success")
      setNotice("Payment received. New credits show up here within a minute.");
    reloadMe();
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setMenu(false); }, [path]);
  // The drawer (small screens): focus moves into it, Escape closes it and hands focus back to the menu button.
  useEffect(() => {
    if (!menu) return;
    side.current?.querySelector<HTMLElement>("a")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setMenu(false); burger.current?.focus(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu]);

  if (!me) return <main className="dash"><p className="muted">Loading…</p></main>;
  const current = (href: string, under: string[] = []) => path === href || (href !== "/dashboard/" && path.startsWith(href)) || under.some((u) => path.startsWith(u));

  return (
    <Ctx.Provider value={{ me, reloadMe, fail, say: setNotice }}>
      <a className="skip" href="#dash-main">Skip to content</a>
      <header className="nav dash-nav">
        <div className="dash-brand">
          <button ref={burger} className="burger" aria-label="Menu" aria-expanded={menu} aria-controls="dash-side" onClick={() => setMenu(!menu)}>
            <Icon name={menu ? "close" : "menu"} size={24} /></button>
          <Logo />
        </div>
        <nav aria-label="Account">
          <span className="credits"><b>{me.credits.toLocaleString()}</b> credits</span>
          <Link href="/pricing/" className="btn small primary">{me.plan === "free" ? "Upgrade" : "Add credits"}</Link>
        </nav>
      </header>
      <div className="dash-shell">
        {menu && <div className="dash-scrim" onClick={() => setMenu(false)} />}
        <aside id="dash-side" ref={side} className={`dash-side ${menu ? "open" : ""}`}>
          <nav aria-label="Dashboard">
            <ul>
              {SECTIONS.map((s) => (
                <li key={s.label}>
                  {s.href
                    ? <Link href={s.href} aria-current={current(s.href, s.under) ? "page" : undefined}><Icon name={s.icon} />{s.label}</Link>
                    : <span className="soon" aria-disabled="true"><Icon name={s.icon} />{s.label} <Soon /></span>}
                  {s.label === "API" && <a className="sub" href={`${API}/docs`} target="_blank" rel="noreferrer">API docs <Icon name="external" size={14} /></a>}
                </li>))}
            </ul>
          </nav>
          <div className="dash-who">
            <p><b>{me.email}</b><br /><span className="muted">{me.plan[0].toUpperCase() + me.plan.slice(1)} plan</span></p>
            <Link href="/dashboard/billing/" aria-current={current("/dashboard/billing/") ? "page" : undefined}><Icon name="card" size={18} />Billing</Link>
            <button onClick={() => { setToken(null); router.push("/"); }}><Icon name="logout" size={18} />Log out</button>
          </div>
        </aside>
        <main className="dash" id="dash-main" tabIndex={-1}>
          {!me.email_verified && <p className="notice">Confirm your email to start making clips. We sent a link to {me.email}.{" "}
            <button className="link" onClick={() => api("/v1/auth/resend-verification", { body: {} }).then(() => setNotice("We sent the link again.")).catch(fail)}>Send it again</button></p>}
          {notice && <p className="notice" role="status">{notice} <button className="link" onClick={() => setNotice("")}>Dismiss</button></p>}
          {error && <p className="error" role="alert">{error.text} {error.upgrade && <Link href="/pricing/">Get more credits</Link>}{" "}
            <button className="link" onClick={() => setError(null)}>Dismiss</button></p>}
          {children}
        </main>
      </div>
    </Ctx.Provider>
  );
}
