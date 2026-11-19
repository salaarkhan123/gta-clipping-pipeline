import { api, API, ApiError, getToken } from "./api";
import CONTRACT from "./api-contract.json";
import { deadAir } from "./deadair";

// An edit of one clip, as the editor keeps it. Every time is in seconds of the SOURCE video, so an edit means the
// same thing however the clip was rendered before.
// - trim: where the clip starts and ends in the source (it may reach outside the clip's first cut).
// - cuts: parts inside the trim to leave out, sorted, never overlapping.
// - caption_lines: the caption lines with their text as the user wrote them. Empty: the words as they were said.
// - hook_text: the on-screen hook in the user's words; null keeps the AI's.
// - options: the look (POST /v1/clips option names, only those GET /v1/options lists).
// The API does not store an edit yet (the export agent owns that format); `forApi` is the one place that turns
// this into what it sends, so only it changes when the stored format lands.
export type Span = [number, number];
export type Line = { start: number; end: number; text: string };
// - words: the caption word by word as text-based editing saved it (API `edit.words`: edited text, hidden words,
//   highlights, emoji, splits, words cut with their video). Kept as the API sent it: this editor does not change
//   it, and a save or export that dropped it would undo those edits (PATCH replaces the whole edit).
export type EditWord = { start: number; end: number; text: string; hidden?: boolean; cut?: boolean;
  highlight?: string | null; emoji?: string | null; break_before?: boolean };
export type Edit = { trim: { start: number; end: number }; cuts: Span[]; caption_lines: Line[]; hook_text: string | null;
  options: Record<string, unknown>; words?: EditWord[] | null };
export type Word = { start: number; end: number; text: string };

// An edit carries only the look options the API's edit takes (lib/api-contract.json `edit_options`, checked against
// the API by clip-api/tests/test_web_contract.py); any other name is a 422. Clip-time options such as tighten,
// punch_zoom or flash_forward stay on the job that made the clip.
const EDIT_OPTIONS = new Set<string>(CONTRACT.edit_options);
export const editOptions = (o: Record<string, unknown>) => Object.fromEntries(Object.entries(o || {}).filter(([k]) => EDIT_OPTIONS.has(k)));
// Saved `words` win over caption lines in the API (ClipEditDoc.caption_words). This editor changes caption text as
// lines (caption_lines is non-empty only when a line was changed here), so a line change sends the lines and no
// words, keeping each word that was cut with its video as a cut; otherwise the saved words go back as they were.
export function forApi(e: Edit) {
  const lines = e.caption_lines.length > 0, words = Array.isArray(e.words) ? e.words : null;
  const cuts = lines && words ? words.filter((w) => w.cut).reduce((all, w) => addCut(all, [w.start, w.end]), e.cuts) : e.cuts;
  return { trim: e.trim, cuts, caption_lines: e.caption_lines, hook_text: e.hook_text,
    ...(words ? { words: lines ? null : words } : {}), options: editOptions(e.options) };
}

export const round = (t: number) => Math.round(t * 100) / 100;
// The shortest clip the editor lets the trim make: the API's shortest clip.
export const MIN_LENGTH = 10;

// A clip with no saved edit opens with the dead air its run cut shown as cuts, so rendering it keeps them; each
// one can be given back like any other cut.
export function startEdit(clip: any, options: Record<string, unknown>): Edit {
  const saved = clip.edit && typeof clip.edit === "object" ? clip.edit : null;     // once the API sends a stored edit
  if (saved?.trim && Array.isArray(saved.cuts)) return { caption_lines: [], hook_text: null, options, ...saved };
  const trim = { start: round(clip.start_sec), end: round(clip.end_sec) };
  return { trim, cuts: deadAir(clip.segments, trim.start, trim.end), caption_lines: [], hook_text: null, options };
}

// ---------- the draft in this browser, one per clip ----------
const key = (clipId: string) => `cc_edit_${clipId}`;
export type Draft = { edit: Edit; at: number };
export function loadDraft(clipId: string): Draft | null {
  try {
    const d = JSON.parse(localStorage.getItem(key(clipId)) || "null");
    return d && d.edit?.trim && Array.isArray(d.edit.cuts) ? d : null;
  } catch { return null; }
}
export function saveDraft(clipId: string, edit: Edit): number {
  const at = Date.now();
  try { localStorage.setItem(key(clipId), JSON.stringify({ edit, at })); } catch { /* storage full or blocked: the edit stays on the page */ }
  return at;
}
export const dropDraft = (clipId: string) => { try { localStorage.removeItem(key(clipId)); } catch { /* nothing kept */ } };
export const hasDraft = (clipId: string) => { try { return !!localStorage.getItem(key(clipId)); } catch { return false; } };
export const sameEdit = (a: Edit, b: Edit) => JSON.stringify(a) === JSON.stringify(b);

// ---------- cuts ----------
// A new cut joins the ones it touches; anything outside the trim is dropped.
export function addCut(cuts: Span[], [s, e]: Span): Span[] {
  const all = [...cuts, [round(Math.min(s, e)), round(Math.max(s, e))] as Span].sort((a, b) => a[0] - b[0]);
  const out: Span[] = [];
  for (const c of all) {
    const last = out[out.length - 1];
    if (last && c[0] <= last[1] + 0.05) last[1] = Math.max(last[1], c[1]);
    else out.push([c[0], c[1]]);
  }
  return out;
}
// The cuts with one span given back.
export function removeSpan(cuts: Span[], [s, e]: Span): Span[] {
  const out: Span[] = [];
  for (const [a, b] of cuts) {
    if (b <= s || a >= e) { out.push([a, b]); continue; }
    if (a < s - 0.01) out.push([a, round(s)]);
    if (b > e + 0.01) out.push([round(e), b]);
  }
  return out;
}
export const inCut = (t: number, cuts: Span[]) => cuts.find(([s, e]) => t >= s && t < e) || null;
// How long the clip is with its trim and cuts.
export function keptLength(e: Edit): number {
  const cut = e.cuts.reduce((n, [s, x]) => n + Math.max(0, Math.min(x, e.trim.end) - Math.max(s, e.trim.start)), 0);
  return Math.max(0, e.trim.end - e.trim.start - cut);
}
// Cuts that still fall inside the trim, clipped to it.
export const cutsInside = (e: Edit): Span[] =>
  e.cuts.map(([s, x]) => [Math.max(s, e.trim.start), Math.min(x, e.trim.end)] as Span).filter(([s, x]) => x - s > 0.01);

// ---------- words and caption lines ----------
// A clip's word times are on its rendered timeline. With `segments` (the source parts the clip was rendered from,
// in order) they are mapped back exactly; without them, the clip is taken to run straight from its start, which
// is close but not exact when dead air was cut or the clip opens on its peak. `exact` says which.
export function sourceTime(clip: any): { at: (t: number) => number; exact: boolean } {
  const segs: Span[] | null = Array.isArray(clip.segments) && clip.segments.every((s: any) => Array.isArray(s) && s.length === 2) ? clip.segments : null;
  if (!segs) return { at: (t) => round(clip.start_sec + t), exact: false };
  return { exact: true, at: (t) => {
    let left = t;
    for (const [s, e] of segs) { if (left < e - s) return round(s + left); left -= e - s; }
    const [, end] = segs[segs.length - 1];
    return round(end);
  } };
}

// The clip's spoken words in source seconds, from its captions file; the subtitles route when that file cannot be
// read from the browser. [] when the clip has no captions.
export async function loadWords(clip: any): Promise<Word[]> {
  const map = sourceTime(clip).at;
  if (clip.captions_url) {
    try {
      const r = await fetch(clip.captions_url);
      if (r.ok) {
        const words = (await r.json())?.words;
        if (Array.isArray(words)) return words.filter((w: any) => typeof w?.start === "number" && typeof w?.text === "string")
          .map((w: any) => ({ start: map(w.start), end: map(Math.max(w.end ?? w.start, w.start)), text: String(w.text).trim() })).filter((w) => w.text);
      }
    } catch { /* fall through to the subtitles route */ }
  }
  const res = await fetch(`${API}/v1/clips/${clip.id}/subtitles?format=vtt`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (res.status === 404) return [];
  if (!res.ok) throw new ApiError(res.status, "error", "Couldn't read this clip's words.");
  return vttWords(await res.text()).map((w) => ({ ...w, start: map(w.start), end: map(w.end) }));
}
// Cues split into words, each word given an even share of its cue's time.
function vttWords(vtt: string): Word[] {
  const out: Word[] = [];
  const stamp = (s: string) => s.split(":").reduce((t, n) => t * 60 + parseFloat(n), 0);
  for (const block of vtt.split(/\n\s*\n/)) {
    const m = block.match(/([\d:.]+)\s*-->\s*([\d:.]+)\s*\n([\s\S]+)/);
    if (!m) continue;
    const a = stamp(m[1]), b = stamp(m[2]), words = m[3].trim().split(/\s+/);
    words.forEach((text, i) => out.push({ start: a + ((b - a) * i) / words.length, end: a + ((b - a) * (i + 1)) / words.length, text }));
  }
  return out;
}
// Words grouped into caption lines the way the API's subtitle files are: up to 7 words or 42 characters, a new
// line after a pause of 0.6 s.
export function linesOf(words: Word[]): Line[] {
  const lines: Word[][] = [];
  let cur: Word[] = [];
  for (const w of words) {
    const text = cur.map((x) => x.text).join(" ");
    if (cur.length && (cur.length >= 7 || w.start - cur[cur.length - 1].end > 0.6 || text.length + w.text.length + 1 > 42)) { lines.push(cur); cur = []; }
    cur.push(w);
  }
  if (cur.length) lines.push(cur);
  return lines.map((l) => ({ start: l[0].start, end: Math.max(l[l.length - 1].end, l[0].start + 0.2), text: l.map((w) => w.text).join(" ") }));
}

// ---------- saving and rendering ----------
// Saving an edit on the clip and rendering it again are routes the API is still getting (see lib/routes.ts).
// Both send the edit through `forApi`.
export const saveOnClip = (clipId: string, edit: Edit) => api(`/v1/clips/${clipId}`, { method: "PATCH", body: { edit: forApi(edit) } });
