// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("../", import.meta.url));
const source = (path) => readFileSync(join(web, path), "utf8");

test("ScoreOverlay is the one chip: AI quality or Sample score, never a virality %", () => {
  const chip = source("components/clips/ScoreOverlay.tsx");
  assert.match(chip, /AI quality/);
  assert.match(chip, /Sample score/);
  assert.doesNotMatch(chip, /virality|viral %|probability/i);
  assert.match(chip, /rounded-\[7px\]/);
  assert.match(chip, /bg-black\/70/);
  assert.match(chip, /text-\[17px\]/);
  assert.match(chip, /text-lime/);
});

test("landing AiRating and results RatingBadge both render ScoreOverlay", () => {
  assert.match(source("components/landing/demos/Bits.tsx"), /ScoreOverlay/);
  assert.match(source("components/clips/Rating.tsx"), /<ScoreOverlay value=\{r\.shown\} kind="ai"/);
});

test("hero upload demo uses ScoreOverlay for AI and sample scores and stays decorative", () => {
  const demo = source("components/landing/demos/VodToClips.tsx");
  assert.match(demo, /aria-hidden="true"/);
  assert.match(demo, /kind="sample"/);
  assert.match(demo, /kind="ai"/);
  assert.match(demo, /ASPECTS = \["9:16", "16:9", "1:1", "4:5"\]/);
  assert.match(demo, /Download shapes · auto-post coming soon/);
  assert.doesNotMatch(demo, /virality/i);
});

test("prefers-reduced-motion still kills demo motion", () => {
  assert.match(source("components/landing/demos/demos.module.css"), /prefers-reduced-motion: reduce/);
  assert.match(source("components/landing/demos/VodToClips.tsx"), /useReducedMotion/);
});
