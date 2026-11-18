// What the results page shows about clips and jobs, worked out from the API's own fields only (GET /v1/projects/{id},
// clip_json and job_json in app/routes_media.py). No imports, so `node --test` runs it as it is.

// ---- AI rating ----------------------------------------------------------------------------------------------

// The five sub-scores of judge v2 (`clip.scores`, app/ai.py SCORES), in the order the AI gives them.
const V2_PARTS: Record<string, string> = { hook: "Hook", payoff: "Payoff", clarity: "Clarity", emotion: "Emotion", pacing: "Pacing" };
// Judge v1's four (`clip.virality`, app/ai.py PARTS): clips rated before judge v2 carry these instead.
const V1_PARTS: Record<string, string> = { hook: "Hook", flow: "Flow", value: "Value", trend: "Trend" };

export type Part = { key: string; label: string; value: number };
export type Rating = {
  shown: number | null;       // display_score: the AI rating calibrated across this run (55 to 99), null when not rated
  raw: number | null;         // virality_score: the AI's own 0-100
  parts: Part[];              // the sub-scores behind it, five for judge v2 clips, four for older ones
  version: "v2" | "v1" | null;
  rank: number | null;        // place in its run by AI rating, 1 = best
  of: number | null;          // clips in its run
  why: string | null;         // the AI's one-sentence reason
};

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function partsOf(src: unknown, names: Record<string, string>): Part[] {
  if (!src || typeof src !== "object") return [];
  const o = src as Record<string, unknown>;
  return Object.keys(names).filter((k) => num(o[k])).map((k) => ({ key: k, label: names[k], value: Math.round(o[k] as number) }));
}

export function ratingOf(c: any): Rating {
  const v2 = partsOf(c.scores, V2_PARTS);
  const v1 = v2.length ? [] : partsOf(c.virality, V1_PARTS);
  const rank = num(c.rank_index) ? c.rank_index + 1 : num(c.rank) ? c.rank : null;
  return {
    shown: num(c.display_score) ? Math.round(c.display_score) : null,
    raw: num(c.virality_score) ? Math.round(c.virality_score) : null,
    parts: v2.length ? v2 : v1,
    version: v2.length ? "v2" : v1.length ? "v1" : null,
    rank, of: num(c.rank_of) ? c.rank_of : null,
    why: (typeof c.why === "string" && c.why) || (typeof c.reason === "string" && c.reason) || null,
  };
}

// ---- Kinds ----------------------------------------------------------------------------------------------------

// The labels the AI gives a moment (app/pipeline/moments.py KINDS). A kind the API adds later is shown by its own name.
const KIND_NAMES: Record<string, string> = { funny: "Funny", argument: "Argument", reaction: "Reaction", clutch: "Clutch", fail: "Fail", story: "Story" };
export const kindName = (k: string) => KIND_NAMES[k] || k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " ");

// The kinds present in these clips, most common first: the filter offers only what the API returned.
export function kindsIn(clips: any[]): { kind: string; count: number }[] {
  const n = new Map<string, number>();
  for (const c of clips) if (typeof c.kind === "string" && c.kind) n.set(c.kind, (n.get(c.kind) || 0) + 1);
  return [...n].map(([kind, count]) => ({ kind, count })).sort((a, b) => b.count - a.count || a.kind.localeCompare(b.kind));
}

// ---- Sorting and filters --------------------------------------------------------------------------------------

export type Sort = "rating" | "time";
export type Mark = "all" | "kept" | "liked" | "bookmarked" | "discarded";
export type View = { sort: Sort; kind: string | null; mark: Mark };

const MARKS: Record<Mark, (c: any) => boolean> = {
  all: () => true, kept: (c) => c.kept === true, liked: (c) => c.reaction === "like",
  bookmarked: (c) => !!c.bookmarked, discarded: (c) => c.kept === false,
};
export const MARK_NAMES: Record<Mark, string> = { all: "All", kept: "Kept", liked: "Liked", bookmarked: "Bookmarked", discarded: "Discarded" };

// The best clip first by AI rating. Clips the AI did not rate follow, by the API's own score (how strongly the moment
// stood out). Ties keep the earlier moment first. "time": where the moment is in the source video.
const ratingKey = (c: any) => (num(c.display_score) ? c.display_score : -1);
export function arrange(clips: any[], v: View): any[] {
  const out = clips.filter((c) => MARKS[v.mark](c) && (v.kind === null || c.kind === v.kind));
  if (v.sort === "time") return out.sort((a, b) => a.start_sec - b.start_sec);
  return out.sort((a, b) => ratingKey(b) - ratingKey(a) || (b.score ?? 0) - (a.score ?? 0) || a.start_sec - b.start_sec);
}

// While a run is still adding clips, the cards already shown keep their places and new ones join at the end, so
// nothing jumps under the pointer. `previous` is the order shown last time for the same view.
export function steady(sorted: any[], previous: string[] | null): any[] {
  if (!previous) return sorted;
  const by = new Map(sorted.map((c) => [c.id, c]));
  const kept = previous.filter((id) => by.has(id));
  const had = new Set(kept);
  return [...kept.map((id) => by.get(id)), ...sorted.filter((c) => !had.has(c.id))];
}

// ---- Shape, length --------------------------------------------------------------------------------------------

export type Shape = "tall" | "square" | "wide";
// The clip's shape from its run's `aspect` option (job_json.options); null when the run did not say.
export function shapeOf(aspect: unknown, vertical?: unknown): Shape | null {
  if (aspect === "16:9") return "wide";
  if (aspect === "1:1" || aspect === "4:5") return "square";
  if (aspect === "9:16") return "tall";
  if (vertical === false) return "wide";
  if (vertical === true) return "tall";
  return null;
}
export const ASPECT_CLASS: Record<Shape, string> = { tall: "aspect-[9/16]", square: "aspect-[4/5]", wide: "aspect-video" };

// The clip's length as rendered: its source parts (`segments`, dead air already cut) added up; start to end otherwise.
export function lengthOf(c: any): number {
  if (Array.isArray(c.segments) && c.segments.length) {
    const s = c.segments.reduce((t: number, p: any) => t + (Array.isArray(p) && num(p[0]) && num(p[1]) ? Math.max(0, p[1] - p[0]) : 0), 0);
    if (s > 0) return s;
  }
  return Math.max(0, (c.end_sec ?? 0) - (c.start_sec ?? 0));
}

// ---- Jobs -----------------------------------------------------------------------------------------------------

export const isActive = (j: any) => j.status === "QUEUED" || j.status === "RUNNING";
export const isStopped = (j: any) => j.status === "CANCELED" || j.status === "CANCELLED";

// The stages the worker reports (`job.stage`, app/pipeline and app/worker.py), in words. Unknown ones read "Working".
const STAGES: Record<string, string> = {
  starting: "Starting", importing: "Importing the video", downloading: "Getting your video", checking: "Checking the video",
  probing: "Reading the video", language: "Detecting the language", chat_motion: "Watching chat", audio: "Listening for reactions",
  transcribing: "Transcribing speech", translating: "Translating", indexing_frames: "Looking through the frames",
  searching: "Searching", judging: "Rating the moments", rendering: "Rendering clips", writing_titles: "Writing titles",
  storing: "Saving clips", uploading: "Saving clips", summarizing: "Summarising", done: "Finishing",
};
export function stageName(j: any): string {
  if (j.status === "QUEUED") return "Waiting in line";
  return (typeof j.stage === "string" && STAGES[j.stage]) || "Working";
}

export type Outcome =
  | { kind: "running" }
  | { kind: "done"; charged: number | null; returned: number }
  | { kind: "failed"; refunded: number | null; message: string | null }
  | { kind: "cancelled"; refunded: number | null };

// What happened to a job and its credits, exactly as job_json reports them: a failed or cancelled job is settled with
// credits_charged 0, so its whole reservation went back (app/ledger.py settle).
export function outcomeOf(j: any): Outcome {
  if (isActive(j)) return { kind: "running" };
  const reserved = num(j.credits_reserved) ? j.credits_reserved : null;
  const refunded = j.credits_charged === 0 ? reserved : null;
  if (j.status === "FAILED" || j.status === "LOST") return { kind: "failed", refunded, message: j.error?.message || null };
  if (isStopped(j)) return { kind: "cancelled", refunded };
  const charged = num(j.credits_charged) ? j.credits_charged : null;
  return { kind: "done", charged, returned: charged !== null && reserved !== null ? Math.max(0, reserved - charged) : 0 };
}

// ---- Export resolutions ---------------------------------------------------------------------------------------

// Short side in pixels of each `resolution` value (app/pipeline/render.py RESOLUTIONS).
export const SIDE: Record<string, number> = { "480": 480, "720": 720, "1080": 1080, "2k": 1440, "4k": 2160 };
export const resolutionName = (r: string) => (r === "2k" ? "2K (1440p)" : r === "4k" ? "4K (2160p)" : `${r}p`);

export type ResChoice = { value: string; allowed: boolean; overSource: boolean };
// The resolutions GET /v1/options lists, each marked with whether the plan's cap (`max_side`, GET /v1/billing/plans)
// allows it and whether it is above the source (the API never renders above the source's own short side).
// `cap` null: the plan's cap is not known here, so nothing is marked as refused and the server applies it.
export function resolutionChoices(values: string[], cap: number | null, sourceSide: number | null): ResChoice[] {
  return values.filter((v) => v in SIDE).map((v) => ({
    value: v, allowed: cap === null || SIDE[v] <= cap, overSource: sourceSide !== null && SIDE[v] > sourceSide,
  }));
}

// ---- Transcript -----------------------------------------------------------------------------------------------

export type Cue = { start: number; end: number; text: string };
const stamp = (s: string) => {
  const m = s.trim().match(/^(?:(\d+):)?(\d+):(\d+)[.,](\d+)$/);
  return m ? (+(m[1] || 0)) * 3600 + +m[2] * 60 + +m[3] + +m[4] / 1000 : NaN;
};
// The cues of a WebVTT file (GET /v1/clips/{id}/subtitles?format=vtt): times are clip times.
export function parseVtt(text: string): Cue[] {
  const out: Cue[] = [];
  for (const block of text.replace(/\r/g, "").split(/\n\n+/)) {
    const lines = block.split("\n");
    const at = lines.findIndex((l) => l.includes("-->"));
    if (at < 0) continue;
    const [a, b] = lines[at].split("-->").map((x) => stamp(x.split(" ").filter(Boolean)[0] || ""));
    const text = lines.slice(at + 1).join(" ").trim();
    if (Number.isFinite(a) && Number.isFinite(b) && text) out.push({ start: a, end: b, text });
  }
  return out;
}
export const cueAt = (cues: Cue[], t: number) => cues.findIndex((c) => t >= c.start && t < c.end);
