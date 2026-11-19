// node --test tests/
// The site names a link-import platform only once it is verified in production: VERIFIED_PLATFORMS in
// lib/platforms.ts is the one list, and the copy is built from it.
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { linkPhrase, pastePrompt, platformNames, VERIFIED_PLATFORMS } from "../lib/platforms.ts";

const root = fileURLToPath(new URL("../", import.meta.url));
const files = (dir) => readdirSync(join(root, dir)).flatMap((n) => {
  const p = join(dir, n);
  return statSync(join(root, p)).isDirectory() ? files(p) : /\.tsx?$/.test(n) ? [p] : [];
});

// Every import platform the backend knows (app/ingest/sources.py), by the name the copy would use.
const PLATFORMS = ["Twitch", "Kick", "YouTube", "Google Drive", "Dropbox"];
// Not copy about link imports: the link chooser's label for a link already pasted, and the coming-soon posting
// destinations ("YouTube Shorts"). The privacy notice and terms follow the rule too (owner decision).
const NOT_COPY = ["components/dash/LinkChooser.tsx"];

test("the copy names only verified platforms (none today)", () => {
  assert.deepEqual([...VERIFIED_PLATFORMS], []);
  for (const f of [...files("app"), ...files("components")].filter((f) => !NOT_COPY.includes(f))) {
    // The dashboard's source picker offers Google Drive and Dropbox only when GET /v1/imports/sources lists them;
    // those two entries are the app's own options, left for the owner to decide on (#184 follow-up notes).
    const text = readFileSync(join(root, f), "utf8").replace(/\/\/.*$/gm, "").replace(/YouTube Shorts/g, "")
      .split("\n").filter((l) => !/platform: "(gdrive|dropbox)"/.test(l)).join("\n");
    for (const name of PLATFORMS.filter((n) => !VERIFIED_PLATFORMS.includes(n))) assert.doesNotMatch(text, new RegExp(`\\b${name}\\b`), `${f} names ${name}`);
  }
});

test("the link prompts read right with none, one or several platforms", () => {
  assert.equal(pastePrompt([]), "Paste a recorded video link or upload a file.");
  assert.equal(pastePrompt(["Twitch"]), "Paste a recorded Twitch video link or upload a file.");
  assert.equal(pastePrompt(["YouTube", "Twitch", "Kick"]), "Paste a recorded YouTube, Twitch or Kick video link or upload a file.");
  assert.equal(linkPhrase([]), "a recorded video link");
  assert.equal(platformNames(["Twitch", "Kick"]), "Twitch or Kick");
});

test("the paste bars and placeholders use the shared prompt", () => {
  for (const f of ["components/StartInput.tsx", "components/landing/demos/VodToClips.tsx"])
    assert.match(readFileSync(join(root, f), "utf8"), /pastePrompt\(\)/, f);
});
