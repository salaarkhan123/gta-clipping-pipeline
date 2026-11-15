"use client";
import { useEffect, useState } from "react";
import { AuthDialog } from "@/components/Auth";
import { Footer, Nav } from "@/components/Chrome";
import { api, ApiError, FREE_CREDITS, getToken, money } from "@/lib/api";

type Plan = { id: string; name: string; price_month_cents: number; price_year_cents: number; monthly_credits: number;
  max_side: number; max_render_min: number | null };

const BLURB: Record<string, string> = {
  free: "Try AI clipping with no commitment.",
  starter: "For new clippers building their first accounts.",
  pro: "For serious clippers running campaigns.",
};
const blurb = (p: Plan) => BLURB[p.id] || "For clipping agencies and teams.";

const INCLUDED = ["AI clip finder and virality score", "Find any moment by speech or what's on screen", "Automatic facecam detection",
  "9:16, 4:5, 1:1 and 16:9", "Five caption styles, SRT and VTT export", "AI titles and hashtags", "API access and the agent skill"];

const FAQ: [string, string][] = [
  ["Can I use ClutchClips for free?", `Yes. Sign up and get ${FREE_CREDITS} free credits, enough for about ${FREE_CREDITS} minutes of video. No credit card required.`],
  ["How do credits work?", "1 credit processes 1 minute of source video. A 2-hour stream uses 120 credits, and you can make as many clips from it as you want. More clips, searches and reframes of the same upload only cost the minutes they render."],
  ["Do unused credits roll over?", "Yes. Credits stay in your account while your plan is active."],
  ["What if a job fails?", "The credits come back to your account automatically."],
  ["Can I cancel anytime?", "Yes. Cancel from your account menu and keep your plan until the end of the period you paid for."],
  ["What payment methods do you accept?", "Cards, Apple Pay and Google Pay through Stripe. Receipts and invoices are in the billing portal."],
];

export default function Pricing() {
  const [plans, setPlans] = useState<Plan[] | null>(null), [packs, setPacks] = useState<any[]>([]);
  const [currency, setCurrency] = useState("usd"), [yearly, setYearly] = useState(true);
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

  // The real yearly discount, worked out from the plans the server returns.
  const paidPlans = (plans || []).filter((p) => p.price_month_cents > 0);
  const save = paidPlans.length ? Math.round(100 * (1 - Math.min(...paidPlans.map((p) => p.price_year_cents / (p.price_month_cents * 12))))) : 0;
  const popular = paidPlans.length >= 2 ? paidPlans[1].id : paidPlans[0]?.id;
  const fmt = (c: number) => money(c, currency).replace(/\.00$/, "");

  return (
    <>
      <Nav />
      <main>
        <header className="page-head">
          <div className="container">
            <span className="pill"><span className="dot" />PRICING</span>
            <h1>Plans for every <span className="grad">clipper</span></h1>
            <p>Start free. Upgrade when you&apos;re ready to clip at scale. 1 credit = 1 minute of source video.</p>
          </div>
        </header>

        <section className="flush">
          <div className="container center">
            <div className="toggle" role="group" aria-label="Billing period">
              <button className={!yearly ? "active" : ""} onClick={() => setYearly(false)}>Monthly</button>
              <button className={yearly ? "active" : ""} onClick={() => setYearly(true)}>Yearly {save > 0 && <span className="save">-{save}%</span>}</button>
            </div>
            {msg && <p className="notice" role="status">{msg}</p>}
            {!plans ? <p className="muted">Loading plans…</p> : (
              <div className="price-grid">
                {plans.map((p) => {
                  const paid = p.price_month_cents > 0;
                  const perMonth = yearly ? p.price_year_cents / 12 : p.price_month_cents;
                  const pop = p.id === popular;
                  return (
                    <article key={p.id} className={`plan ${pop ? "popular" : ""}`}>
                      {pop && <span className="ribbon">Most Popular</span>}
                      <h3>{p.name}</h3>
                      <p className="desc">{blurb(p)}</p>
                      <div className="old">{paid && yearly && perMonth < p.price_month_cents ? fmt(p.price_month_cents) : ""}</div>
                      <div className="price">{fmt(Math.round(perMonth))}<small> / month</small></div>
                      <div className="billed">{!paid ? "Free forever" : yearly ? `Billed ${fmt(p.price_year_cents)} yearly` : "Billed monthly"}</div>
                      {current === p.id ? <button className="btn btn-ghost" disabled>Your plan</button>
                        : paid ? <button className={`btn ${pop ? "btn-primary" : "btn-ghost"}`} disabled={busy === p.id}
                            onClick={() => go("/v1/billing/subscribe", { plan_id: p.id, interval: yearly ? "year" : "month" }, p.id)}>
                            {busy === p.id ? "Opening checkout…" : `Get ${p.name}`}</button>
                        : <a className="btn btn-ghost" href={getToken() ? "/dashboard/" : "/login/?new=1"}>Start Free</a>}
                      <p className="sub">{!paid ? `${FREE_CREDITS} credits when you sign up`
                        : yearly ? `${(p.monthly_credits * 12).toLocaleString()} credits up front` : `${p.monthly_credits.toLocaleString()} credits / month`}</p>
                      <ul>
                        <li>{p.max_side >= 1080 ? "1080p" : "720p"} exports</li>
                        <li>Reframe and caption {p.max_render_min ? `up to ${p.max_render_min >= 60 ? `${p.max_render_min / 60} hr` : `${p.max_render_min} min`}` : "any length"} per job</li>
                        <li>All caption styles</li>
                        {paid && <li>Unused credits roll over</li>}
                        {paid && <li>Priority support</li>}
                      </ul>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {plans && (
          <section className="flush">
            <div className="container">
              <h2 className="section-title">Full feature comparison</h2>
              <p className="section-sub">Every plan gets every tool. Plans differ in credits, export quality and job length.</p>
              <div className="compare-wrap">
                <table className="compare">
                  <thead><tr><th>Feature</th>{plans.map((p) => <th key={p.id}>{p.name}</th>)}</tr></thead>
                  <tbody>
                    <tr className="group"><td colSpan={plans.length + 1}>Usage</td></tr>
                    <tr><td>Credits</td>{plans.map((p) => <td key={p.id}>{p.price_month_cents ? `${p.monthly_credits.toLocaleString()}/mo` : `${FREE_CREDITS} one-time`}</td>)}</tr>
                    <tr><td>Max export quality</td>{plans.map((p) => <td key={p.id}>{p.max_side >= 1080 ? "1080p" : "720p"}</td>)}</tr>
                    <tr><td>Reframe / Captions length per job</td>{plans.map((p) => <td key={p.id}>{p.max_render_min ? `${p.max_render_min} min` : "Unlimited"}</td>)}</tr>
                    <tr><td>File storage</td>{plans.map((p) => <td key={p.id}>7 days</td>)}</tr>
                    <tr className="group"><td colSpan={plans.length + 1}>Tools</td></tr>
                    {INCLUDED.map((f) => <tr key={f}><td>{f}</td>{plans.map((p) => <td key={p.id} className="yes">✓</td>)}</tr>)}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {packs.length > 0 && (
          <section className="flush">
            <div className="container center">
              <h2 className="section-title">Need a few more credits?</h2>
              <p className="section-sub">One-time top-ups. They never expire.</p>
              <div className="packs">{packs.map((k) => (
                <button key={k.id} className="btn btn-ghost" disabled={busy === k.id} onClick={() => go("/v1/billing/checkout", { pack_id: k.id }, k.id)}>
                  {k.credits.toLocaleString()} credits for {money(k.price_cents, currency)}</button>))}</div>
            </div>
          </section>
        )}

        <section className="flush">
          <div className="container">
            <h2 className="section-title">Pricing FAQ</h2>
            <p className="section-sub">Questions about billing and credits.</p>
            <div className="faq">{FAQ.map(([q, a], i) => (<details key={q} open={i === 0}><summary>{q}</summary><p>{a}</p></details>))}</div>
          </div>
        </section>

        <section className="flush">
          <div className="container">
            <div className="cta-band">
              <h2>Get started with the <span className="grad">free plan</span></h2>
              <p>{FREE_CREDITS} free credits · No credit card required</p>
              <a href={getToken() ? "/dashboard/" : "/login/?new=1"} className="btn btn-primary btn-lg">Try for Free</a>
            </div>
          </div>
        </section>
      </main>
      <Footer />
      <AuthDialog open={!!want} onClose={() => setWant(null)} note="Create an account to continue to checkout."
        onDone={() => { const f = want; setWant(null); f?.(); }} />
    </>
  );
}
