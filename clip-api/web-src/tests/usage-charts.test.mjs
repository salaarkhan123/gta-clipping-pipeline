// node --test tests/usage-charts.test.mjs  (E1 account usage charts from the credit ledger)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { LEDGER_PAGE, totals, usageSeries } from "../lib/credits.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const sample = [
  { delta: -20, kind: "reserve", job_id: "j1", note: null, created_at: "2026-11-19T14:00:00Z" },
  { delta: 5, kind: "release", job_id: "j1", note: null, created_at: "2026-11-19T14:30:00Z" },
  { delta: 100, kind: "topup", job_id: null, note: null, created_at: "2026-11-18T12:00:00Z" },
  { delta: 50, kind: "grant", job_id: null, note: "Plan", created_at: "2026-11-17T08:00:00Z" },
];

test("usageSeries empty ledger yields no bars", () => {
  assert.deepEqual(usageSeries([]), []);
});

test("usageSeries one day collapses reserves and refunds into net used", () => {
  const oneDay = [
    { delta: -10, kind: "reserve", job_id: "a", note: null, created_at: "2026-11-20T09:00:00Z" },
    { delta: 3, kind: "release", job_id: "a", note: null, created_at: "2026-11-20T09:10:00Z" },
    { delta: 25, kind: "grant", job_id: null, note: null, created_at: "2026-11-20T10:00:00Z" },
  ];
  const series = usageSeries(oneDay);
  assert.equal(series.length, 1);
  assert.deepEqual(series[0], { day: series[0].day, added: 25, used: 7 });
  assert.deepEqual(totals(oneDay), { added: 25, used: 7 });
});

test("usageSeries orders days oldest-first for left-to-right charts", () => {
  const series = usageSeries(sample);
  assert.equal(series.length, 3);
  assert.deepEqual(series.map((d) => ({ added: d.added, used: d.used })), [
    { added: 50, used: 0 },
    { added: 100, used: 0 },
    { added: 0, used: 15 },
  ]);
  // Day labels are local calendar strings; each row has a non-empty day.
  for (const d of series) assert.ok(d.day && d.day.length > 0);
});

test("Analytics, Calendar, and Social accounts nav are wired", () => {
  const nav = source("components/dash/shell/nav.ts");
  assert.match(nav, /label: "Analytics", icon: "chart", href: "\/dashboard\/analytics\/"/);
  assert.match(nav, /label: "Calendar", icon: "calendar", href: "\/dashboard\/calendar\/"/);
  assert.match(nav, /label: "Social accounts", icon: "share", href: "\/dashboard\/social-accounts\/"/);
});

test("analytics page reads only GET /v1/credits and discloses the 50-row window", () => {
  const page = source("app/dashboard/analytics/page.tsx");
  assert.match(page, /api<Ledger>\("\/v1\/credits"\)/);
  assert.match(page, /latest \{LEDGER_PAGE\} ledger entries/);
  assert.equal(LEDGER_PAGE, 50);
  assert.equal((page.match(/api</g) || []).length, 1);
  assert.match(page, /This is not views, virality/);
  assert.doesNotMatch(page, /\/v1\/(social|publish|views|analytics)/);
  assert.doesNotMatch(page, /\b(impressions|engagement|followers)\b/i);
});
