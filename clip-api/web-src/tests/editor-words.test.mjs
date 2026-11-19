// node --test tests/   (Node 23.6 or later runs the .ts module as it is)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("the edit sends its words (#215) and keeps the rest as it was", () => {
  const edit = source("lib/edit.ts");
  assert.match(edit, /export const forApi = \(e: Edit\) => \(\{ trim: e\.trim, cuts: e\.cuts, caption_lines: e\.caption_lines, hook_text: e\.hook_text, options: e\.options,\s*\.\.\.\(e\.words \? \{ words: e\.words \} : \{\}\) \}\);/);
  assert.match(edit, /export type EditWord = \{ start: number; end: number; text: string; hidden: boolean; cut: boolean; highlight: string \| null;\s*emoji: string \| null; break_before: boolean \};/);
});

test("word menu and caption look appear only when the API has them; otherwise Coming soon", () => {
  const routes = source("lib/routes.ts"), editor = source("components/dash/Editor.tsx"), words = source("components/dash/editor/Words.tsx");
  assert.match(routes, /paths\?\.\["\/v1\/clips\/\{clip_id\}\/words"\]\?\.get/);           // feature-detected in /openapi.json
  assert.match(routes, /components\?\.schemas\?\.CaptionLook/);
  assert.match(editor, /const model: EditWord\[\] \| null = known\.words \?/);
  assert.match(words, /if \(!on \|\| !words\) return \([\s\S]{0,200}<ComingSoonBadge short \/>/);
  assert.match(words, /if \(!spec\) return <p [^>]*>Font, weight, colours, size, italic, underline, case and row <ComingSoonBadge short \/>/);
  for (const item of ["Edit word", "Split here", "Highlight", "Remove caption", "Remove caption &amp; video", "Add emoji"]) assert.ok(words.includes(item), item);
});

test("the preview draws the render's fonts, size and row", () => {
  const fonts = source("components/dash/editor/captionFonts.ts"), words = source("components/dash/editor/Words.tsx");
  for (const f of ["anton", "bebas", "bangers", "luckiest", "poppins"]) assert.match(fonts, new RegExp(`${f}: \\{ name:`));
  assert.match(fonts, /Noto_Emoji/);
  assert.match(words, /fontSize: `\$\{size\}cqh`/);                 // 100 % = 6 % of the frame's height, like the renderer
  assert.match(words, /top: `\$\{\(look\.y \?\? 0\.72\) \* 100\}%`/);
});
