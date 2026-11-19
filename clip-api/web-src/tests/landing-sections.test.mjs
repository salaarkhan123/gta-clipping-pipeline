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

test("the layouts the reframe demo shows are ones the renderer draws, under the app's names", () => {
  const names = { split2: "Split in two", full: "Full", pip: "Picture in picture", screen_first: "Screen first" };
  const built = source("../app/pipeline/layouts.py").match(/^LAYOUTS = \(([^)]+)\)/m)[1];
  const shown = [...source("components/landing/demos/Reframe.tsx").matchAll(/\{ id: "(\w+)", name: "([^"]+)"/g)];
  assert.equal(shown.length, 4);
  for (const [, id, name] of shown) {
    assert.ok(built.includes(`"${id}"`), id);
    assert.equal(name, names[id], id);
  }
});

test("what is not built says Coming soon on the card and offers nothing to click", () => {
  const soon = source("components/landing/demos/Soon.tsx");
  assert.match(soon, /<ComingSoonBadge \/>/);
  assert.doesNotMatch(soon, /<button|<a |href=|onClick/);
  for (const [file, title] of [["sections/WorkflowSection.tsx", "Auto posting"], ["sections/TeamsSection.tsx", "Team workspace"]]) {
    const text = source(`components/landing/${file}`);
    assert.match(text, new RegExp(`title: "${title}", soon: true`), file);
    assert.match(text, /\.soon && <ComingSoonBadge \/>/, file);
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

test("an AI rating is shown only when the AI judge rated the clip", () => {
  const footage = source("components/landing/demos/Footage.tsx");
  assert.match(footage, /export const aiRated = \(item: Item \| null\) => typeof item\?\.rating === "number" && item\.rating_source === "ai";/);
  for (const f of ["demos/VodToClips.tsx", "demos/CaptionStyles.tsx", "demos/Reframe.tsx", "demos/HookText.tsx", "demos/DeadAir.tsx",
    "sections/ModelsSection.tsx", "sections/WorkflowSection.tsx", "sections/EditorSection.tsx", "sections/TeamsSection.tsx"]) {
    for (const line of source(`components/landing/${f}`).split("\n").filter((l) => l.includes("<AiRating"))) assert.match(line, /aiRated\(/, f);
  }
});

test("demo media never plays sound, waits for reduced motion and carries its credit", () => {
  const footage = source("components/landing/demos/Footage.tsx");
  assert.match(footage, /<video[^>]*\bmuted\b/);
  assert.match(footage, /!reduced/);
  assert.match(source("components/landing/demos/demos.module.css"), /prefers-reduced-motion: reduce/);
});

test("each card that shows footage names every creator it shows, once, at the bottom", () => {
  const footage = source("components/landing/demos/Footage.tsx");
  assert.doesNotMatch(footage, /item\.credit &&/);                  // no credit chip on a frame
  assert.match(footage, /export function Credits\(\{ items/);
  // Every item a card plays is in its Credits line.
  const cards = {
    "demos/VodToClips.tsx": /<Credits items=\{\[vod, wide\?\.item, \.\.\.tall\]\}/,
    "demos/CaptionStyles.tsx": /<Credits items=\{\[plain\]\} \/>/,
    "demos/Reframe.tsx": /<Credits items=\{items\} \/>/,
    "demos/HookText.tsx": /<Credits items=\{\[real\]\} \/>/,
    "sections/EditorSection.tsx": /<Credits items=\{\[clip\]\}/,
  };
  for (const [f, credits] of Object.entries(cards)) {
    const text = source(`components/landing/${f}`);
    assert.match(text, credits, f);
    const plays = [...text.matchAll(/<Footage section="[\w-]+" item=\{([\w.?]+)\}/g)].map((m) => m[1]);
    assert.ok(plays.length > 0, f);
  }
  // Files with no Credits line play no footage.
  for (const f of ["demos/DeadAir.tsx", "sections/ModelsSection.tsx", "sections/WorkflowSection.tsx", "sections/TeamsSection.tsx"])
    assert.doesNotMatch(source(`components/landing/${f}`), /<Footage /, f);
});

test("the caption presets follow the clip's real words with the renderer's line rules", () => {
  const demo = source("components/landing/demos/CaptionStyles.tsx"), cap = source("components/landing/demos/Caption.tsx");
  const py = source("../app/pipeline/captions.py");
  for (const name of ["PAUSE", "IMPACT_SHORT"]) {
    const ours = cap.match(new RegExp(`${name} = ([\\d.]+)`))[1], theirs = py.match(new RegExp(`^${name} = ([\\d.]+)`, "m"))[1];
    assert.equal(Number(ours), Number(theirs), name);
  }
  assert.match(demo, /wordAt\(said, v\.currentTime\)/);            // timed by the playing clip
  assert.match(demo, /"No captions"/);
  assert.match(demo, /Font <ComingSoonBadge short \/>/);           // the app has no font or effect choice yet
  assert.match(demo, /Effects <ComingSoonBadge short \/>/);
});
