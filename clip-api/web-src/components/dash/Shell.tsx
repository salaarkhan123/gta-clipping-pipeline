"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Logo } from "@/components/Chrome";
import { api, ApiError, getToken, setToken } from "@/lib/api";

type Problem = { text: string; upgrade?: boolean } | null;
type Dash = { me: any; reloadMe: () => Promise<void>; fail: (e: unknown) => void; say: (text: string) => void };
const Ctx = createContext<Dash | null>(null);
export const useDash = () => useContext(Ctx)!;

// Sections that are not built yet are listed but not linked: never offer a feature that does not exist.
const SECTIONS: { href?: string; label: string }[] = [
  { href: "/dashboard/", label: "Projects" },
  { href: "/dashboard/library/", label: "Library" },
  { label: "Brand kit" },
  { label: "Publishing" },
  { href: "/dashboard/keys/", label: "API keys" },
  { href: "/dashboard/billing/", label: "Billing" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname() || "";
  const [me, setMe] = useState<any>(null);
  const [error, setError] = useState<Problem>(null), [notice, setNotice] = useState("");
  const [menu, setMenu] = useState(false);

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

  if (!me) return <main className="dash"><p className="muted">Loading…</p></main>;
  const current = (href: string) => (href === "/dashboard/" ? path === "/dashboard/" || path.startsWith("/dashboard/project") : path.startsWith(href));

  return (
    <Ctx.Provider value={{ me, reloadMe, fail, say: setNotice }}>
      <header className="nav dash-nav">
        <div className="dash-brand">
          <button className="burger" aria-label="Menu" aria-expanded={menu} aria-controls="dash-side" onClick={() => setMenu(!menu)}>☰</button>
          <Logo />
        </div>
        <nav aria-label="Account">
          <span className="credits"><b>{me.credits.toLocaleString()}</b> credits</span>
          <Link href="/pricing/" className="btn small primary">{me.plan === "free" ? "Upgrade" : "Add credits"}</Link>
        </nav>
      </header>
      <div className="dash-shell">
        <aside id="dash-side" className={`dash-side ${menu ? "open" : ""}`}>
          <nav aria-label="Dashboard">
            {SECTIONS.map((s) => s.href
              ? <Link key={s.label} href={s.href} aria-current={current(s.href) ? "page" : undefined}>{s.label}</Link>
              : <span key={s.label} className="soon" aria-disabled="true">{s.label} <small>Coming soon</small></span>)}
          </nav>
          <div className="dash-who">
            <p><b>{me.email}</b><br /><span className="muted">{me.plan[0].toUpperCase() + me.plan.slice(1)} plan</span></p>
            <button className="link" onClick={() => { setToken(null); router.push("/"); }}>Log out</button>
          </div>
        </aside>
        <main className="dash">
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
