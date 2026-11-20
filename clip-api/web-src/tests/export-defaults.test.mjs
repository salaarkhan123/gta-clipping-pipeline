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
  // ... sends them back unless a caption line was changed here: then the lines, no words, word cuts kept as cuts
  assert.match(edit, /export function forApi\(e: Edit\) \{[\s\S]*?words \? \{ words: lines \? null : words \} : \{\}/);
  assert.match(edit, /lines && words \? words\.filter\(\(w\) => w\.cut\)\.reduce\(\(all, w\) => addCut\(all, \[w\.start, w\.end\]\), e\.cuts\)/);
  assert.match(source("lib/exporting.ts"), /options = \{ \.\.\.options, hook: options\.hook_overlay \}/);
});

test("new website jobs ask for previews; the export dialogs show the exact price", () => {
  assert.match(source("lib/options.ts"), /export const RENDER = "preview";/);
  assert.match(source("components/dash/setup/JobSetup.tsx"), /render: RENDER/);
  for (const file of ["components/dash/Editor.tsx", "components/dash/BulkEdit.tsx"]) assert.match(source(file), /<QuoteLine [^>]*exact \/>/);
  assert.match(source("components/dash/ClipCard.tsx"), /clip\.rendered !== "full" && <ExportFull/);
});
