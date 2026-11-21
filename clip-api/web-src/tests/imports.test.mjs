// Import progress in words: the stage names #194 sends (reading, downloading, copying, merging) and the older ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { importStep, optionsForUpload, takedownBody } from "../lib/imports.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("each import stage reads as words", () => {
  assert.equal(importStep({ status: "RUNNING", stage: "reading" }), "Reading the link");
  assert.equal(importStep({ status: "RUNNING", stage: "merging" }), "Joining picture and sound");
  assert.equal(importStep({ status: "RUNNING", stage: "importing" }), "Downloading the video");
  assert.equal(importStep({ status: "QUEUED", stage: null }), "Waiting to start");
  assert.equal(importStep({ status: "RUNNING", stage: "something-new" }, "Importing"), "Importing");
  assert.equal(importStep(null), "Getting the video");
});

test("downloading shows bytes when the API sends them", () => {
  assert.equal(importStep({ status: "RUNNING", stage: "downloading", bytes_done: 12e6, bytes_total: 24e6 }), "Downloading the video · 12.0 of 24.0 MB");
  assert.equal(importStep({ status: "RUNNING", stage: "downloading", bytes_done: 0, bytes_total: null }), "Downloading the video");
});

// A link the site refuses (YouTube's bot check, a failed download): the settings the user chose stay, and "Upload
// original video" runs the same job on the uploaded file.
test("the same options on the uploaded original: the part picked for the import becomes the job's range", () => {
  const chosen = { duration: "30-60", limit: 5, caption_style: "impact", template: "gta", range: null };
  assert.deepEqual(optionsForUpload(chosen, { start: 600, end: 660 }), { ...chosen, range: { start: 600, end: 660 } });
  assert.deepEqual(optionsForUpload(chosen, null), chosen);              // no part was picked: nothing changes
  assert.equal(chosen.range, null);                                      // the chosen options are not modified
});

test("self-service takedown body: consent and exactly one of url or all_imports", () => {
  assert.deepEqual(takedownBody({ consent: true, url: "https://kick.com/x" }), { consent: true, url: "https://kick.com/x" });
  assert.deepEqual(takedownBody({ consent: true, all_imports: true }), { consent: true, all_imports: true });
  assert.throws(() => takedownBody({ consent: true, url: "", all_imports: false }), /Choose a source URL/);
});

test("a refused or failed import keeps the settings and offers Upload original video", () => {
  const chooser = source("components/dash/LinkChooser.tsx"), setup = source("components/dash/setup/JobSetup.tsx");
  // Every way an import ends badly after the settings were chosen marks it failed: the start call refused, the
  // link clip job failed, the plain import failed. A cancel does not.
  assert.match(chooser, /setProblem\(e\.message\); setFailed\(e\.status === 422 \|\| e\.status === 503\);/);
  assert.match(chooser, /setFailed\(job\.status === "FAILED"\); return;/);
  assert.match(chooser, /setFailed\(imp\.status === "FAILED"\);/);
  assert.match(chooser, /if \(e instanceof ApiError && e\.status === 422\) \{ setProblem\(e\.message\); setFailed\(true\); \}/);
  // The button is on the job-setup screen (which stays as it is: no navigation, no reset) and on the other tools' bar.
  assert.match(chooser, /<Icon name="upload" size=\{16\} \/>Upload original video<\/button>\}\s*<p[^>]*>Your settings stay as they are, and nothing was charged for the import\.<\/p>/);
  assert.match(chooser, /afterProblem=\{uploadOriginal\} busy=\{!!up\}/);
  assert.match(setup, /\{problem && <p className="error m-0" role="alert">\{problem\}<\/p>\}\s*\{afterProblem\}/);
  assert.match(chooser, /\{problem && <p className="error" role="alert">\{problem\}<\/p>\}\s*\{uploadOriginal\}/);
  // The upload then asks for the same job: the same request builder, with the picked part kept as the job's range.
  assert.match(chooser, /useUpload\(\(u\) => original\.current \? uploaded\(u\) : router\.push\(/);
  assert.match(chooser, /options: whole \? optionsForUpload\(setup\.current, picked_range\) : clipOptions\(setup\.current\)/);
  // The price comes from the server before anything starts: no more than the one already shown starts at once,
  // anything else is shown and confirmed. Nothing is worked out in the browser.
  assert.match(chooser, /const q = await api<\{ credits_reserved\?: number \}>\("\/v1\/clips\/quote", \{ body \}\)\.catch\(\(\) => null\);\s*const credits = /);
  assert.match(chooser, /if \(credits !== undefined && quoted && credits <= quoted\.credits\) \{ await runTool\(u, true\); return; \}\s*setConfirm\(\{ upload: u, credits, original: true \}\);/);
  assert.match(chooser, /onClick=\{\(\) => runTool\(confirm\.upload, !!confirm\.original\)\}>Start<\/button>/);
  // A link refused before any setting was chosen: the same button, and the upload opens the tool with the template picked on Home.
  assert.equal(chooser.match(/Upload original video<\/button>/g).length, 2);
  assert.doesNotMatch(chooser, /Upload the file instead<\/button>/);
  assert.match(chooser, /&tool=\$\{kind\}\$\{template \? `&template=\$\{encodeURIComponent\(template\)\}` : ""\}/);
});
