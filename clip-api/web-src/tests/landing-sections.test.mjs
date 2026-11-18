// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("../", import.meta.url));
const source = (path) => readFileSync(join(web, path), "utf8");

test("the landing shows exactly the caption styles the renderer draws", () => {
  const api = source("../app/render_options.py").match(/CaptionStyle = Literal\[([^\]]+)\]/)[1];
  const renderer = [...api.matchAll(/"(\w+)"/g)].map((m) => m[1]);
  const shown = [...source("components/landing/demos/Caption.tsx").matchAll(/\{ id: "(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(shown, renderer);
});

test("the layouts the reframe demo names are ones the renderer draws", () => {
  const names = { "Split in two": "split2", Full: "full", "Picture in picture": "pip", "Screen first": "screen_first" };
  const built = source("../app/pipeline/layouts.py").match(/^LAYOUTS = \(([^)]+)\)/m)[1];
  const shown = [...source("components/landing/demos/Reframe.tsx").matchAll(/\{ name: "([^"]+)"/g)].map((m) => m[1]);
  assert.ok(shown.length > 0);
  for (const n of shown) assert.ok(names[n] && built.includes(`"${names[n]}"`), n);
});

test("what is not built says Coming soon on the card and offers nothing to click", () => {
  const soon = source("components/landing/demos/Soon.tsx");
  assert.match(soon, /<ComingSoon \/>/);
  assert.doesNotMatch(soon, /<button|<a |href=|onClick/);
  for (const [file, title] of [["sections/WorkflowSection.tsx", "Auto posting"], ["sections/TeamsSection.tsx", "Team workspace"]]) {
    const text = source(`components/landing/${file}`);
    assert.match(text, new RegExp(`title: "${title}", soon: true`), file);
    assert.match(text, /\.soon && <ComingSoon \/>/, file);
    assert.doesNotMatch(text, /<button|href=|onClick/, file);
  }
  const carousel = source("components/landing/sections/DemoCarousel.tsx");
  for (const id of ["broll", "voice"]) assert.match(carousel, new RegExp(`id: "${id}",[^}]*soon: true`), id);
});

test("future features are written in the future tense", () => {
  const soon = source("components/landing/demos/Soon.tsx");
  for (const m of soon.matchAll(/text="([^"]+)"/g)) assert.match(m[1], /\bwill\b/, m[1]);
  assert.match(source("components/landing/sections/WorkflowSection.tsx"), /ClutchClips will post/);
  assert.match(source("components/landing/sections/TeamsSection.tsx"), /will be able to share/);
});

test("demo media never plays sound and waits for reduced motion", () => {
  const frames = source("components/landing/demos/Frames.tsx");
  assert.match(frames, /<video[^>]* muted /);
  assert.match(frames, /!reduced/);
  assert.match(source("components/landing/demos/demos.module.css"), /prefers-reduced-motion: reduce/);
});
