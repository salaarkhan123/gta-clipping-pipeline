// node --test tests/
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { findPlaceholders, MARKER } from "../scripts/check-legal.mjs";

const script = fileURLToPath(new URL("../scripts/check-legal.mjs", import.meta.url));
const site = (pages) => {
  const dir = mkdtempSync(join(tmpdir(), "check-legal-"));
  for (const [path, html] of Object.entries(pages)) {
    mkdirSync(join(dir, path, ".."), { recursive: true });
    writeFileSync(join(dir, path), html);
  }
  return dir;
};
const run = (dir, env = {}) => spawnSync(process.execPath, [script, dir], { env: { ...process.env, LEGAL_PREVIEW: "", ...env }, encoding: "utf8" });

test("a production build fails while a page shows an [OWNER …] placeholder", () => {
  const dir = site({ "terms/index.html": `<p>Run by <mark ${MARKER}="">[OWNER: legal entity name]</mark></p>`, "index.html": "<h1>Home</h1>" });
  try {
    assert.deepEqual(findPlaceholders(dir), ["terms/index.html"]);
    const r = run(dir);
    assert.equal(r.status, 1);
    assert.match(r.stderr, /terms\/index\.html/);
  } finally { rmSync(dir, { recursive: true }); }
});

test("a build with no placeholder passes, and a preview build is allowed to show them", () => {
  const clean = site({ "terms/index.html": "<p>This policy is being finalised.</p>" });
  const draft = site({ "terms/index.txt": `{"${MARKER}":""}` });
  try {
    assert.deepEqual(findPlaceholders(clean), []);
    assert.equal(run(clean).status, 0);
    assert.equal(run(draft).status, 1);
    assert.equal(run(draft, { LEGAL_PREVIEW: "1" }).status, 0);
  } finally { rmSync(clean, { recursive: true }); rmSync(draft, { recursive: true }); }
});

test("npm run build runs the check after next build", () => {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(pkg.scripts.build, "next build && node scripts/check-legal.mjs out");
});
