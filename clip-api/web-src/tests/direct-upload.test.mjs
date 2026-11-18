// node --test tests/   The site's resumable upload against a fake API and bucket.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { directUpload } from "../lib/directUpload.ts";

const MiB = 1024 * 1024;

// The API's four endpoints over an in-memory bucket. `drop` makes the bucket refuse that many PUTs of a part.
function fakeServer({ partSize = 5 * MiB, drop = {} } = {}) {
  const s = { stored: new Map(), calls: [], puts: [], aborted: 0, started: 0, alive: true };
  const count = (size) => Math.ceil(size / partSize);
  let size = 0;
  const err = (code) => Object.assign(new Error(code), { code });
  s.call = async (path, body) => {
    s.calls.push(path);
    if (path === "/v1/uploads/multipart") {
      s.started++; size = body.size_bytes; s.alive = true; s.stored.clear();
      return { upload_token: `tok${s.started}`, upload_id: "upl_1", part_size: partSize, part_count: count(size) };
    }
    if (!s.alive) throw err("upload_gone");
    if (path.endsWith("/parts")) {
      const all = Array.from({ length: count(size) }, (_, i) => i + 1);
      const todo = all.filter((n) => !s.stored.has(n)).slice(0, 2);       // two per call: the client must loop
      return { part_size: partSize, part_count: all.length, done: all.filter((n) => s.stored.has(n)),
               parts: todo.map((n) => ({ part_number: n, size: n === all.length ? size - partSize * (all.length - 1) : partSize, url: `put:${n}` })) };
    }
    if (path.endsWith("/complete")) {
      if (s.stored.size !== count(size)) throw err("upload_incomplete");
      s.alive = false;
      return { upload_id: "upl_1", size_bytes: size };
    }
    if (path.endsWith("/abort")) { s.aborted++; s.alive = false; return null; }
  };
  s.put = (url, blob, onProgress) => {
    const n = Number(url.split(":")[1]);
    s.puts.push(n);
    let abort = () => {};
    const promise = new Promise((resolve, reject) => {
      abort = () => reject(new Error("aborted"));
      if (drop[n] > 0) { drop[n]--; reject(new Error("network")); return; }
      onProgress(blob.size / 2);
      s.stored.set(n, blob.size);
      setTimeout(resolve, 1);
    });
    return { promise, abort: () => abort() };
  };
  return s;
}

const memory = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k), m }; };
const file = (bytes, name = "vod.mp4") => Object.assign(new Blob([new Uint8Array(bytes)]), { name, lastModified: 1 });
const deps = (s, saved) => ({ call: s.call, put: s.put, saved, wait: async () => {},
                              error: (code, message) => Object.assign(new Error(message), { code }) });

test("every part is sent once, in batches, then the upload is completed", async () => {
  const s = fakeServer(), seen = [];
  const up = await directUpload(file(11 * MiB), (f) => seen.push(f), deps(s, memory())).promise;
  assert.equal(up.upload_id, "upl_1");
  assert.deepEqual([...s.stored.entries()].sort((a, b) => a[0] - b[0]), [[1, 5 * MiB], [2, 5 * MiB], [3, MiB]]);
  assert.deepEqual(s.puts.sort(), [1, 2, 3]);
  assert.equal(s.calls.at(-1), "/v1/uploads/multipart/complete");
  assert.equal(seen.at(-1), 1);
  assert.ok(seen.every((f, i) => i === 0 || f >= 0));
});

test("a failed part is retried", async () => {
  const s = fakeServer({ drop: { 2: 2 } });
  await directUpload(file(11 * MiB), () => {}, deps(s, memory())).promise;
  assert.equal(s.puts.filter((n) => n === 2).length, 3);
});

test("after a dropped connection the same file resumes where it stopped", async () => {
  const s = fakeServer({ drop: { 3: 3 } }), saved = memory();
  await assert.rejects(directUpload(file(11 * MiB), () => {}, deps(s, saved)).promise, { code: "network" });
  assert.equal(s.aborted, 0);                               // the parts stay in the bucket
  assert.equal(saved.m.size, 1);
  s.puts.length = 0;
  const progress = [];
  await directUpload(file(11 * MiB), (f) => progress.push(f), deps(s, saved)).promise;
  assert.equal(s.started, 1);                               // the same upload, not a new one
  assert.deepEqual(s.puts, [3]);                            // only the missing part
  assert.ok(progress[0] >= 10 / 11 - 1e-9);                 // progress starts from what was stored
  assert.equal(saved.m.size, 0);
});

test("an expired upload starts over", async () => {
  const s = fakeServer(), saved = memory();
  saved.setItem(`cc_upload:vod.mp4:${11 * MiB}:1`, "old-token");
  s.alive = false;
  await directUpload(file(11 * MiB), () => {}, deps(s, saved)).promise;
  assert.equal(s.started, 1);
});

test("cancel aborts the parts and rejects with aborted", async () => {
  const s = fakeServer(), saved = memory();
  const run = directUpload(file(11 * MiB), () => run.abort(), deps(s, saved));
  await assert.rejects(run.promise, { code: "aborted" });
  await new Promise((r) => setTimeout(r, 5));
  assert.equal(s.aborted, 1);
  assert.ok(!s.calls.includes("/v1/uploads/multipart/complete"));
  assert.equal(saved.m.size, 0);
});

test("the site falls back to the API upload when the server has no bucket", () => {
  const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
  assert.match(api, /e\.code === "direct_upload_unavailable"/);
  assert.match(api, /current = uploadThroughApi\(file, onProgress\)/);
});
