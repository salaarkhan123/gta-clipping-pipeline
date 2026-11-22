// node --test tests/
import assert from "node:assert/strict";
import { test } from "node:test";
import { MAX_CLIPS, MIN_WANT, SEC_PER_SLOT, suggestWant } from "../lib/highlights.ts";

test("suggestWant mirrors pipeline highlights.py (2h → 40 inside 30–50)", () => {
  assert.equal(SEC_PER_SLOT, 180);
  assert.equal(MAX_CLIPS, 50);
  assert.equal(suggestWant(0), MIN_WANT);
  assert.equal(suggestWant(10 * 60), MIN_WANT);
  assert.equal(suggestWant(30 * 60), 10);
  assert.equal(suggestWant(60 * 60), 20);
  assert.equal(suggestWant(2 * 60 * 60), 40);
  assert.equal(suggestWant(3 * 60 * 60), MAX_CLIPS);
});
