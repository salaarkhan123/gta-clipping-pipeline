"use client";
import { useEffect, useState } from "react";
import { AuthDialog } from "@/components/Auth";
import { Footer, Nav } from "@/components/Chrome";
import { api, ApiError, getToken, money } from "@/lib/api";

type Plan = { id: string; name: string; price_month_cents: number; price_year_cents: number; monthly_credits: number;
  max_side: number; max_render_min: number | null };

const INCLUDED = ["Clip Maker, Reframe, Captions and Video Finder", "Automatic camera detection", "9:16, 4:5, 1:1 and 16:9",
  "Five caption styles, SRT and VTT export", "Titles, hashtags and a score for every clip", "API access and the agent skill"];

export default function Pricing() {
  const [plans, setPlans] = useState<Plan[] | null>(null), [packs, setPacks] = useState<any[]>([]);
  const [currency, setCurrency] = useState("usd"), [yearly, setYearly] = useState(false);
  const [current, setCurrent] = useState<string | null>(null);
  const [msg, setMsg] = useState(""), [busy, setBusy] = useState(""), [want, setWant] = useState<(() => void) | null>(null);

  useEffect(() => {
    api("/v1/billing/plans", { auth: false }).then((r) => { setPlans(r.plans); setCurrency(r.currency); })
      .catch((e) => setMsg(e.message));
    api("/v1/billing/packs", { auth: false }).then((r) => setPacks(r.packs)).catch(() => {});
    if (getToken()) api("/v1/me").then((m) => setCurrent(m.plan)).catch(() => {});
    if (new URLSearchParams(window.location.search).get("purchase") === "cancelled") setMsg("Checkout was cancelled. Nothing was charged.");
  }, []);

  async function go(path: string, body: unknown, id: string) {
    if (!getToken()) { setWant(() => () => go(path, body, id)); return; }
    setBusy(id); setMsg("");
    try {
      const r = await api(path, { body });
      window.location.href = r.checkout_url || r.portal_url;
    } catch (e) {
      if (e instanceof ApiError && e.code === "already_subscribed") return go("/v1/billing/portal", {}, id);
      setMsg(e instanceof ApiError && e.code === "billing_unavailable"
        ? "Paid plans open soon. Your free credits work in the meantime." : (e as Error).message);
      setBusy("");
    }
  }

  return (
    <>
      <Nav />
      <main className="pricing">
        <h1>Pay for the minutes you clip</h1>
        <p className="lede">One credit is one minute of video. Each video is charged in full once; more clips from it only cost the minutes rendered.</p>
        <div className="toggle" role="group" aria-label="Billing period">
          <button className={!yearly ? "on" : ""} onClick={() => setYearly(false)}>Monthly</button>
          <button className={yearly ? "on" : ""} onClick={() => setYearly(true)}>Yearly</button>
        </div>
        {msg && <p className="notice" role="status">{msg}</p>}
        {!plans ? <p className="muted">Loading plans…</p> : (
          <div className="plans">
            {plans.map((p) => {
              const paid = p.price_month_cents > 0;
              const perMonth = yearly ? p.price_year_cents / 12 : p.price_month_cents;
              return (
                <article key={p.id} className={`plan ${p.id === "pro" ? "pick" : ""}`}>
                  <h2>{p.name}</h2>
                  <p className="price">{paid ? money(Math.round(perMonth), currency) : money(0, currency)}<span>{paid ? " a month" : ""}</span></p>
                  <p className="muted">{!paid ? "30 credits when you sign up" : yearly
                    ? `${money(p.price_year_cents, currency)} billed yearly. ${(p.monthly_credits * 12).toLocaleString()} credits up front.`
                    : `${p.monthly_credits.toLocaleString()} credits every month`}</p>
                  <ul>
                    <li>{p.max_side >= 1080 ? "1080p" : "720p"} exports</li>
                    <li>Reframe and caption {p.max_render_min ? `up to ${p.max_render_min} minutes` : "videos of any length"} per job</li>
                    {paid && <li>Unused credits roll over</li>}
                  </ul>
                  {current === p.id ? <button className="btn ghost" disabled>Your plan</button>
                    : paid ? <button className="btn primary" disabled={busy === p.id}
                        onClick={() => go("/v1/billing/subscribe", { plan_id: p.id, interval: yearly ? "year" : "month" }, p.id)}>
                        {busy === p.id ? "Opening checkout…" : `Get ${p.name}`}</button>
                    : <a className="btn ghost" href={getToken() ? "/dashboard/" : "/login/?new=1"}>Start free</a>}
                </article>
              );
            })}
          </div>
        )}
        <section className="included">
          <h2>Every plan includes</h2>
          <ul>{INCLUDED.map((x) => <li key={x}>{x}</li>)}</ul>
        </section>
        {packs.length > 0 && (
          <section className="packs">
            <h2>Need a few more credits?</h2>
            <p className="muted">One-time top-ups. They never expire.</p>
            <div>{packs.map((k) => (
              <button key={k.id} className="btn ghost" disabled={busy === k.id} onClick={() => go("/v1/billing/checkout", { pack_id: k.id }, k.id)}>
                {k.credits.toLocaleString()} credits for {money(k.price_cents, currency)}</button>))}</div>
          </section>
        )}
      </main>
      <Footer />
      <AuthDialog open={!!want} onClose={() => setWant(null)} note="Create an account to continue to checkout."
        onDone={() => { const f = want; setWant(null); f?.(); }} />
    </>
  );
}
