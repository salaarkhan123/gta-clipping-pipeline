// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const setup = source("components/dash/setup/JobSetup.tsx");

test("job setup: tools we don't have are marked Coming soon and can't be turned on", () => {
  for (const name of ["Motion graphics", "Auto B-roll", "Enhance audio", "Auto sound effects", "Auto transitions", "Auto colour correction",
    "Eye-contact correction", "Voice dubbing"]) {
    assert.match(setup, new RegExp(`<SettingRow icon="[a-z]+" name="${name}" soon />`), name);
  }
  // A Coming-soon row draws a switch that is off and disabled, and nothing under it.
  const parts = source("components/dash/setup/parts.tsx");
  assert.match(parts, /\{soon \? <Switch on=\{false\} label=\{`\$\{name\}: coming soon`\} disabled \/> : children\}/);
  assert.match(parts, /\{!soon && under\}/);
  assert.match(setup, /aria-label="Brand kit"/);                                  // brand kits are real: the saved looks
  assert.match(setup, /Upload SRT <ComingSoonBadge short \/>/);
});

test("job setup: the price only comes from the server, and Generate Highlights waits for consent and enough credits", () => {
  // No credit amount is written into the screen: the total is the caller's server quote.
  assert.doesNotMatch(setup, /credits:\s*\d/);
  assert.match(setup, /const credits = price\.state === "ok" \? price\.credits : null;/);
  assert.match(setup, /const ready = [^;]*!short[^;]*\(!consent \|\| consent\.checked\);/);
  assert.match(setup, /: "Generate Highlights"\}<\/button>/);
  assert.match(setup, /One click: analyse, rank, clip, captions and framing/);
  assert.match(setup, /import \{ suggestWant \} from "@\/lib\/highlights"/);
  assert.match(setup, /Up to ~\$\{autoCap\} ranked highlights/);
  const chooser = source("components/dash/LinkChooser.tsx");
  assert.match(chooser, /price=\{quoted \? \{ state: "ok", credits: quoted\.credits/);       // the API's estimate for the link
  assert.match(chooser, /consent=\{\{ checked: consent, onChange: setConsent, text: CONSENT \}\}/);
  assert.match(chooser, /api\("\/v1\/imports", \{ body: \{ url, consent: true, \.\.\.importRange\(\) \} \}\)/);     // the import consent, as recorded today
  assert.doesNotMatch(chooser, /Math\.ceil\(sec \/ 60\)|minutes\(duration\)/);                    // no price worked out in the browser
  assert.match(source("components/dash/setup/MakeView.tsx"), /useQuote\(known\?\.quote \? QUOTE : null/);
});

test("start card: a new project starts with every built polish option; Auto-edit is Coming soon, Open editor goes to the clips", () => {
  const polish = source("lib/polish.ts"), card = source("components/dash/SourceBar.tsx");
  assert.match(polish, /\{ id: "captions", name: "Captions", icon: "captions", built: true, option: "captions" \}/);
  assert.match(polish, /\{ id: "tighten", name: "Speech cleanup", icon: "mic", built: true, option: "tighten" \}/);
  assert.match(polish, /\{ id: "hook", name: "Hook", icon: "hook", built: true, option: "hook_overlay" \}/);
  assert.match(polish, /\{ id: "broll", name: "B-roll", icon: "image", built: false \}/);
  assert.match(card, /const ALL_POLISH = Object\.fromEntries\(POLISH\.filter\(\(p\) => p\.built\)/);     // unbuilt options are never sent
  assert.match(card, /polishQuery\(ALL_POLISH\)/);
  assert.match(card, /\{tab !== "clip" \? <div [^>]*>\s*<ComingSoonBadge \/>/);
  assert.match(card, /<Link href="\/dashboard\/library\/\?view=clips"[^>]*>\s*<Icon name="sliders" size=\{19\} \/>Open editor<\/Link>/);
  for (const f of ["components/dash/LinkChooser.tsx", "components/dash/setup/MakeView.tsx"]) assert.match(source(f), /polishLook\(window\.location\.search\)/, f);
});

test("job setup: only options the API lists are sent", () => {
  assert.match(setup, /return onlyListed\(listed, o\);/);
});

test("job setup: whole-recording transcript is off by default and only sent when listed", () => {
  assert.match(setup, /transcribe_whole: false \}/);
  assert.match(setup, /transcribe_whole: f\.transcribe_whole/);
  assert.match(setup, /\{has\("transcribe_whole"\) && <SettingRow icon="transcript" name="Whole-recording transcript"/);
  assert.match(setup, /on=\{f\.transcribe_whole\} label="Whole-recording transcript"/);
  assert.match(setup, /Transcribes the whole recording first so the AI can propose moments from the dialogue\. Takes longer on long VODs\. Same credit price\./);
  assert.doesNotMatch(setup, /viral|guaranteed|OpusClip|letter.?grade/i);

  // onlyListed is the send path: a key that is not on GET /v1/options is never invented.
  assert.match(source("lib/options.ts"), /Object\.entries\(options\)\.filter\(\(\[k\]\) => k in listed\)/);
  const onlyListed = (listed, options) => Object.fromEntries(Object.entries(options).filter(([k]) => k in listed));
  assert.deepEqual(onlyListed({ transcribe_whole: { type: "boolean", default: false } }, { transcribe_whole: true, extra: 1 }), { transcribe_whole: true });
  assert.deepEqual(onlyListed({ transcribe_whole: {} }, { transcribe_whole: false }), { transcribe_whole: false });
  assert.equal("transcribe_whole" in onlyListed({}, { transcribe_whole: true }), false);
});
