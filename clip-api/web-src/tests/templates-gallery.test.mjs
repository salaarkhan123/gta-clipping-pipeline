// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const page = readFileSync(new URL("../app/dashboard/templates/page.tsx", import.meta.url), "utf8");
const composer = readFileSync(new URL("../components/dash/StyleComposer.tsx", import.meta.url), "utf8");

test("templates: a preview is only the template's own clip; none is repeated or borrowed", () => {
  assert.match(page, /const footageFor = \(t: any, items: MediaItem\[\]\): MediaItem \| null => items\.find\(\(i\) => i\.id === t\.id \|\| \(i as any\)\.template === t\.id\) \|\| null;/);
  assert.doesNotMatch(page, /norm\(i\.game\)/);                      // no "same game" fallback, which repeated one clip
});

test("templates: clips first, empty cards drawn not blank, one credit line, nothing removed", () => {
  assert.match(page, /sort\(\(a, b\) => Number\(withClip\(b\.t\)\) - Number\(withClip\(a\.t\)\) \|\| a\.i - b\.i\)/);
  assert.match(page, /\{clip \? <Clip t=\{t\} clip=\{clip\} \/> : <Empty t=\{t\} group=\{groupName\(groupOf\(t\)\)\} \/>\}/);
  assert.match(page, /Preview coming soon/);
  assert.doesNotMatch(page, /clip\.credit/);                         // no per-tile creator chip
  assert.match(page, /Preview footage from/);
  assert.doesNotMatch(page, /shown = all\.filter\(\(t\) => [^)]*withClip/);   // a template without a clip still shows
});

test("templates: Gaming category default and Recreate handoff into Clip Maker", () => {
  assert.match(page, /const GAMING = "gaming"/);
  assert.match(page, /useState\(GAMING\)/);
  assert.match(page, />Recreate</);
  assert.match(page, /tool=clips&template=/);
  assert.match(page, /prompt=/);
  assert.match(page, /not copy another creator/);
});

test("style composer: honest disabled chat connectors, real Clip Maker submit", () => {
  assert.match(composer, /Clip with this style/);
  assert.match(composer, /Edit in Claude/);
  assert.match(composer, /ChatGPT plugin/);
  assert.match(composer, /ComingSoonBadge/);
  assert.match(composer, /no chat agent is called/);
  assert.match(composer, /Brand kit/);
  assert.doesNotMatch(composer, /fetch\(|api\(/);                    // no fake connector calls
});
