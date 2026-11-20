"use client";
// Account usage from the credit ledger only: credits added vs used by day. No views, virality, or post-publish metrics.
import Link from "next/link";
import { useEffect, useState } from "react";
import { useDash } from "@/components/dash/Shell";
import { PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import { api } from "@/lib/api";
import { DayUsage, Ledger, LEDGER_PAGE, totals, usageSeries } from "@/lib/credits";

function Stat({ label, value, hint, tone = "text-text" }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className="grid content-start gap-1 rounded-20 border border-solid border-line-soft bg-card p-5">
      <span className="text-[13px] font-medium text-muted">{label}</span>
      <span className={`font-sans text-[28px] font-semibold leading-[1.1] tracking-[-0.02em] tabular-nums ${tone}`}>{value}</span>
      {hint && <span className="text-[12.5px] text-fg-3">{hint}</span>}
    </div>
  );
}

function Bars({ series }: { series: DayUsage[] }) {
  const peak = Math.max(1, ...series.flatMap((d) => [d.added, d.used]));
  return (
    <div className="grid gap-4" role="img" aria-label="Credits added and used by day">
      <div className="flex flex-wrap gap-4 text-[12.5px] text-muted">
        <span className="inline-flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-[3px] bg-lime" aria-hidden="true" />Added</span>
        <span className="inline-flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-[3px] bg-cyan" aria-hidden="true" />Used (after refunds)</span>
      </div>
      <ul className="m-0 grid list-none gap-3 p-0">
        {series.map((d) => (
          <li key={d.day} className="grid gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-muted">{d.day}</span>
              <span className="text-[12.5px] tabular-nums text-fg-3">
                +{d.added.toLocaleString()} added · {d.used.toLocaleString()} used
              </span>
            </div>
            <div className="grid gap-1">
              <div className="h-2 overflow-hidden rounded-pill bg-surface" title={`${d.added} credits added`}>
                <div className="h-full rounded-pill bg-lime" style={{ width: `${(d.added / peak) * 100}%` }} />
              </div>
              <div className="h-2 overflow-hidden rounded-pill bg-surface" title={`${d.used} credits used`}>
                <div className="h-full rounded-pill bg-cyan" style={{ width: `${(d.used / peak) * 100}%` }} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Analytics() {
  const { me, fail } = useDash();
  const [ledger, setLedger] = useState<Ledger | null>(null);
  useEffect(() => { api<Ledger>("/v1/credits").then(setLedger).catch(fail); }, [fail]);
  const rows = ledger?.history || [];
  const sum = totals(rows);
  const series = usageSeries(rows);

  return (
    <div className="grid gap-6">
      <div className={PAGE_HEAD}>
        <div className="grid gap-1">
          <h1 className={PAGE_TITLE}>Account usage</h1>
          <p className="m-0 max-w-[52ch] text-[14px] text-muted">
            Credits spent and refunded from your ledger. This is not views, virality, or how clips performed after you publish them.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/dashboard/credits/" className="btn small ghost">Credit history</Link>
          <Link href="/dashboard/pricing/" className="btn small primary">Add credits</Link>
        </div>
      </div>
      <section aria-label="Summary" className="grid grid-cols-3 gap-3 narrow:grid-cols-1">
        <Stat label="Balance" value={(ledger?.balance ?? me.credits).toLocaleString()} tone="text-lime" />
        <Stat label="Used by jobs" value={ledger ? sum.used.toLocaleString() : "…"} hint={ledger ? "Net of refunds in recent history" : undefined} />
        <Stat label="Added" value={ledger ? sum.added.toLocaleString() : "…"} hint={ledger ? "Grants, purchases and positive adjustments" : undefined} />
      </section>
      <section className="grid gap-3 rounded-20 border border-solid border-line-soft bg-card p-5" aria-labelledby="usage-chart-title">
        <h2 id="usage-chart-title" className="m-0 text-[18px]">Credits by day</h2>
        {!ledger ? <p className="m-0 text-muted">Loading…</p>
          : !series.length ? <p className="m-0 text-muted">No credit activity yet.</p>
          : <Bars series={series} />}
        {ledger && rows.length >= LEDGER_PAGE && (
          <p className="m-0 text-[13px] text-fg-3">Chart uses your latest {LEDGER_PAGE} ledger entries. Older activity is not included yet.</p>
        )}
      </section>
    </div>
  );
}
