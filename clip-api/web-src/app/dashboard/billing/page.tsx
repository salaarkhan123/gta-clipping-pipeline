"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useDash } from "@/components/dash/Shell";
import { BALANCE, PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import { api } from "@/lib/api";
import { tidy } from "@/lib/templates";

const KINDS: Record<string, string> = { grant: "Credits added", topup: "Credits bought", reserve: "Job started", release: "Refund", adjust: "Adjustment" };
const UNPAID = ["past_due", "unpaid"];

export default function Billing() {
  const { me, fail } = useDash();
  const [history, setHistory] = useState<any[] | null>(null);
  useEffect(() => { api("/v1/credits").then((r) => setHistory(r.history)).catch(fail); }, [fail]);
  const portal = () => api("/v1/billing/portal", { body: {} }).then((r) => { window.location.href = r.portal_url; }).catch(fail);
  // Plan ids carry a version ("pro_v2"): shown as the plan's name ("Pro").
  const plan = tidy(String(me.plan).replace(/_v\d+$/, ""));
  // Shown only when the account says so (`subscription_status`, `subscription_cancel_at`); an account without
  // those fields shows nothing.
  const ends = typeof me.subscription_cancel_at === "string" && !Number.isNaN(Date.parse(me.subscription_cancel_at)) ? new Date(me.subscription_cancel_at) : null;

  return (
    <div className="stack">
      <div className={PAGE_HEAD}><h1 className={PAGE_TITLE}>Billing and credits</h1></div>
      {UNPAID.includes(me.subscription_status) && <div className="error bill-note" role="alert">
        <p><strong>Your last payment failed.</strong> Update your payment method to keep your {plan} plan.</p>
        <button className="btn small ghost" onClick={portal}>Manage billing</button>
      </div>}
      {ends && <p className="notice bill-note">Your {plan} plan ends on {ends.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}. You keep it until then.</p>}
      <section className={BALANCE} aria-label="Balance">
        <div>
          <p className="flex items-baseline gap-2 font-display text-[34px] font-bold leading-[normal] tabular-nums text-lime">{me.credits.toLocaleString()}
            <small className="font-body text-[14px] font-medium leading-[normal] text-muted">credits · {plan} plan</small></p>
          <p className="muted small">One credit is one minute of video. A failed or cancelled job is refunded in full.</p>
        </div>
        <div className="row">
          <Link href="/dashboard/pricing/" className="btn small primary">{me.plan === "free" ? "See plans" : "Add credits"}</Link>
          {me.plan !== "free" && <button className="btn small ghost" onClick={portal}>Manage billing</button>}
        </div>
      </section>
      <section>
        <h2>Credit history</h2>
        {history === null ? <p className="muted">Loading…</p> : !history.length ? <p className="muted">Nothing yet.</p>
          : <div className="table-wrap"><table className="ledger">
              <thead><tr><th scope="col">When</th><th scope="col">What</th><th scope="col">Credits</th></tr></thead>
              <tbody>{history.map((h, i) => (
                <tr key={i}><td>{new Date(h.created_at).toLocaleString()}</td><td>{h.note || KINDS[h.kind] || h.kind}</td>
                  <td className={h.delta < 0 ? "minus" : "plus"}>{h.delta > 0 ? `+${h.delta}` : h.delta}</td></tr>))}</tbody>
            </table></div>}
      </section>
    </div>
  );
}
