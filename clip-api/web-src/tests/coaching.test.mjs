// Per-dimension AI rating coaching: band → sentence from the numeric sub-score only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { coachingFor, scoreBand } from "../lib/coaching.ts";
import { GAMING_SCORES, V1_SCORES, V2_SCORES } from "../lib/scores.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("scoreBand maps numeric values to strong / mid / weak", () => {
  assert.equal(scoreBand(100), "strong");
  assert.equal(scoreBand(75), "strong");
  assert.equal(scoreBand(74), "mid");
  assert.equal(scoreBand(45), "mid");
  assert.equal(scoreBand(44), "weak");
  assert.equal(scoreBand(0), "weak");
  assert.equal(scoreBand(Number.NaN), "weak");
});

test("coachingFor returns one sentence per band for every known v2, v1, and gaming score", () => {
  for (const key of [...V2_SCORES, ...V1_SCORES, ...GAMING_SCORES]) {
    const strong = coachingFor(key, 90);
    const mid = coachingFor(key, 60);
    const weak = coachingFor(key, 20);
    assert.equal(typeof strong, "string");
    assert.equal(typeof mid, "string");
    assert.equal(typeof weak, "string");
    assert.ok(strong.length > 10, `${key} strong too short`);
    assert.ok(mid.length > 10, `${key} mid too short`);
    assert.ok(weak.length > 10, `${key} weak too short`);
    assert.notEqual(strong, mid);
    assert.notEqual(mid, weak);
    assert.notEqual(strong, weak);
  }
});

test("missing or non-finite scores yield no coaching", () => {
  assert.equal(coachingFor("hook", null), null);
  assert.equal(coachingFor("hook", undefined), null);
  assert.equal(coachingFor("hook", Number.NaN), null);
  assert.equal(coachingFor("payoff", "80"), null);
});

test("coaching copy is AI opinion, never a letter grade or view forecast", () => {
  for (const key of [...V2_SCORES, ...V1_SCORES, ...GAMING_SCORES]) {
    for (const v of [90, 60, 20]) {
      const tip = coachingFor(key, v);
      assert.doesNotMatch(tip, /\b[A-F][+-]?\b/);
      assert.doesNotMatch(tip, /letter grade|probability|% chance|views you will get|go viral/i);
    }
  }
});

test("RatingParts wires coachingFor under each bar and keeps overall why", () => {
  const rating = source("components/clips/Rating.tsx");
  assert.match(rating, /coachingFor/);
  assert.match(rating, /lib\/coaching/);
  assert.match(rating, /r\.why && !compact/);
  assert.doesNotMatch(rating, /\b[A-F][+-]?\s*(Hook|Flow|Value|Trend)\b/);
  assert.doesNotMatch(rating, /letter grade|virality probability|chance to go viral/i);
});

test("ClipCard still surfaces suggestion.text tip separately", () => {
  const card = source("components/dash/ClipCard.tsx");
  assert.match(card, /clip\.suggestion\?\.text/);
});
