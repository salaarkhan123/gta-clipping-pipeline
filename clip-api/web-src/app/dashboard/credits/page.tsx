"use client";
// Credit usage history: the balance and every recent ledger entry from GET /v1/credits, by day.
import Link from "next/link";
import { useEffect, useState } from "react";
import { Icon, IconName } from "@/components/dash/Icon";
import { useDash } from "@/components/dash/Shell";
import { Tabs } from "@/components/dash/Tabs";
import { BackTitle, PAGE_HEAD } from "@/components/dash/ui";
import { StatCard } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { api } from "@/lib/api";
import { byDay, Ledger, LEDGER_PAGE, LedgerRow, rowName, Side, sideOf, totals } from "@/lib/credits";

const ICONS: Record<string, IconName> = { grant: "sparkle", topup: "card", reserve: "scissors", release: "undo", adjust: "sliders" };

function Entry({ r }: { r: LedgerRow }) {
  const t = new Date(r.created_at);
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <span className="grid h-9 w-9 flex-none place-items-center rounded-12 bg-control text-fg-2" aria-hidden="true"><Icon name={ICONS[r.kind] || "bolt"} size={18} /></span>
      <span className="grid min-w-0 flex-1 gap-[2px]">
        <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[14.5px] font-medium text-text">{rowName(r)}</span>
        <span className="flex flex-wrap gap-x-2 text-[12.5px] text-muted">
          {!Number.isNaN(t.getTime()) && <time dateTime={r.created_at}>{t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</time>}
          {r.job_id && <span className="font-mono text-fg-3" title={`Job ${r.job_id}`}>{r.job_id}</span>}
        </span>
      </span>
      <b className={`font-sans text-[15px] font-semibold tabular-nums ${r.delta > 0 ? "text-lime" : "text-text"}`}>{r.delta > 0 ? `+${r.delta.toLocaleString()}` : r.delta.toLocaleString()}</b>
    </li>
  );
}

export default function Credits() {
  const { me, fail } = useDash();
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [side, setSide] = useState<Side>("all");
  useEffect(() => { api<Ledger>("/v1/credits").then(setLedger).catch(fail); }, [fail]);
  const rows = ledger?.history || [];
  const shown = side === "all" ? rows : rows.filter((r) => sideOf(r) === side);
  const sum = totals(rows);

  return (
    <div className="grid gap-6">
      <div className={PAGE_HEAD}>
        <div className="grid gap-1">
          <BackTitle title="Credit usage" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Credit usage" }]} />
          <p className="m-0 text-[14px] text-muted">One credit is one minute of video. A failed or cancelled job is refunded in full.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/dashboard/analytics/" className="btn small ghost">Usage charts</Link>
          <Link href="/dashboard/billing/" className="btn small ghost">Subscription</Link>
          <Link href="/dashboard/pricing/" className="btn small primary">Add credits</Link>
        </div>
      </div>
      <section aria-label="Summary" className="grid grid-cols-3 gap-3 narrow:grid-cols-1">
        <StatCard label="Balance" value={(ledger?.balance ?? me.credits).toLocaleString()} tone="text-lime" />
        <StatCard label="Used by jobs" value={ledger ? sum.used.toLocaleString() : "…"} hint={ledger ? "In the entries below, after refunds" : undefined} />
        <StatCard label="Added" value={ledger ? sum.added.toLocaleString() : "…"} hint={ledger ? "Plan credits, purchases and grants below" : undefined} />
      </section>
      <section className="grid gap-3" aria-labelledby="history-title">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="history-title" className="m-0 text-[16px] font-semibold">History</h2>
          <Tabs seg label="Show" panel="history" value={side} onChange={setSide} tabs={[["all", "All"], ["used", "Used"], ["added", "Added"]]} />
        </div>
        <div id="history" role="tabpanel">
          {!ledger ? <p className="muted">Loading…</p>
            : !shown.length ? <EmptyState icon="bolt" title={rows.length ? "Nothing of this kind in your recent history" : "No credit activity yet"} />
            : <div className="grid gap-5">{byDay(shown).map((g) => (
                <div key={g.day} className="grid gap-2">
                  <h3 className="m-0 text-[13px] font-medium text-muted">{g.day}</h3>
                  <ul className="m-0 list-none divide-x-0 divide-y divide-solid divide-line-soft overflow-hidden rounded-16 bg-card p-0">
                    {g.rows.map((r, i) => <Entry key={`${r.created_at}-${i}`} r={r} />)}</ul>
                </div>))}
              </div>}
          {ledger && rows.length >= LEDGER_PAGE && <p className="mt-4 text-[13px] text-fg-3">Showing your latest {LEDGER_PAGE} entries.</p>}
        </div>
      </section>
    </div>
  );
}
