// The credit ledger as GET /v1/credits returns it: the balance and the latest entries, newest first. Every number
// shown on the credit pages comes from here; nothing is computed from a price list.
export type LedgerRow = { delta: number; kind: string; job_id: string | null; note: string | null; created_at: string };
export type Ledger = { balance: number; history: LedgerRow[] };

// The API returns at most this many entries and has no paging yet.
export const LEDGER_PAGE = 50;

export const KIND_NAMES: Record<string, string> = { grant: "Credits added", topup: "Credits bought", reserve: "Job started",
  release: "Refund", adjust: "Adjustment" };
export const rowName = (r: LedgerRow) => r.note || KIND_NAMES[r.kind] || r.kind;

// "added": credits that came in (grants, purchases, positive adjustments). "used": what jobs took, net of their
// refunds (a job reserves its worst case and releases what it did not use).
export type Side = "all" | "added" | "used";
export const isJob = (r: LedgerRow) => r.kind === "reserve" || r.kind === "release";
export const sideOf = (r: LedgerRow): Exclude<Side, "all"> => (isJob(r) ? "used" : r.delta >= 0 ? "added" : "used");

export function totals(rows: LedgerRow[]) {
  let added = 0, used = 0;
  for (const r of rows) {
    if (isJob(r)) used -= r.delta;
    else if (r.delta >= 0) added += r.delta;
    else used -= r.delta;
  }
  return { added, used: Math.max(0, used) };
}

// Entries grouped by calendar day (local time), newest day first, order inside a day kept.
export function byDay(rows: LedgerRow[]): { day: string; rows: LedgerRow[] }[] {
  const out: { day: string; rows: LedgerRow[] }[] = [];
  for (const r of rows) {
    const d = new Date(r.created_at);
    const day = Number.isNaN(d.getTime()) ? "Unknown date" : d.toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" });
    const last = out[out.length - 1];
    if (last && last.day === day) last.rows.push(r);
    else out.push({ day, rows: [r] });
  }
  return out;
}

// Per-day added/used totals for the account usage chart. Oldest day first so bars read left→right in time.
// Numbers come only from the ledger (`totals` / `byDay`); nothing about views or publish performance.
export type DayUsage = { day: string; added: number; used: number };
export function usageSeries(rows: LedgerRow[]): DayUsage[] {
  return byDay(rows)
    .map(({ day, rows: dayRows }) => ({ day, ...totals(dayRows) }))
    .reverse();
}
