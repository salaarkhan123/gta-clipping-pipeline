"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PeriodToggle, Plan, PlanCards, yearlySaving } from "@/components/PricingPlans";
import { useDash } from "@/components/dash/Shell";
import { BALANCE } from "@/components/dash/ui";
import { api, ApiError, money } from "@/lib/api";

// Pricing inside the app: the same plans and packs as the public page, from the server's plan config.
export default function AppPricing() {
  const { me, fail } = useDash();
  const [plans, setPlans] = useState<Plan[] | null>(null), [packs, setPacks] = useState<any[]>([]);
  const [currency, setCurrency] = useState("usd"), [yearly, setYearly] = useState(true);
  const [busy, setBusy] = useState(""), [msg, setMsg] = useState("");

  useEffect(() => {
    api("/v1/billing/plans", { auth: false }).then((r) => { setPlans(r.plans); setCurrency(r.currency); }).catch(fail);
    api("/v1/billing/packs", { auth: false }).then((r) => setPacks(r.packs)).catch(() => {});
  }, [fail]);

  async function go(path: string, body: unknown, id: string) {
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
    <div className="wide mx-auto grid w-full max-w-[1160px] gap-7">
      <header className="mb-10 grid justify-items-center gap-3 text-center">
        <h1 className="text-[26px]">Pick a plan</h1>
        <p className="muted">1 credit processes 1 minute of source video. A failed or cancelled job gives its credits back.
          {" "}You have <b>{me.credits.toLocaleString()}</b> credits. <Link href="/dashboard/billing/">Credit history</Link></p>
        {plans && <PeriodToggle yearly={yearly} onChange={setYearly} save={yearlySaving(plans)} />}
      </header>
      {msg && <p className="notice" role="status">{msg}</p>}
      {!plans ? <p className="muted">Loading plans…</p>
        : <PlanCards plans={plans} currency={currency} yearly={yearly} current={me.plan} busy={busy} freeHref="/dashboard/"
            onPick={(p) => go("/v1/billing/subscribe", { plan_id: p.id, interval: yearly ? "year" : "month" }, p.id)} />}
      {packs.length > 0 && <section className={BALANCE} aria-labelledby="packs-title">
        <div><h2 id="packs-title">Need a few more credits?</h2><p className="muted small">One-time top-ups. They never expire.</p></div>
        <div className="row">{packs.map((k) => (
          <button key={k.id} className="btn small ghost" disabled={busy === k.id} onClick={() => go("/v1/billing/checkout", { pack_id: k.id }, k.id)}>
            {k.credits.toLocaleString()} credits for {money(k.price_cents, currency)}</button>))}</div>
      </section>}
    </div>
  );
}
