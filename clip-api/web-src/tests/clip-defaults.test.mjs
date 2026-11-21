// node --test tests/
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const source = (path) => readFileSync(join(root, path), "utf8");
const files = (dir) => readdirSync(join(root, dir)).flatMap((n) => {
  const p = join(dir, n);
  return statSync(join(root, p)).isDirectory() ? files(p) : /\.tsx?$/.test(n) ? [p] : [];
});

test("no clip cap unless the user sets one; lengths stop at 60 s plus Auto", () => {
  const form = source("components/dash/setup/JobSetup.tsx"), chooser = source("components/dash/LinkChooser.tsx");
  assert.match(form, /limit: null as number \| null/);
  assert.match(form, /if \(!has\("limit"\) && f\.limit !== null\) o\.max_clips =/);
  assert.match(chooser, /else if \(o\.cap !== null\) options\.max_clips = o\.cap;/);
  assert.doesNotMatch(form + chooser, /max_clips = 3|max_clips: 3/);
  for (const text of [form, chooser]) assert.match(text, /allows\(listed, "duration", b\) && offeredBucket\(b\)/);
  assert.match(source("lib/options.ts"), /export const offeredBucket = \(b: string\) => b === "0-90" \|\| \+b\.split\("-"\)\[1\] <= 60;/);
  const offered = (b) => b === "0-90" || +b.split("-")[1] <= 60;                     // the rule in lib/options.ts
  assert.deepEqual(["0-90", "0-30", "30-60", "60-90", "90-180", "180-300"].filter(offered), ["0-90", "0-30", "30-60"]);
});

test("the score is an AI rating, never a probability or a prediction of virality", () => {
  for (const f of [...files("app"), ...files("components")]) {
    const text = source(f).replace(/\/\/.*$/gm, "");
    assert.doesNotMatch(text, /virality score|probability|predict/i, f);
  }
});
