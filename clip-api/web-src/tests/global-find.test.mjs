// node --test tests/global-find.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  defaultFindBody, filterProjects, findProjectHref, isFindShortcut, projectIdFromLocation, searchPath,
} from "../lib/globalFind.ts";

test("project id comes from the dashboard ?id= query", () => {
  assert.equal(projectIdFromLocation("?id=up_abc&tool=find"), "up_abc");
  assert.equal(projectIdFromLocation(""), null);
});

test("search path encodes the query for GET /v1/uploads/{id}/search", () => {
  assert.equal(searchPath("up_1", "oh my god"), "/v1/uploads/up_1/search?q=oh%20my%20god&limit=10");
  assert.equal(searchPath("up_1", "  chase  ", 5), "/v1/uploads/up_1/search?q=chase&limit=5");
});

test("find project href opens the Find moments tab and keeps the query", () => {
  assert.equal(findProjectHref("up_9"), "/dashboard/project/?id=up_9&tool=find");
  assert.equal(findProjectHref("up_9", " police "), "/dashboard/project/?id=up_9&tool=find&q=police");
});

test("Cmd+K and Ctrl+K are the Find shortcut; plain K is not", () => {
  assert.equal(isFindShortcut({ metaKey: true, ctrlKey: false, altKey: false, shiftKey: false, key: "k" }), true);
  assert.equal(isFindShortcut({ metaKey: false, ctrlKey: true, altKey: false, shiftKey: false, key: "K" }), true);
  assert.equal(isFindShortcut({ metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, key: "k" }), false);
  assert.equal(isFindShortcut({ metaKey: true, ctrlKey: false, altKey: true, shiftKey: false, key: "k" }), false);
});

test("default find body matches Find moments defaults and can skip cutting clips", () => {
  const body = defaultFindBody("up_2", "  no way  ", true);
  assert.equal(body.upload_id, "up_2");
  assert.equal(body.query, "no way");
  assert.equal(body.make_clips, true);
  assert.equal(body.clip_length, 30);
  assert.equal(body.options.aspect, "9:16");
  assert.equal(defaultFindBody("up_2", "x", false).make_clips, false);
});

test("filterProjects matches filenames case-insensitively", () => {
  const projects = [{ filename: "GIA_Benchmark.mkv" }, { filename: "other.mp4" }];
  assert.deepEqual(filterProjects(projects, "gia").map((p) => p.filename), ["GIA_Benchmark.mkv"]);
  assert.equal(filterProjects(projects, "").length, 2);
});
