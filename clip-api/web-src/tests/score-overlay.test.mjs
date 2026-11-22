// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("../", import.meta.url));
const source = (path) => readFileSync(join(web, path), "utf8");

test("Score is the one score mark: an AI score, a sample or a rank, never a virality %", () => {
  const chip = source("components/ui/Score.tsx");
  assert.match(chip, /ai: "AI score", sample: "Sample", rank: "Rank"/);
  assert.doesNotMatch(chip, /virality|viral %|probability/i);
  assert.match(chip, /bg-black\/70/);
  assert.match(chip, /text-lime/);
  assert.match(chip, /sm: \{/);
  assert.match(chip, /md: \{/);
});

test("every place a score shows renders Score: landing, hero stage, results", () => {
  assert.match(source("components/landing/demos/Bits.tsx"), /<Score value=\{value\} kind=\{kind\}/);
  assert.match(source("components/landing/demos/HeroStage.tsx"), /aiRated\(c\) && <Score value=\{c\.rating!\} kind="ai"/);
  assert.match(source("app/page.tsx"), /aiRated\(c\) \? <Score value=\{c\.rating!\} kind="ai" \/>/);
  const rating = source("components/clips/Rating.tsx");
  assert.match(rating, /<Score value=\{r\.shown\} kind="ai"/);
  assert.match(rating, /<Score value=\{r\.rank!\} of=\{r\.of\} kind="rank"/);
});

test("the old chip is gone and nothing draws a score by hand", () => {
  assert.throws(() => source("components/clips/ScoreOverlay.tsx"));
  for (const f of ["components/clips/ClipTile.tsx", "components/clips/Rating.tsx", "components/landing/demos/HeroStage.tsx"])
    assert.doesNotMatch(source(f), /text-\[17px\] font-bold tabular-nums[^"]*text-lime/, f);
});

test("the hero stage is decorative, loops only while shown, and is still under reduced motion", () => {
  const demo = source("components/landing/demos/HeroStage.tsx");
  assert.match(demo, /aria-hidden="true"/);
  assert.match(demo, /useReducedMotion/);
  assert.match(demo, /const phase: Phase = reduced \? "clips" : moving;/);      // the still end state
  assert.match(demo, /usePhase\(play && !reduced\)/);                          // paused off screen and off its slide
  assert.match(demo, /pressed \? "scale-\[\.94\] bg-\[#9fe02f\]" : "bg-lime"/);  // the button's press state
  assert.doesNotMatch(demo, /virality/i);
});

test("prefers-reduced-motion still kills demo motion", () => {
  assert.match(source("components/landing/demos/demos.module.css"), /prefers-reduced-motion: reduce/);
  assert.match(source("app/tokens.css"), /prefers-reduced-motion: reduce/);
});
