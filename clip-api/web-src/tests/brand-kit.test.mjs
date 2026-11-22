// Brand kit redesign: two-column IA, actions, Coming soon assets, persist via custom templates only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("brand kit page: settings in a 640 px column, the live preview beside it (under it on a narrow window)", () => {
  const page = source("app/dashboard/brand-kit/page.tsx");
  assert.match(page, /grid-cols-\[minmax\(0,640px\)_minmax\(340px,1fr\)\]/);     // the measured 640 px settings column
  assert.match(page, /wide:grid-cols-\[minmax\(0,720px\)\]/);
  assert.match(page, /<KitForm /);
  assert.match(page, /aria-label="Preview"/);
  assert.ok(page.indexOf("<KitForm ") < page.indexOf('aria-label="Preview"'));    // the preview comes after the cards
});

test("brand kit actions: save, save as, rename, duplicate, delete, set default", () => {
  const page = source("app/dashboard/brand-kit/page.tsx");
  const bar = source("components/dash/brand/KitBar.tsx");
  assert.match(page, />Save as new kit</);
  assert.match(page, /current \? "Save changes" : "Save kit"/);
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

test("brand kit sections: compact rows whose choices open in pickers", () => {
  const form = source("components/dash/brand/Sections.tsx"), pickers = source("components/dash/brand/Pickers.tsx");
  for (const title of ["Basic", "Styles", "Layout", "Editing", "Intro & outro", "Media"]) assert.match(form, new RegExp(`title="${title}"`), title);
  assert.match(form, /<CaptionRow /);
  assert.match(form, /<HookRow /);
  assert.match(form, /<LayoutRows /);
  assert.match(form, /<More>/);
  assert.match(form, /Brand colour/);
  assert.doesNotMatch(form, /CaptionStyles|HookTones/);                // no always-open strips of tiles
  assert.match(pickers, /layoutChoices\(listed, a, used \? kit\.layout : "auto"\)/);
  assert.match(pickers, /<Dropdown label=\{`\$\{title\} style`\} kind="dialog"/);
  assert.match(pickers, />Reset<\/button>/);
  assert.match(pickers, />Save as new<\/button>/);
  // Layout pictures and the preview are the engine's own renders, listed by the kit-preview manifest.
  assert.match(pickers, /useMedia\("kit-preview"\)/);
  assert.match(source("components/dash/brand/KitPreview.tsx"), /kitPreviewId\(shape, kit\.layout, kit\.camera\)/);
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
