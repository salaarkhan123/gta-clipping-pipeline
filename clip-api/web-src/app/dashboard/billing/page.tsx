"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useDash } from "@/components/dash/Shell";
import { api } from "@/lib/api";

const KINDS: Record<string, string> = { grant: "Credits added", topup: "Credits bought", reserve: "Job started", release: "Refund", adjust: "Adjustment" };

export default function Billing() {
  const { me, fail } = useDash();
  const [history, setHistory] = useState<any[] | null>(null);
  useEffect(() => { api("/v1/credits").then((r) => setHistory(r.history)).catch(fail); }, [fail]);

  return (
    <>
      <h1 className="dash-title">Billing</h1>
      <section className="panel">
        <p><span className="credits"><b>{me.credits.toLocaleString()}</b> credits</span> · {me.plan[0].toUpperCase() + me.plan.slice(1)} plan</p>
        <p className="muted">One credit is one minute of video. A failed or cancelled job is refunded in full.</p>
        <div className="row">
          <Link href="/pricing/" className="btn small primary">{me.plan === "free" ? "See plans" : "Add credits"}</Link>
          {me.plan !== "free" && <button className="btn small ghost" onClick={() => api("/v1/billing/portal", { body: {} })
            .then((r) => { window.location.href = r.portal_url; }).catch(fail)}>Manage billing</button>}
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
    </>
  );
}
