// node --test tests/  (dashboard shell, brand kit, asset library, credit usage)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { byDay, sideOf, totals, usageSeries } from "../lib/credits.ts";
import { change, HISTORY_MAX, redo, startHistory, undo } from "../lib/history.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("sidebar: every built page is a link, every planned one is Coming soon and never a link", () => {
  const nav = source("components/dash/shell/nav.ts");
  for (const [label, href] of [["Home", "/dashboard/"], ["Projects", "/dashboard/library/"], ["Brand kit", "/dashboard/brand-kit/"],
    ["Asset library", "/dashboard/assets/"], ["Templates", "/dashboard/templates/"], ["Analytics", "/dashboard/analytics/"],
    ["Calendar", "/dashboard/calendar/"], ["Social accounts", "/dashboard/social-accounts/"],
    ["API access", "/dashboard/keys/"]]) {
    assert.match(nav, new RegExp(`label: "${label}", icon: "[a-zA-Z]+", href: "${href.replace(/\//g, "\\/")}"`), label);
  }
  for (const label of ["Labs", "Learning centre"]) {
    assert.match(nav, new RegExp(`\\{ label: "${label}", icon: "[a-zA-Z]+" \\}`), label);
  }
  const side = source("components/dash/shell/Sidebar.tsx");
  // An item without href renders a span with the shared badge, not a Link.
  assert.match(side, /if \(!item\.href\) return \([\s\S]*?<span aria-disabled="true"[\s\S]*?<ComingSoonBadge short \/>/);
});

test("top bar: credits come from the account, Add credits goes to pricing, the bell is Coming soon", () => {
  const bar = source("components/dash/shell/TopBar.tsx");
  assert.match(bar, /Number\(me\.credits\)\.toLocaleString\(\)/);
  assert.match(bar, /href="\/dashboard\/pricing\/"[^>]*>Add credits</);
  assert.match(bar, /title="Notifications: coming soon"[\s\S]{0,200}<ComingSoonBadge short \/>/);
  assert.match(bar, /onFind/);
  assert.match(bar, /Find moments/);
});

test("global Find: Cmd+K / Ctrl+K opens the shell palette that hits search and find", () => {
  const frame = source("components/dash/shell/Frame.tsx");
  assert.match(frame, /isFindShortcut/);
  assert.match(frame, /<GlobalFind open=\{findOpen\}/);
  assert.match(frame, /onFind=\{\(\) => setFindOpen\(true\)\}/);
  const find = source("components/dash/shell/GlobalFind.tsx");
  assert.match(find, /searchPath\(uploadId, q\)/);
  assert.match(find, /api\("\/v1\/find"/);
  assert.match(find, /not_transcribed/);
  assert.match(find, /findProjectHref/);
  const panel = source("components/dash/FindPanel.tsx");
  assert.match(panel, /handoffQuery/);
  assert.match(panel, /findHandoffFromSearch/);
  const project = source("app/dashboard/project/page.tsx");
  assert.match(project, /useSearchParams/);
  assert.match(project, /applyFindHandoff/);
  assert.match(project, /handoffQuery=\{findQuery\}/);
});

test("account menu: subscription, credit usage, remove imports, language, API keys, log out", () => {
  const menu = source("components/dash/shell/AccountMenu.tsx");
  assert.match(menu, /<Row href="\/dashboard\/billing\/" icon="card">Subscription<\/Row>/);
  assert.match(menu, /<Row href="\/dashboard\/credits\/" icon="bolt">Credit usage history<\/Row>/);
  assert.match(menu, /<Row href="\/dashboard\/cases\/#remove-imports" icon="shield">Remove my imports<\/Row>/);
  assert.match(menu, /<Row href="\/dashboard\/keys\/" icon="key">API keys<\/Row>/);
  assert.match(menu, /Language<span[^>]*>English<\/span><ComingSoonBadge short \/>/);
  assert.match(menu, /onClick=\{onLogout\}/);
});

test("phone: the shell has no bottom tab bar, so sticky page bars sit on the screen's edge", () => {
  assert.match(source("components/dash/shell/Frame.tsx"), /"--app-bottom-bar": "0px"/);
});

test("brand kit: planned parts are Coming soon and send nothing; saving sends only the look", () => {
  const form = source("components/dash/brand/Sections.tsx");
  for (const part of ["Logos", "Music"]) assert.match(form, new RegExp(`${part} <span[^>]*>[^<]*</span><ComingSoonBadge />`), part);
  assert.match(form, /A short opener and end card for each shape\.<ComingSoonBadge \/>/);
  assert.match(form, /title="Additional assets"/);
  const kit = source("lib/brandkit.ts");
  // Nothing priced is ever in a kit: the options come from the look keys plus the hook tone.
  assert.match(kit, /const out = lookOptions\(kit, listed\);\n\s+if \("hook_style" in listed\) out\.hook_style = kit\.hook_style;/);
  const code = kit.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
  assert.doesNotMatch(code, /max_clips|clip_length|resolution|logo|music|intro|outro/i);
});

test("undo and redo: change clears redo, undo then redo returns to the same value, history is capped", () => {
  let h = startHistory({ style: "impact", hook: true });
  h = change(h, { style: "pop" });
  h = change(h, { hook: false });
  assert.deepEqual(h.now, { style: "pop", hook: false });
  h = undo(h);
  assert.deepEqual(h.now, { style: "pop", hook: true });
  h = undo(h);
  assert.deepEqual(h.now, { style: "impact", hook: true });
  assert.equal(undo(h), h);                         // nothing left to undo
  h = redo(redo(h));
  assert.deepEqual(h.now, { style: "pop", hook: false });
  h = change(undo(h), { style: "neon" });
  assert.equal(h.future.length, 0);                 // a new change drops what was undone
  let long = startHistory({ n: 0 });
  for (let i = 1; i <= HISTORY_MAX + 10; i++) long = change(long, { n: i });
  assert.equal(long.past.length, HISTORY_MAX);
});

test("credit usage: jobs count as used net of refunds, grants and purchases as added", () => {
  const rows = [
    { delta: -12, kind: "reserve", job_id: "job_1", note: null, created_at: "2026-11-18T10:00:00Z" },
    { delta: 4, kind: "release", job_id: "job_1", note: null, created_at: "2026-11-18T10:05:00Z" },
    { delta: 500, kind: "topup", job_id: null, note: null, created_at: "2026-11-17T09:00:00Z" },
    { delta: 30, kind: "grant", job_id: null, note: "Free signup credits", created_at: "2026-11-16T09:00:00Z" },
    { delta: -5, kind: "adjust", job_id: null, note: null, created_at: "2026-11-16T08:00:00Z" },
  ];
  assert.deepEqual(totals(rows), { added: 530, used: 13 });
  assert.equal(sideOf(rows[1]), "used");             // a refund belongs to the job's side
  assert.equal(sideOf(rows[2]), "added");
  assert.equal(sideOf(rows[4]), "used");
  assert.equal(byDay(rows).length, 3);
  assert.equal(byDay(rows)[0].rows.length, 2);
});

test("usageSeries: oldest day first with per-day added and used from the ledger", () => {
  const rows = [
    { delta: -12, kind: "reserve", job_id: "job_1", note: null, created_at: "2026-11-18T10:00:00Z" },
    { delta: 4, kind: "release", job_id: "job_1", note: null, created_at: "2026-11-18T10:05:00Z" },
    { delta: 500, kind: "topup", job_id: null, note: null, created_at: "2026-11-17T09:00:00Z" },
    { delta: 30, kind: "grant", job_id: null, note: "Free signup credits", created_at: "2026-11-16T09:00:00Z" },
    { delta: -5, kind: "adjust", job_id: null, note: null, created_at: "2026-11-16T08:00:00Z" },
  ];
  const series = usageSeries(rows);
  assert.equal(series.length, 3);
  // Chronological: 16th → 17th → 18th (local calendar labels from byDay).
  assert.deepEqual(series.map((d) => [d.added, d.used]), [[30, 5], [500, 0], [0, 8]]);
  assert.deepEqual(usageSeries([]), []);
});

test("credit usage and assets: numbers only from the API", () => {
  const credits = source("app/dashboard/credits/page.tsx");
  assert.match(credits, /api<Ledger>\("\/v1\/credits"\)/);
  assert.match(credits, /href="\/dashboard\/analytics\/"/);
  const assets = source("app/dashboard/assets/page.tsx");
  assert.match(assets, /api<\{ projects: Video\[\] \}>\(`\/v1\/projects\?limit=\$\{PAGE\}&offset=\$\{from\}`\)/);
  // Storage, own censor list, vocabulary, fonts, images and audio are planned.
  assert.equal((assets.match(/<ComingSoonBadge/g) || []).length + (assets.match(/<SoonAdd /g) || []).length >= 6, true);
});

test("analytics page: ledger charts only, honest copy, no publish metrics", () => {
  const page = source("app/dashboard/analytics/page.tsx");
  assert.match(page, /api<Ledger>\("\/v1\/credits"\)/);
  assert.match(page, /usageSeries/);
  assert.match(page, /LEDGER_PAGE/);
  assert.match(page, /Credits spent and refunded from your ledger/);
  assert.match(page, /not views, virality, or how clips performed after you publish/);
  assert.doesNotMatch(page, /\/v1\/(social|publish|analytics|views)/i);
  assert.doesNotMatch(page, /\b(impressions|engagement|followers)\b/i);
});
