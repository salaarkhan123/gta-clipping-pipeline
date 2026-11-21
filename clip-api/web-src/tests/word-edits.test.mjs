// node --test tests/   (Node 23.6 or later runs the .ts module as it is)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { applyWordOp, isEditWordList, tidyWordText, WORD_EMOJI_PICKS, wordEditReady } from "../lib/wordEdits.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const W = (over = {}) => ({
  start: 1, end: 1.4, text: "wow", hidden: false, cut: false, highlight: null, emoji: null, break_before: false, ...over,
});

test("EditWord list detection accepts the words GET shape and rejects plain transcript words", () => {
  assert.equal(isEditWordList([W()]), true);
  assert.equal(isEditWordList([]), true);
  assert.equal(isEditWordList([{ start: 1, end: 2, text: "wow" }]), false);
  assert.equal(wordEditReady([W()]), true);
  assert.equal(wordEditReady(null), false);
});

test("highlight, emoji, and split mutate EditWord fields the PATCH body keeps", () => {
  const base = [W({ text: "oh" }), W({ start: 1.4, end: 1.8, text: "my" }), W({ start: 1.8, end: 2.2, text: "god" })];
  const lit = applyWordOp(base, [2], { kind: "highlight", colour: "#ff3355" });
  assert.equal(lit[2].highlight, "#ff3355");
  assert.equal(lit[0].highlight, null);

  const cleared = applyWordOp(lit, [2], { kind: "highlight", colour: null });
  assert.equal(cleared[2].highlight, null);

  const withEmoji = applyWordOp(base, [0, 1, 2], { kind: "emoji", emoji: "🔥" });
  assert.equal(withEmoji[2].emoji, "🔥");          // emoji attaches after the last selected word
  assert.equal(withEmoji[0].emoji, null);

  const toggled = applyWordOp(withEmoji, [2], { kind: "emoji", emoji: "🔥" });
  assert.equal(toggled[2].emoji, null);

  const split = applyWordOp(base, [1, 2], { kind: "split" });
  assert.equal(split[1].break_before, true);       // split marks the first selected word
  assert.equal(split[2].break_before, false);
  assert.equal(applyWordOp(split, [1], { kind: "split" })[1].break_before, false);
});

test("edit text and hide keep spoken times on the EditWord the save sends", () => {
  const base = [W({ text: "god", start: 11.8, end: 12.4 })];
  assert.equal(tidyWordText("  {\\b1}nope  "), "b1nope");
  assert.equal(tidyWordText("   "), null);

  const renamed = applyWordOp(base, [0], { kind: "text", text: "GOD!" });
  assert.equal(renamed[0].text, "GOD!");
  assert.equal(renamed[0].start, 11.8);
  assert.equal(renamed[0].end, 12.4);

  const hidden = applyWordOp(renamed, [0], { kind: "hide", hidden: true });
  assert.equal(hidden[0].hidden, true);
  // forApi (lib/edit.ts) sends edit.words as-is when caption_lines stay empty.
  assert.match(source("lib/edit.ts"), /words \? \{ words: lines \? null : words \}/);
  assert.deepEqual(
    { highlight: hidden[0].highlight, emoji: hidden[0].emoji, break_before: hidden[0].break_before, hidden: hidden[0].hidden, text: hidden[0].text },
    { highlight: null, emoji: null, break_before: false, hidden: true, text: "GOD!" },
  );
});

test("WordMenu uses applyWordOp and Soon only when EditWord is unavailable", () => {
  const words = source("components/dash/editor/Words.tsx");
  const editor = source("components/dash/Editor.tsx");
  const helpers = source("lib/wordEdits.ts");
  assert.match(helpers, /export type WordEditOp =/);
  assert.match(words, /applyWordOp/);
  assert.match(words, /wordEditReady/);
  assert.match(words, /if \(!on \|\| !wordEditReady\(words\)\) return \([\s\S]{0,200}<ComingSoonBadge short \/>/);
  assert.match(editor, /loadEditWords\(clip\.id\)/);
  assert.match(editor, /setWordEditsOn\(isEditWordList\(list\)\)/);
  assert.match(editor, /const menuOn = !!model && wordEditReady\(model\)/);
  for (const item of ["Edit word", "Split here", "Highlight", "Remove caption", "Remove caption &amp; video", "Add emoji"]) {
    assert.ok(words.includes(item), item);
  }
  for (const e of WORD_EMOJI_PICKS) assert.ok(helpers.includes(`"${e}"`), e);
});
