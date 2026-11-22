// node --test tests/
// Hook tone chips prefer GET /v1/options catalogue labels when present; title-case ids otherwise.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { hookCatalogueOf, hookToneDescription, hookToneLabel } from "../lib/hookStyles.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const CATALOGUE = [
  { id: "serious", label: "Serious", description: "Straight, no-nonsense wording with no hype." },
  { id: "casual", label: "Casual", description: "Relaxed and everyday, like talking to a friend." },
];

test("hookToneLabel prefers catalogue label when present", () => {
  assert.equal(hookToneLabel("serious", CATALOGUE), "Serious");
  assert.equal(hookToneLabel("casual", CATALOGUE), "Casual");
});

test("hookToneLabel falls back to title-case id when catalogue absent or missing id", () => {
  assert.equal(hookToneLabel("serious"), "Serious");
  assert.equal(hookToneLabel("serious", null), "Serious");
  assert.equal(hookToneLabel("serious", []), "Serious");
  assert.equal(hookToneLabel("hook_tone", undefined), "Hook tone");
  assert.equal(hookToneLabel("unknown_tone", CATALOGUE), "Unknown tone");
});

test("hookToneDescription is only set when catalogue has that id", () => {
  assert.equal(hookToneDescription("serious", CATALOGUE), "Straight, no-nonsense wording with no hype.");
  assert.equal(hookToneDescription("serious", null), undefined);
  assert.equal(hookToneDescription("missing", CATALOGUE), undefined);
});

test("hookCatalogueOf tolerates missing and malformed rows", () => {
  assert.deepEqual(hookCatalogueOf(undefined), []);
  assert.deepEqual(hookCatalogueOf(null), []);
  assert.deepEqual(hookCatalogueOf("nope"), []);
  assert.deepEqual(hookCatalogueOf([{ id: "a" }, { label: "B" }, { id: "c", label: "C", description: "d" }]), [
    { id: "c", label: "C", description: "d" },
  ]);
  assert.deepEqual(hookCatalogueOf(CATALOGUE), CATALOGUE);
});

test("HookTones and brand kit / job setup pass catalogue; Editor uses labels", () => {
  const styles = source("components/dash/setup/Styles.tsx");
  assert.match(styles, /hookToneLabel\(s, entries\)/);
  assert.match(styles, /title=\{tip\}/);
  assert.match(styles, /hookCatalogueOf\(catalogue\)/);
  assert.match(source("components/dash/brand/Pickers.tsx"), /hookCatalogueOf\(listed\.hook_style\?\.catalogue\)/);
  assert.match(source("components/dash/setup/JobSetup.tsx"), /catalogue=\{listed\.hook_style\.catalogue\}/);
  assert.match(source("components/dash/Editor.tsx"), /hookToneLabel\(v, hookCatalogueOf\(listed\.hook_style\.catalogue\)\)/);
});

test("brand kit Logos/Music/Intro stay Coming soon; assets images/audio stay Soon", () => {
  const form = source("components/dash/brand/Sections.tsx");
  for (const part of ["Logos", "Music"]) assert.match(form, new RegExp(`${part} <span[^>]*>[^<]*</span><ComingSoonBadge />`), part);
  assert.match(form, /A short opener and end card for each shape\.<ComingSoonBadge \/>/);
  const assets = source("app/dashboard/assets/page.tsx");
  assert.equal((assets.match(/<ComingSoonBadge/g) || []).length + (assets.match(/<SoonAdd /g) || []).length >= 5, true);     // own list, vocabulary, images, audio
});
