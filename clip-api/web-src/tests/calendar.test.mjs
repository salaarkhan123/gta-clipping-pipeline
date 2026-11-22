// Social schedule / calendar surface (wired to #266 publish APIs).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const publish = source("lib/publish.ts");

test("calendar page: week/month/list, status chips, schedule composer, honest disabled state", () => {
  const page = source("app/dashboard/calendar/page.tsx");
  assert.match(page, /Social schedule/);
  assert.match(page, /PageHeader/);
  assert.match(page, /\["week", "Week"\], \["month", "Month"\], \["list", "List"\]/);
  assert.match(page, /CalendarEmpty/);
  assert.match(page, /ScheduleComposer/);
  assert.match(page, /CalendarBoard/);
  assert.match(page, /StatusChip/);
  assert.match(page, /loadPosts/);
  assert.match(page, /\/v1\/posts\/\$\{id\}\/cancel/);
  assert.match(page, /\/v1\/posts\/\$\{id\}\/retry/);
  assert.match(page, /Schedule clip/);
  assert.match(page, /never a fake success/);
});

test("calendar empty: sample gaming schedule + tips, labeled Example only", () => {
  const empty = source("components/publish/CalendarEmpty.tsx");
  assert.match(empty, /SAMPLE_SCHEDULE/);
  assert.match(empty, /SCHEDULE_TIPS/);
  assert.match(empty, /Example only/);
  assert.match(empty, /Sample week for a gaming creator/);
  assert.match(empty, /Publishing is not enabled yet/);
  assert.match(empty, /mode === "disabled"/);
  assert.match(publish, /id: "sample-1"/);
  assert.match(publish, /Space GTA and ranked clips/);
  assert.doesNotMatch(empty, /SAMPLE_SCHEDULE\.map[\s\S]*loadPosts/);
});

test("schedule composer: create via publish API, edit via PATCH, export_url gate", () => {
  const form = source("components/publish/ScheduleComposer.tsx");
  assert.match(form, /\/v1\/clips\/\$\{clipId\}\/publish\/check/);
  assert.match(form, /\/v1\/clips\/\$\{clipId\}\/publish/);
  assert.match(form, /\/v1\/posts\/\$\{editing\.id\}/);
  assert.match(form, /method: "PATCH"/);
  assert.match(form, /export_url/);
  assert.match(form, /rights_confirmed/);
  assert.match(form, /Idempotency-Key/);
  assert.doesNotMatch(form, /PUBLISHING\s*=\s*true/);
});

test("calendar board: week and month grids + list cards", () => {
  const board = source("components/publish/CalendarBoard.tsx");
  assert.match(board, /view === "week"/);
  assert.match(board, /monthGrid/);
  assert.match(board, /postsOnDay/);
  assert.match(board, /can_edit/);
  assert.match(board, /can_cancel/);
  assert.match(board, /can_retry/);
});

test("publish helpers: status tones, weekStart Monday-first, sample ids", () => {
  assert.match(publish, /STATUS_TONE: Record<PostStatus, string>/);
  assert.match(publish, /SCHEDULED: "border-\[rgba\(60,240,255/);
  assert.match(publish, /PUBLISHED: "border-\[rgba\(184,255,60/);
  assert.match(publish, /FAILED: "border-\[rgba\(255,92,122/);
  assert.match(publish, /Monday-first week/);
  assert.match(publish, /const dow = \(day\.getDay\(\) \+ 6\) % 7/);
  assert.match(publish, /Array\.from\(\{ length: 42 \}/);
  assert.match(publish, /id: "sample-1"/);
  assert.match(publish, /id: "sample-4"/);
  // Behavioral: Monday-first week containing Sunday 2026-11-22 is Mon 16.
  const startOfLocalDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const weekStart = (anchor) => {
    const day = startOfLocalDay(anchor);
    const dow = (day.getDay() + 6) % 7;
    return addDays(day, -dow);
  };
  const mon = weekStart(new Date(2026, 10, 22));
  assert.equal(mon.getDay(), 1);
  assert.equal(mon.getDate(), 16);
});

test("status chip uses STATUS_TONE", () => {
  const chip = source("components/publish/StatusChip.tsx");
  assert.match(chip, /STATUS_TONE/);
  assert.match(chip, /STATUS_LABEL/);
});

test("social accounts: honest disabled copy while PUBLISHING is off", () => {
  const page = source("app/dashboard/social-accounts/page.tsx");
  assert.match(page, /PageHeader/);
  assert.match(page, /EmptyState/);
  assert.match(page, /Publishing is not enabled yet/);
  assert.match(page, /Access tokens never appear/);
  assert.match(page, /no fake connected accounts/);
});
