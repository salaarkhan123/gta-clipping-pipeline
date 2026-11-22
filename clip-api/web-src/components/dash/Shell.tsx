"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, getToken, setToken } from "@/lib/api";
import { Frame } from "./shell/Frame";
import { PolicyBanner } from "./PolicyBanner";

type Problem = { text: string; upgrade?: boolean } | null;
type Dash = { me: any; reloadMe: () => Promise<void>; fail: (e: unknown) => void; say: (text: string) => void };
// Pages laid out in two columns (a form beside a live preview) get a wider column than the rest.
const WIDE = ["/dashboard/brand-kit"];
const Ctx = createContext<Dash | null>(null);
export const useDash = () => useContext(Ctx)!;

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname() || "";
  const [me, setMe] = useState<any>(null);
  const [error, setError] = useState<Problem>(null), [notice, setNotice] = useState("");
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
  if (!me) return <main className="dash"><p className="muted">Loading…</p></main>;

  return (
    <Ctx.Provider value={{ me, reloadMe, fail, say: setNotice }}>
      <a className="skip" href="#dash-main">Skip to content</a>
      <Frame me={me} path={path} onLogout={() => { setToken(null); router.push("/"); }}>
        <main className={`dash px-11 pb-[72px] pt-3 narrow:px-4 narrow:pb-10 narrow:pt-[18px] ${WIDE.some((w) => path.startsWith(w)) ? "max-w-[1440px]" : ""}`} id="dash-main" tabIndex={-1}>
          {!me.email_verified && <p className="notice">Confirm your email to start making clips. We sent a link to {me.email}.{" "}
            <button className="link" onClick={() => api("/v1/auth/resend-verification", { body: {} }).then(() => setNotice("We sent the link again.")).catch(fail)}>Send it again</button></p>}
          <PolicyBanner />
          {notice && <p className="notice" role="status">{notice} <button className="link" onClick={() => setNotice("")}>Dismiss</button></p>}
          {error && <p className="error" role="alert">{error.text} {error.upgrade && <Link href="/dashboard/pricing/">Get more credits</Link>}{" "}
            <button className="link" onClick={() => setError(null)}>Dismiss</button></p>}
          {children}
        </main>
      </Frame>
    </Ctx.Provider>
  );
}
