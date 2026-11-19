// Import progress in words: the stage names #194 sends (reading, downloading, copying, merging) and the older ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { importStep } from "../lib/imports.ts";

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
