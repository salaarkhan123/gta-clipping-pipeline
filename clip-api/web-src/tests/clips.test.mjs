// node --test tests/   (Node 23.6 or later runs the .ts module as it is)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { arrange, aspectFromOptions, aspectRatioOf, ASPECT_FRAME, isLowResPreview, kindsIn, lengthOf, outcomeOf, OVERLAY_ASPECTS, parseVtt, ratingOf, resolutionChoices, shapeOf, stageName, steady } from "../components/clips/model.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("the AI rating shows judge v2's five sub-scores, else judge v1's four, and never a probability", () => {
  const v2 = ratingOf({ display_score: 93.4, virality_score: 81, scores: { hook: 90, payoff: 80, clarity: 70, emotion: 60, pacing: 50 }, virality: { hook: 1, flow: 2 }, rank_index: 0, rank_of: 12, why: "Big turn." });
  assert.equal(v2.shown, 93);
  assert.equal(v2.version, "v2");
  assert.deepEqual(v2.parts.map((p) => p.label), ["Hook", "Payoff", "Clarity", "Emotion", "Pacing"]);
  assert.equal(v2.rank, 1);
  assert.equal(v2.of, 12);
  const v1 = ratingOf({ display_score: 70, virality: { score: 66, hook: 70, flow: 60, value: 50, trend: 40 } });
  assert.equal(v1.version, "v1");
  assert.deepEqual(v1.parts.map((p) => p.key), ["hook", "flow", "value", "trend"]);
  const none = ratingOf({ display_score: null, rank: 4, rank_of: 9 });
  assert.equal(none.shown, null);
  assert.equal(none.rank, 4);
  for (const f of ["components/clips/Rating.tsx", "components/clips/ClipTile.tsx", "components/clips/ClipPlayer.tsx"])
    assert.doesNotMatch(source(f), /virality probability|chance to go viral|% viral/i);
});

test("kinds come from the clips themselves, most common first", () => {
  assert.deepEqual(kindsIn([{ kind: "funny" }, { kind: "clutch" }, { kind: "funny" }, { kind: null }]), [{ kind: "funny", count: 2 }, { kind: "clutch", count: 1 }]);
});

test("sort by AI rating (unrated last, by score) or by time, filtered by kind and mark", () => {
  const clips = [
    { id: "a", display_score: 70, score: 1, start_sec: 50, kind: "funny" },
    { id: "b", display_score: 95, score: 1, start_sec: 90, kind: "clutch", bookmarked: true },
    { id: "c", display_score: null, score: 9, start_sec: 10, kind: "funny", kept: false },
  ];
  assert.deepEqual(arrange(clips, { sort: "rating", kind: null, mark: "all" }).map((c) => c.id), ["b", "a", "c"]);
  assert.deepEqual(arrange(clips, { sort: "time", kind: null, mark: "all" }).map((c) => c.id), ["c", "a", "b"]);
  const long = [{ id: "x", start_sec: 5, end_sec: 20 }, { id: "y", start_sec: 1, end_sec: 50, segments: [[1, 11], [30, 50]] }, { id: "z", start_sec: 9, end_sec: 39 }];
  assert.deepEqual(arrange(long, { sort: "duration", kind: null, mark: "all" }).map((c) => c.id), ["y", "z", "x"]);
  assert.deepEqual(arrange(clips, { sort: "rating", kind: "funny", mark: "all" }).map((c) => c.id), ["a", "c"]);
  assert.deepEqual(arrange(clips, { sort: "rating", kind: null, mark: "bookmarked" }).map((c) => c.id), ["b"]);
  assert.deepEqual(arrange(clips, { sort: "rating", kind: null, mark: "discarded" }).map((c) => c.id), ["c"]);
});

test("while a run adds clips, shown cards keep their places and new ones join at the end", () => {
  const sorted = [{ id: "new" }, { id: "b" }, { id: "a" }];
  assert.deepEqual(steady(sorted, ["a", "b"]).map((c) => c.id), ["a", "b", "new"]);
  assert.deepEqual(steady(sorted, null).map((c) => c.id), ["new", "b", "a"]);
});

test("a card takes its run's aspect; its length is the rendered parts", () => {
  assert.equal(shapeOf("9:16"), "tall");
  assert.equal(shapeOf("16:9"), "wide");
  assert.equal(shapeOf("4:5"), "square");
  assert.equal(shapeOf(undefined, false), "wide");
  assert.equal(shapeOf(undefined), null);
  assert.equal(lengthOf({ start_sec: 10, end_sec: 40, segments: [[10, 20], [25, 40]] }), 25);
  assert.equal(lengthOf({ start_sec: 10, end_sec: 40 }), 30);
});

test("overlay aspect ratios stay distinct and map from the job options", () => {
  assert.deepEqual([...OVERLAY_ASPECTS], ["9:16", "1:1", "4:5", "16:9"]);
  assert.equal(aspectFromOptions("9:16"), "9:16");
  assert.equal(aspectFromOptions("1:1"), "1:1");
  assert.equal(aspectFromOptions("4:5"), "4:5");
  assert.equal(aspectFromOptions("16:9"), "16:9");
  assert.equal(aspectFromOptions(undefined, true), "9:16");
  assert.equal(aspectFromOptions(undefined, false), "16:9");
  assert.equal(aspectFromOptions(undefined), "9:16");
  assert.equal(aspectRatioOf("tall"), "9:16");
  assert.equal(aspectRatioOf("square"), "4:5");
  assert.equal(aspectRatioOf("wide"), "16:9");
  assert.equal(ASPECT_FRAME["1:1"], "aspect-square");
  assert.equal(ASPECT_FRAME["4:5"], "aspect-[4/5]");
});

test("low-res preview is only when the API says rendered preview", () => {
  assert.equal(isLowResPreview({ rendered: "preview" }), true);
  assert.equal(isLowResPreview({ rendered: "full" }), false);
  assert.equal(isLowResPreview({ rendered: "none" }), false);
  assert.equal(isLowResPreview({}), false);
  assert.equal(isLowResPreview({ preview_url: "https://x/p.mp4" }), false);
});

test("the clip player shows a low-res preview badge and an aspect toggle, not a fake duplicate", () => {
  const player = source("components/clips/ClipPlayer.tsx");
  assert.match(player, /isLowResPreview/);
  assert.match(player, /Low-res preview/);
  assert.match(player, /OVERLAY_ASPECTS/);
  assert.match(player, /aria-label="Aspect"/);
  assert.doesNotMatch(player, /Duplicate/);
});

test("a failed or cancelled run says what was refunded, from the job's own numbers", () => {
  assert.deepEqual(outcomeOf({ status: "FAILED", credits_reserved: 12, credits_charged: 0, error: { message: "No speech." } }),
    { kind: "failed", refunded: 12, message: "No speech." });
  assert.deepEqual(outcomeOf({ status: "CANCELED", credits_reserved: 5, credits_charged: 0 }), { kind: "cancelled", refunded: 5 });
  assert.deepEqual(outcomeOf({ status: "SUCCEEDED", credits_reserved: 10, credits_charged: 7 }), { kind: "done", charged: 7, returned: 3 });
  assert.equal(outcomeOf({ status: "RUNNING" }).kind, "running");
  assert.equal(stageName({ status: "RUNNING", stage: "transcribing" }), "Transcribing speech");
  assert.equal(stageName({ status: "QUEUED", stage: null }), "Waiting in line");
});

test("export resolutions above the plan's cap cannot be picked; an unknown cap refuses none", () => {
  const r = resolutionChoices(["480", "720", "1080", "2k", "4k"], 1080, 1080);
  assert.deepEqual(r.filter((c) => c.allowed).map((c) => c.value), ["480", "720", "1080"]);
  assert.deepEqual(r.filter((c) => c.overSource).map((c) => c.value), ["2k", "4k"]);
  assert.equal(resolutionChoices(["720", "4k"], null, null).every((c) => c.allowed), true);
});

test("the export price is the server's quote; nothing about credits is worked out in the browser", () => {
  const panel = source("components/clips/ExportPanel.tsx");
  assert.match(panel, /useQuote\(known\.exportQuote \? EXPORT_QUOTE : null, body\(known\.exportQuote\)/);
  assert.match(panel, /creditWords\(ask\.r\.credits\)/);
});

test("the transcript is read from the clip's WebVTT subtitles", () => {
  const cues = parseVtt("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nno way\n\n00:00:01.500 --> 00:01:02.250\nhe actually did it\n");
  assert.deepEqual(cues, [{ start: 0, end: 1.5, text: "no way" }, { start: 1.5, end: 62.25, text: "he actually did it" }]);
});

test("results chrome shares Library's grid/list toggle; list rows still open the player", () => {
  const results = source("components/clips/Results.tsx");
  const tile = source("components/clips/ClipTile.tsx");
  assert.match(results, /import \{ CLIP_LIST, LayoutToggle, nameOf, numbering, useClipLayout \} from "@\/components\/dash\/ClipCard"/);
  assert.match(results, /<ResultsBar view=\{view\} onView=\{setView\} kinds=\{kinds\} total=\{clips\.length\}>/);
  assert.match(results, /<LayoutToggle value=\{layout\} onChange=\{setLayout\} \/>/);
  assert.match(results, /layout === "list" \? CLIP_LIST : GRID\[shape\]/);
  assert.match(results, /onOpen=\{\(\) => setPlaying\(c\.id\)\}/);
  assert.match(tile, /if \(layout === "list"\)/);
  assert.match(tile, /onClick=\{onOpen\}/);
  assert.match(tile, /<RatingBadge clip=\{clip\} \/>/);
});

test("Publish opens the panel; AI B-roll stays Coming soon", () => {
  const player = source("components/clips/ClipPlayer.tsx");
  assert.match(player, /import \{ PublishPanel \} from "@\/components\/publish\/PublishPanel"/);
  assert.match(player, /title="Publish or schedule to connected accounts"[\s\S]*?\/>Publish\s*<\/button>/);
  assert.match(player, /\{publishing && <PublishPanel clipId=\{clip\.id\}/);
  assert.match(player, /const SOON: \[IconName, string\]\[\] = \[\["image", "AI B-roll"\]\]/);
  assert.match(player, /aria-disabled="true"[^]*<ComingSoonBadge short/);
});
