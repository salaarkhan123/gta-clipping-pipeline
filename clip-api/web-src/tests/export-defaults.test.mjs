// node --test tests/   (Node 23.6 or later runs the .ts module as it is)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { deadAir } from "../lib/deadair.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("a clip with no saved edit opens with its run's dead air as cuts", () => {
  assert.deepEqual(deadAir([[10, 14], [15.5, 20]], 10, 20), [[14, 15.5]]);
  assert.deepEqual(deadAir([[18, 19], [10, 14], [15.5, 20]], 10, 20), [[14, 15.5]]);     // the flash-forward is left aside
  assert.deepEqual(deadAir([[10, 14], [15.5, 20]], 14.5, 20), [[14.5, 15.5]]);           // only inside the trim
  assert.deepEqual(deadAir([[10, 20]], 10, 20), []);
  assert.deepEqual(deadAir(undefined, 10, 20), []);
  assert.match(source("lib/edit.ts"), /cuts: deadAir\(clip\.segments, trim\.start, trim\.end\)/);
});

test("a save or export keeps the words text-based editing saved; the hook switch reaches the export (#218 review)", () => {
  const edit = source("lib/edit.ts");
  assert.match(edit, /words\?: EditWord\[\] \| null/);                                          // the editor keeps them
  assert.match(edit, /forApi = [\s\S]*?Array\.isArray\(e\.words\) \? \{ words: e\.words \}/);   // and sends them back
  assert.match(source("lib/exporting.ts"), /options = \{ \.\.\.options, hook: options\.hook_overlay \}/);
});

test("new website jobs ask for previews; the export dialogs show the exact price", () => {
  assert.match(source("lib/options.ts"), /export const RENDER = "preview";/);
  assert.match(source("components/dash/setup/JobSetup.tsx"), /render: RENDER/);
  for (const file of ["components/dash/Editor.tsx", "components/dash/BulkEdit.tsx"]) assert.match(source(file), /<QuoteLine [^>]*exact \/>/);
  assert.match(source("components/dash/ClipCard.tsx"), /clip\.rendered !== "full" && <ExportFull/);
});
