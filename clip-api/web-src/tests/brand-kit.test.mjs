// Brand kit redesign: two-column IA, actions, Coming soon assets, persist via custom templates only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("brand kit page: settings left, live preview right", () => {
  const page = source("app/dashboard/brand-kit/page.tsx");
  assert.match(page, /grid-cols-\[minmax\(0,1fr\)_minmax\(320px,420px\)\]/);
  assert.match(page, /<KitForm /);
  assert.match(page, /aria-label="Preview"/);
  assert.match(page, /mid:order-2/);
  assert.match(page, /mid:order-1/);
});

test("brand kit actions: save, save as, rename, duplicate, delete, set default", () => {
  const page = source("app/dashboard/brand-kit/page.tsx");
  const bar = source("components/dash/brand/KitBar.tsx");
  assert.match(page, />Save as</);
  assert.match(page, /current \? "Save" : "Save kit"/);
  assert.match(bar, />Rename</);
  assert.match(bar, />Duplicate</);
  assert.match(bar, /Set as default/);
  assert.match(bar, /Delete kit/);
  assert.match(page, /duplicateKit\(/);
  assert.match(page, /setDefaultKitId\(/);
  assert.match(page, /deleteKit\(/);
  assert.match(page, /createKit\(/);
  assert.match(page, /updateKit\(/);
});

test("brand kit sections: Basic, Styles, Layout, Additional assets collapsed", () => {
  const form = source("components/dash/brand/Sections.tsx");
  assert.match(form, /title="Basic"/);
  assert.match(form, /title="Styles"/);
  assert.match(form, /title="Layout"/);
  assert.match(form, /title="Additional assets"/);
  assert.match(form, /defaultOpen=\{false\}/);
  assert.match(form, /Kit name/);
  assert.match(form, /Brand colour/);
  assert.match(form, /layoutChoices\(listed, kit\.aspect, kit\.layout\)/);
});

test("brand kit: Coming soon assets never enter kitOptions", () => {
  const form = source("components/dash/brand/Sections.tsx");
  for (const part of ["Logos", "Music"]) assert.match(form, new RegExp(`${part} <span[^>]*>[^<]*</span><ComingSoonBadge />`), part);
  assert.match(form, /A short opener and end card for each shape\.<ComingSoonBadge \/>/);
  assert.match(form, /Overlays <span[^>]*>[^<]*<\/span><ComingSoonBadge \/>/);
  const kit = source("lib/brandkit.ts");
  assert.match(kit, /const out = lookOptions\(kit, listed\);\n\s+if \("hook_style" in listed\) out\.hook_style = kit\.hook_style;/);
  const code = kit.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
  assert.doesNotMatch(code, /max_clips|clip_length|resolution|logo|music|intro|outro/i);
  assert.match(kit, /cc_default_brand_kit/);
});

test("default kit preference is localStorage only; duplicate uses POST create", () => {
  const kit = source("lib/brandkit.ts");
  assert.match(kit, /export const duplicateKit = \(name: string, kit: Kit, listed: Listed\) => createKit\(name, kit, listed\);/);
  assert.match(kit, /localStorage\.setItem\(DEFAULT_KEY/);
  assert.doesNotMatch(kit, /\/v1\/templates\/custom\/.*default/);
});
