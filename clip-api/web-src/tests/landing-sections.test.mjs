// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("../", import.meta.url));
const source = (path) => readFileSync(join(web, path), "utf8");

test("the landing shows exactly the caption styles the renderer draws", () => {
  const api = source("../app/render_options.py").match(/CaptionStyle = Literal\[([^\]]+)\]/)[1];
  const renderer = [...api.matchAll(/"(\w+)"/g)].map((m) => m[1]);
  const shown = [...source("components/landing/demos/Caption.tsx").matchAll(/\{ id: "(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(shown, renderer);
});

test("the layouts the reframe demo shows are ones the renderer draws, under the app's names", () => {
  const names = { split2: "Split in two", full: "Full", pip: "Picture in picture", screen_first: "Screen first" };
  const built = source("../app/pipeline/layouts.py").match(/^LAYOUTS = \(([^)]+)\)/m)[1];
  const shown = [...source("components/landing/demos/Reframe.tsx").matchAll(/\{ id: "(\w+)", name: "([^"]+)"/g)];
  assert.equal(shown.length, 4);
  for (const [, id, name] of shown) {
    assert.ok(built.includes(`"${id}"`), id);
    assert.equal(name, names[id], id);
  }
});

test("what is not built says Coming soon on the card and offers nothing to click", () => {
  const soon = source("components/landing/demos/Soon.tsx");
  assert.match(soon, /<ComingSoonBadge \/>/);
  assert.doesNotMatch(soon, /<button|<a |href=|onClick/);
  for (const [file, title] of [["sections/TeamsSection.tsx", "Team workspace"]]) {
    const text = source(`components/landing/${file}`);
    assert.match(text, new RegExp(`title: "${title}", soon: true`), file);
    assert.match(text, /\.soon && <ComingSoonBadge \/>/, file);
    assert.doesNotMatch(text, /<button|href=|onClick/, file);
  }
  const carousel = source("components/landing/sections/DemoCarousel.tsx");
  for (const id of ["broll", "voice"]) assert.match(carousel, new RegExp(`id: "${id}",[^}]*soon: true`), id);
});

test("future features are written in the future tense", () => {
  const soon = source("components/landing/demos/Soon.tsx");
  for (const m of soon.matchAll(/text="([^"]+)"/g)) assert.match(m[1], /\bwill\b/, m[1]);
  assert.match(source("components/landing/sections/TeamsSection.tsx"), /will be able to share/);
});

test("an AI rating is shown only when the AI judge rated the clip", () => {
  const footage = source("components/landing/demos/Footage.tsx");
  assert.match(footage, /export const aiRated = \(item: Item \| null\) => typeof item\?\.rating === "number" && item\.rating_source === "ai";/);
  for (const f of ["demos/CaptionStyles.tsx", "demos/Reframe.tsx", "demos/HookText.tsx", "demos/DeadAir.tsx",
    "sections/ModelsSection.tsx", "sections/WorkflowSection.tsx", "sections/EditorSection.tsx", "sections/TeamsSection.tsx"]) {
    for (const line of source(`components/landing/${f}`).split("\n").filter((l) => l.includes("<AiRating") || l.includes("<ScoreOverlay"))) {
      if (line.includes('kind="sample"')) continue;
      assert.match(line, /aiRated\(/, f);
    }
  }
  // Hero walkthrough: AI chip only via aiRated; sample chips are labeled Sample score.
  const vod = source("components/landing/demos/VodToClips.tsx");
  assert.match(vod, /aiRated\(item\)/);
  assert.match(vod, /kind="ai"/);
  assert.match(vod, /kind="sample"/);
});

test("demo media never plays sound, waits for reduced motion and carries its credit", () => {
  const footage = source("components/landing/demos/Footage.tsx");
  assert.match(footage, /<video[^>]*\bmuted\b/);
  assert.match(footage, /!reduced/);
  assert.match(source("components/landing/demos/demos.module.css"), /prefers-reduced-motion: reduce/);
});

test("each card that shows footage names every creator it shows, once, at the bottom", () => {
  const footage = source("components/landing/demos/Footage.tsx");
  assert.doesNotMatch(footage, /item\.credit &&/);                  // no credit chip on a frame
  assert.match(footage, /export function Credits\(\{ items/);
  // Every item a card plays is in its Credits line.
  const cards = {
    "demos/VodToClips.tsx": /<Credits items=\{\[vod, wide\?\.item, \.\.\.tall\]\}/,
    "demos/CaptionStyles.tsx": /<Credits items=\{\[clip\]\}/,
    "demos/HeroStage.tsx": /<Credits items=\{\[vod, \.\.\.tiles\]\}/,
    "demos/Reframe.tsx": /<Credits items=\{items\} \/>/,
    "demos/HookText.tsx": /<Credits items=\{\[real\]\} \/>/,
    "sections/EditorSection.tsx": /<Credits items=\{\[clip\]\}/,
    "demos/DeadAir.tsx": /<Credits items=\{\[clip\]\} \/>/,
    "sections/ModelsSection.tsx": /<Credits items=\{\[vod, best\]\} \/>[\s\S]*<Credits items=\{\[original, split\]\} \/>/,
    "sections/WorkflowSection.tsx": /<Credits items=\{clips\} \/>/,
  };
  for (const [f, credits] of Object.entries(cards)) {
    const text = source(`components/landing/${f}`);
    assert.match(text, credits, f);
    const plays = [...text.matchAll(/<Footage section="[\w-]+" item=\{([\w.?\[\]]+)\}/g)].map((m) => m[1]);
    assert.ok(plays.length > 0, f);
  }
  // Files with no Credits line play no footage.
  assert.doesNotMatch(source("components/landing/sections/TeamsSection.tsx"), /<Footage /);
});

test("hook demo shows one clear subject (NICKMERCS, Warzone), else non-Fortnite approved footage", () => {
  const hook = source("components/landing/demos/HookText.tsx");
  assert.match(hook, /items\.find\(\(i\) => i\.id === "hook-4"\)/);
  assert.match(hook, /!\/fortnite\/i/);
});

test("reframe camera outline is neutral, not a green Facecam sticker", () => {
  const reframe = source("components/landing/demos/Reframe.tsx");
  assert.match(reframe, /label="Camera" tone="white"/);
  assert.doesNotMatch(reframe, /label="Facecam" tone="lime"/);
});

test("editor walkthrough cycles real editor tabs only", () => {
  const ed = source("components/landing/sections/EditorSection.tsx");
  for (const name of ["Transcript", "Caption lines", "Look", "Undo all changes", "Save", "Render", "Your edit"]) {
    assert.match(ed, new RegExp(name));
  }
  assert.doesNotMatch(ed, /B-roll|Upscale|Auto caption magic/i);
});

test("the dead-air and moment-finder cards draw only real data: no sample transcript, peaks or prompt", () => {
  const dead = source("components/landing/demos/DeadAir.tsx"), models = source("components/landing/sections/ModelsSection.tsx");
  assert.match(dead, /useWords\("editor", clip\)/);
  assert.doesNotMatch(dead, /const (SAID|WAVE|SAMPLE)\b/);
  assert.match(models, /i\.source\?\.id === from/);               // marks are clips cut from that same stream
  assert.match(models, /useSignals\("hero-long-video", vod\)/);     // bars are the engine's own highlight score
  assert.match(dead, /usePeaks\("editor", clip\)/);                // waveform is the clip's own audio levels
  assert.doesNotMatch(models, /PEAKS|Police chases|"heist"/);
});

test("the caption presets follow the clip's real words with the renderer's line rules", () => {
  const demo = source("components/landing/demos/CaptionStyles.tsx"), cap = source("components/landing/demos/Caption.tsx");
  const py = source("../app/pipeline/captions.py");
  for (const name of ["PAUSE", "IMPACT_SHORT"]) {
    const ours = cap.match(new RegExp(`${name} = ([\\d.]+)`))[1], theirs = py.match(new RegExp(`^${name} = ([\\d.]+)`, "m"))[1];
    assert.equal(Number(ours), Number(theirs), name);
  }
  assert.match(demo, /wordAt\(said, v\.currentTime\)/);            // timed by the playing clip
  assert.match(demo, /"No captions"/);
  assert.match(demo, /Font <ComingSoonBadge short \/>/);           // the app has no font or effect choice yet
  assert.match(demo, /Effects <ComingSoonBadge short \/>/);
});

test("the clipping slide's rotation: one set per game, each a source and five clips of that same source", async () => {
  const { readFileSync } = await import("node:fs");
  const m = JSON.parse(readFileSync(new URL("../public/media/hero-clean/manifest.json", import.meta.url), "utf8"));
  const sets = [];
  for (const i of m.items) {
    if (i.role === "source") sets.push({ source: i, tiles: [] });
    else sets.at(-1).tiles.push(i);
  }
  const games = sets.map((s) => s.source.game);
  assert.ok(new Set(games).size >= 6, games.join(", "));
  games.forEach((g, i) => assert.notEqual(g, games[(i + 1) % games.length], `${g} twice in a row`));
  const cod = games.map((g, i) => (/call of duty/i.test(g) ? i : -1)).filter((i) => i >= 0);
  for (const i of cod) assert.ok(!cod.includes((i + 1) % games.length), "the two Call of Duty sets are adjacent");
  for (const { source, tiles } of sets) {
    assert.ok(source.source_duration_sec > 600, `${source.id}: the stream's own length`);
    assert.deepEqual(tiles.map((t) => `${t.platform} ${t.aspect}`), ["youtube 16:9", "tiktok 9:16", "instagram 9:16", "facebook 4:5", "youtube 9:16"]);
    for (const t of tiles) {
      assert.equal(t.source.title, source.source.title, `${t.id} is cut from its set's source`);
      assert.equal(t.credit, source.credit, t.id);
      if ("rating" in t) assert.equal(t.rating_source, "ai", `${t.id}: a number is shown only when the AI judge rated the moment`);
    }
  }
});

test("the workflow section claims only what is real: import is a link or an upload, editing is today's run, posting targets the publish platforms", () => {
  const wf = source("components/landing/sections/WorkflowSection.tsx");
  assert.match(wf, /title: "Import"/);
  assert.doesNotMatch(wf, /automatically (pulls|imports)|latest videos|channel's latest/i);
  assert.doesNotMatch(wf, /B-roll|enhances audio/i);
  assert.match(wf, /const PLATFORMS: PlatformId\[\] = \["youtube", "tiktok", "instagram", "facebook"\];/);
  assert.doesNotMatch(wf, /<button|href=|onClick/);
  assert.match(source("app/page.tsx"), /<WorkflowSection \/>/);
});

test("the clipping slide fetches only the next game's posters ahead, never its videos", () => {
  const stage = source("components/landing/demos/HeroStage.tsx");
  const preload = stage.slice(stage.indexOf("function Preload"), stage.indexOf("export function HeroStage"));
  assert.match(preload, /<img key=\{i\.id\} src=\{mediaUrl\("hero-clean", i\.poster\)\}/);
  assert.doesNotMatch(preload, /<video|preload="auto"/);
  assert.match(source("components/landing/demos/Footage.tsx"), /autoPlay preload="none" poster=/);
});
