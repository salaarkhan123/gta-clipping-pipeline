"use client";
import { useEffect, useState } from "react";
import { AuthDialog } from "@/components/Auth";
import { Footer, Nav } from "@/components/Chrome";
import { exportName, INCLUDED, PeriodToggle, Plan, PlanCards, yearlySaving } from "@/components/PricingPlans";
import { api, ApiError, getToken, money } from "@/lib/api";
import { freeCredits } from "@/lib/plans";

const faq = (signup: number | null): [string, string][] => [
  ["Can I use ClutchClips for free?", signup === null ? "Yes. Sign up and get free credits. No credit card required."
    : `Yes. Sign up and get ${signup} free credits, enough for about ${signup} minutes of video. No credit card required.`],
  ["How do credits work?", "1 credit processes 1 minute of source video. A 2-hour stream uses 120 credits, and you can make as many clips from it as you want. More clips, searches and reframes of the same upload only cost the minutes they render."],
  ["Do credits expire?", "No. Credits don't expire: what you don't use stays in your account."],
  ["What if a job fails?", "The credits come back to your account automatically."],
  ["Can I cancel anytime?", "Yes. Cancel from your account menu and keep your plan until the end of the period you paid for."],
  ["What payment methods do you accept?", "Cards, Apple Pay and Google Pay through Stripe. Receipts and invoices are in the billing portal."],
];

export default function Pricing() {
  const [plans, setPlans] = useState<Plan[] | null>(null), [packs, setPacks] = useState<any[]>([]);
  const [currency, setCurrency] = useState("usd"), [yearly, setYearly] = useState(true);
  const [current, setCurrent] = useState<string | null>(null);
  const signup = plans?.find((p) => p.price_month_cents === 0)?.signup_credits ?? null;
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

  const save = yearlySaving(plans || []);

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
            <PeriodToggle yearly={yearly} onChange={setYearly} save={save} />
            {msg && <p className="notice" role="status">{msg}</p>}
            {!plans ? <p className="muted">Loading plans…</p>
              : <PlanCards plans={plans} currency={currency} yearly={yearly} current={current} busy={busy} freeHref={getToken() ? "/dashboard/" : "/login/?new=1"}
                  onPick={(p) => go("/v1/billing/subscribe", { plan_id: p.id, interval: yearly ? "year" : "month" }, p.id)} />}
            <p className="muted small mt-5 text-center">Plans renew until you cancel. By subscribing or buying credits you agree to the{" "}
              <a href="/terms/#credits" className="text-lime underline">Terms of Service</a> and the <a href="/refunds/" className="text-lime underline">Refund Policy</a>.</p>
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
                    <tr><td>Credits</td>{plans.map((p) => <td key={p.id}>{p.price_month_cents ? `${p.monthly_credits.toLocaleString()}/mo` : p.signup_credits === undefined ? "On sign-up" : `${p.signup_credits} on sign-up`}</td>)}</tr>
                    <tr><td>Max export quality</td>{plans.map((p) => <td key={p.id}>{exportName(p.max_side)}</td>)}</tr>
                    <tr><td>Reframe / Captions length per job</td>{plans.map((p) => <td key={p.id}>{p.max_render_min ? `${p.max_render_min} min` : "Unlimited"}</td>)}</tr>
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
            <div className="faq">{faq(signup).map(([q, a], i) => (<details key={q} open={i === 0}><summary>{q}</summary><p>{a}</p></details>))}</div>
          </div>
        </section>

        <section className="flush">
          <div className="container">
            <div className="cta-band">
              <h2>Get started with the <span className="grad">free plan</span></h2>
              <p>{freeCredits(signup)} · No credit card required</p>
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
