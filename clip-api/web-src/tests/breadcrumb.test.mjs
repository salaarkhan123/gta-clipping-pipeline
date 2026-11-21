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
  assert.match(library, /<BackTitle title="Library" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Library" \}\]\} \/>/);
  const templates = source("app/dashboard/templates/page.tsx");
  assert.match(templates, /<BackTitle title="Game templates" crumbs=\{\[\{ label: "Home", href: "\/dashboard\/" \}, \{ label: "Game templates" \}\]\} \/>/);
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
