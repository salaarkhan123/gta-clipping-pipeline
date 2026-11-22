// Sub-score labels: every score the API's judge names (app/ai.py SCORES) has a proper label, and the app's score
// views read the one shared map (lib/scores.ts) instead of their own.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { GAMING_SCORES, SCORE_LABELS, scoreLabel, V2_SCORES } from "../lib/scores.ts";

const here = (p) => fileURLToPath(new URL(p, import.meta.url));

test("every judge v2 and gaming score has a label", () => {
  for (const k of V2_SCORES) assert.ok(SCORE_LABELS[k] && SCORE_LABELS[k] !== k, `no label for ${k}`);
  for (const k of GAMING_SCORES) assert.ok(SCORE_LABELS[k], `no gaming label for ${k}`);
  assert.equal(scoreLabel("payoff"), "Payoff");
  assert.equal(scoreLabel("kills_clutches"), "Kills / clutches");
  assert.equal(scoreLabel("new_part"), "New part");
});

test("the labels cover the scores app/ai.py names", (t) => {
  const ai = here("../../app/ai.py");
  if (!existsSync(ai)) return t.skip("backend not in this tree");
  // app/ai.py names them, or (with #177) takes them from app/pipeline/ranking.py: `SCORES = ranking.SCORES`.
  const src = readFileSync(ai, "utf8");
  const ranking = here("../../app/pipeline/ranking.py");
  const m = src.match(/^SCORES\s*=\s*\(([^)]*)\)/m)
    || (/^SCORES\s*=\s*ranking\.SCORES\b/m.test(src) && existsSync(ranking) && readFileSync(ranking, "utf8").match(/^SCORES\s*=\s*\(([^)]*)\)/m));
  if (!m) return t.skip("this backend has no judge v2 SCORES yet");
  const keys = [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
  assert.deepEqual(keys, [...V2_SCORES]);
  const gaming = here("../../app/gaming_rating.py");
  if (!existsSync(gaming)) return;
  const g = readFileSync(gaming, "utf8").match(/GAMING_COMPONENTS[^=]*=\s*\(([^)]*)\)/m);
  assert.ok(g, "gaming_rating.py should define GAMING_COMPONENTS");
  const gKeys = [...g[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
  assert.deepEqual(gKeys, [...GAMING_SCORES]);
});

test("score views use the shared map", () => {
  // The dashboard card draws the one shared score mark, so it holds no labels of its own.
  assert.match(readFileSync(here("../components/dash/ClipCard.tsx"), "utf8"), /export const ScoreBadge = \(\{ clip \}: \{ clip: any \}\) => <RatingBadge clip=\{clip\} size="sm" \/>;/);
  for (const f of ["../components/clips/model.ts"]) {
    const p = here(f); if (!existsSync(p)) continue;
    const src = readFileSync(p, "utf8");
    assert.match(src, /lib\/scores/, `${f} should import lib/scores`);
    assert.doesNotMatch(src, /(PART_NAMES|V2_PARTS|V1_PARTS)\s*:\s*Record/, `${f} keeps its own label map`);
  }
});
