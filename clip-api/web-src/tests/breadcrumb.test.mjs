// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("Breadcrumb: trail of crumbs, last is current page not a link, nav landmark", () => {
  const ui = source("components/dash/ui.tsx");
  assert.match(ui, /export type Crumb = \{ label: string; href\?: string \}/);
  assert.match(ui, /export function Breadcrumb\(\{ crumbs, id \}/);
  assert.match(ui, /<nav aria-label="Breadcrumb"/);
  assert.match(ui, /aria-current="page"/);
  assert.match(ui, /now \? <h1 id=\{id\} title=\{c\.label\} aria-current="page"/);
  assert.doesNotMatch(ui, /now \?[\s\S]{0,80}<Link/);
  assert.match(ui, /overflow-hidden text-ellipsis whitespace-nowrap/);
  assert.match(ui, /tiny:sr-only/);
  assert.doesNotMatch(ui, /OpusClip|opusclip/i);
});

test("BackTitle still accepts title/href/label and folds into Breadcrumb", () => {
  const ui = source("components/dash/ui.tsx");
  assert.match(ui, /export function BackTitle\(\{ title, href = "\/dashboard\/", label = "Back to Home", id, crumbs \}/);
  assert.match(ui, /crumbs\?\.length \? crumbs : \[\{ label: homeLabel\(label\), href \}, \{ label: title \|\| "" \}\]/);
  assert.match(ui, /return <Breadcrumb crumbs=\{trail\} id=\{id\} \/>/);
  assert.match(ui, /function homeLabel\(label: string\) \{\n  return label\.replace\(\/\^Back to \/i, ""\)\.trim\(\) \|\| "Home";/);
});

test("project page trail is Home then the project name", () => {
  const page = source("app/dashboard/project/page.tsx");
  assert.match(page, /crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: project\.filename \}\]\}/);
  assert.match(page, /<BackTitle title=\{project\.filename\}/);
  assert.doesNotMatch(page, /\/dashboard\/projects\//);
});

test("library and templates trail Home then the current page", () => {
  const library = source("app/dashboard/library/page.tsx");
  assert.match(library, /<h1 [^>]*>My projects<\/h1>/);     // a sidebar page: its own title, no trail
  const templates = source("app/dashboard/templates/page.tsx");
  assert.match(templates, /<BackTitle title="Game templates" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Game templates" \}\]\} \/>/);
});

test("remaining dashboard PAGE_TITLE pages trail Home then the current page", () => {
  const brand = source("app/dashboard/brand-kit/page.tsx");
  // Brand kit is a top-level page of the sidebar: its header is the shared PageHeader, without a trail.
  assert.match(brand, /<PageHeader title="Brand kit"/);
  const assets = source("app/dashboard/assets/page.tsx");
  assert.match(assets, /<BackTitle title="Asset library" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Asset library" \}\]\} \/>/);
  const billing = source("app/dashboard/billing/page.tsx");
  assert.match(billing, /<BackTitle title="Billing and credits" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Billing and credits" \}\]\} \/>/);
  const credits = source("app/dashboard/credits/page.tsx");
  assert.match(credits, /<BackTitle title="Credit usage" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Credit usage" \}\]\} \/>/);
  const cases = source("app/dashboard/cases/page.tsx");
  assert.match(cases, /<BackTitle title="Reports about my content" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Reports about my content" \}\]\} \/>/);
  const admin = source("app/dashboard/admin/cases/page.tsx");
  assert.match(admin, /<BackTitle title="Admins only" id="admins-only" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Admins only" \}\]\} \/>/);
  assert.match(admin, /<BackTitle title="Admin: cases" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Admin: cases" \}\]\} \/>/);
  assert.match(admin, /\{ label: "Admin: cases", href: "\/dashboard\/admin\/cases\/" \}/);
  assert.match(admin, /\{ label: c\.reference \}/);
  for (const src of [brand, assets, billing, credits, cases, admin]) {
    assert.doesNotMatch(src, /PAGE_TITLE/);
    assert.doesNotMatch(src, /OpusClip|opusclip/i);
  }
});

test("nested editor and text tools: Home then project then current, existing project route only", () => {
  const editor = source("components/dash/Editor.tsx");
  assert.match(editor, /<Breadcrumb crumbs=\{\[/);
  assert.match(editor, /\{ label: "Home", href: "\/dashboard\/" \}/);
  assert.match(editor, /\{ label: project\.filename, href: `\/dashboard\/project\/\?id=\$\{project\.upload_id\}` \}/);
  assert.match(editor, /\{ label: name \}/);
  const text = source("components/dash/TextTools.tsx");
  assert.match(text, /\{ label: "Home", href: "\/dashboard\/" \}/);
  assert.match(text, /\{ label: project\.filename, href: `\/dashboard\/project\/\?id=\$\{project\.upload_id\}` \}/);
  assert.match(text, /\{ label: NAME\[kind\] \}/);
  assert.match(text, /<BackTitle title=\{NAME\[kind\]\} id=\{title\}/);
});
