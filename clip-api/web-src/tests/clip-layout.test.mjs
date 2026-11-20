// Grid vs list layout toggle (Library clips). Preference is this-browser only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { CLIP_LAYOUT_KEY, parseClipLayout } from "../lib/clip-layout.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("clip layout: only list is list; anything else is grid", () => {
  assert.equal(parseClipLayout("list"), "list");
  assert.equal(parseClipLayout("grid"), "grid");
  assert.equal(parseClipLayout(null), "grid");
  assert.equal(parseClipLayout(""), "grid");
  assert.equal(parseClipLayout("cards"), "grid");
  assert.equal(CLIP_LAYOUT_KEY, "clutchclips.clipLayout");
});

test("clip layout: toggle is icon buttons with aria-pressed and aria-label, keyboard reachable", () => {
  const card = source("components/dash/ClipCard.tsx");
  assert.match(card, /export function LayoutToggle/);
  assert.match(card, /aria-label="Clip layout"/);
  assert.match(card, /aria-pressed=\{value === mode\}/);
  assert.match(card, /aria-label=\{label\}/);
  assert.match(card, /\["grid", "Grid layout"\], \["list", "List layout"\]/);
  assert.match(card, /type="button"/);
  assert.match(card, /<Icon name=\{mode\}/);
  assert.match(source("components/dash/Icon.tsx"), /list: <>/);
});

test("clip layout: preference is localStorage only, default grid so SSR matches first paint", () => {
  const card = source("components/dash/ClipCard.tsx");
  assert.match(card, /useState<ClipLayout>\("grid"\)/);
  assert.match(card, /localStorage\.getItem\(CLIP_LAYOUT_KEY\)/);
  assert.match(card, /localStorage\.setItem\(CLIP_LAYOUT_KEY, v\)/);
  assert.doesNotMatch(card, /\/v1\/.*layout/);
  assert.doesNotMatch(source("app/dashboard/library/page.tsx"), /\/v1\/.*layout/);
  assert.doesNotMatch(source("components/clips/Results.tsx"), /\/v1\/.*layout/);
});

test("clip layout: grid keeps CLIP_GRID cards; list is a compact row that reuses ScoreBadge and Play", () => {
  const card = source("components/dash/ClipCard.tsx");
  assert.match(card, /export const CLIP_GRID = CARD_ROW/);
  assert.match(card, /export const CLIP_LIST/);
  assert.match(card, /if \(layout === "list"\)/);
  assert.match(card, /<ScoreBadge clip=\{clip\} \/>/);
  assert.match(card, /aria-label=\{`Play \$\{name\}`\}/);
  assert.match(card, /\{project && <span className="truncate text-\[12\.5px\] text-muted">\{project\.name\}<\/span>\}/);
  assert.match(card, /\{clock\(length\)\}/);
  assert.doesNotMatch(card, /display_score \* 100|virality probability|% viral/i);
});

test("library clips: toggle sits with the toolbar and drives the same ClipCard grid or list", () => {
  const page = source("app/dashboard/library/page.tsx");
  assert.match(page, /useClipLayout/);
  assert.match(page, /<LayoutToggle value=\{layout\} onChange=\{setLayout\} \/>/);
  assert.match(page, /layout === "list" \? CLIP_LIST : CLIP_GRID/);
  assert.match(page, /layout=\{layout\}/);
  assert.match(page, /<ProjectGrid projects=\{projects\} \/>/);
  assert.doesNotMatch(page, /ProjectGrid[^>]*layout/);
});

test("project results: same LayoutToggle and key; grid keeps ClipTile GRID[shape]; list is CLIP_LIST rows that still open the player", () => {
  const results = source("components/clips/Results.tsx");
  const tile = source("components/clips/ClipTile.tsx");
  const bar = source("components/clips/ResultsBar.tsx");
  assert.match(results, /useClipLayout/);
  assert.match(results, /<LayoutToggle value=\{layout\} onChange=\{setLayout\} \/>/);
  assert.match(bar, /\{children\}/);
  assert.match(results, /layout === "list" \? CLIP_LIST : GRID\[shape\]/);
  assert.match(results, /layout=\{layout\}/);
  assert.match(results, /onOpen=\{\(\) => setPlaying\(c\.id\)\}/);
  assert.match(tile, /layout = "grid"/);
  assert.match(tile, /if \(layout === "list"\)/);
  assert.match(tile, /<RatingBadge clip=\{clip\} \/>/);
  assert.match(tile, /aria-label=\{`Play \$\{name\}`\}/);
  assert.match(tile, /\{clock\(length\)\}/);
  assert.doesNotMatch(tile, /display_score \* 100|virality probability|% viral/i);
  assert.doesNotMatch(results, /clutchclips\.clipLayout/);
});
