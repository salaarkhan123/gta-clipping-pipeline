// Word-level caption edits against exports.EditWord (emoji, highlight, split, text, hide).
// Pure helpers so the editor WordMenu and tests share one shape.

import type { EditWord } from "./edit";

export const WORD_EMOJI_PICKS = ["🔥", "😂", "💀", "😱", "🏆", "👀", "🎯", "💥"] as const;

// Ops that already have BE fields on EditWord. True gaps (B-roll, Music, …) stay out of this union.
export type WordEditOp =
  | { kind: "text"; text: string }
  | { kind: "highlight"; colour: string | null }
  | { kind: "emoji"; emoji: string | null }
  | { kind: "split" }
  | { kind: "hide"; hidden: boolean };

export const tidyWordText = (raw: string): string | null => {
  const v = raw.trim().replace(/[{}\\]/g, "").slice(0, 60);
  return v || null;
};

export const isEditWordList = (words: unknown): words is EditWord[] =>
  Array.isArray(words) && words.every((w) => w && typeof w === "object"
    && typeof (w as EditWord).start === "number" && typeof (w as EditWord).end === "number"
    && typeof (w as EditWord).text === "string" && "highlight" in (w as object) && "emoji" in (w as object)
    && "break_before" in (w as object) && "hidden" in (w as object) && "cut" in (w as object));

// Apply one EditWord-backed op to the selected indexes. Split toggles break_before on the first pick only;
// emoji attaches to the last pick (drawn after that word). Others update every picked word.
export function applyWordOp(words: EditWord[], picked: number[], op: WordEditOp): EditWord[] {
  if (!picked.length) return words;
  const first = Math.min(...picked), last = Math.max(...picked);
  const set = new Set(picked);
  if (op.kind === "split") {
    return words.map((w, i) => (i === first ? { ...w, break_before: !w.break_before } : w));
  }
  if (op.kind === "emoji") {
    return words.map((w, i) => (i === last ? { ...w, emoji: w.emoji === op.emoji ? null : op.emoji } : w));
  }
  if (op.kind === "text") {
    const text = tidyWordText(op.text);
    if (!text) return words;
    return words.map((w, i) => (set.has(i) ? { ...w, text } : w));
  }
  if (op.kind === "highlight") {
    return words.map((w, i) => (set.has(i) ? { ...w, highlight: op.colour } : w));
  }
  return words.map((w, i) => (set.has(i) ? { ...w, hidden: op.hidden } : w));
}

export const wordEditReady = (words: EditWord[] | null | undefined): words is EditWord[] =>
  Array.isArray(words) && isEditWordList(words);
