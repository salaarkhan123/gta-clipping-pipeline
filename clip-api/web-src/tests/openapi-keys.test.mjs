// E2: dashboard keys page points at public OpenAPI docs; site stays on /v1 (no private website API).
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { usedPaths } from "./api-contract.test.mjs";

const root = fileURLToPath(new URL("..", import.meta.url));
const source = (path) => readFileSync(join(root, path), "utf8");

function files(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx)$/.test(f) ? [p] : [];
  });
}

test("keys page links to /docs and names core public endpoints", () => {
  const page = source("app/dashboard/keys/page.tsx");
  assert.match(page, /href=\{\`\$\{API\}\/docs\`\}/);
  assert.match(page, /OpenAPI reference/);
  assert.match(page, /\/openapi\.json/);
  for (const path of ["/v1/uploads", "/v1/clips", "/v1/options", "/v1/credits", "/v1/keys"]) {
    assert.match(page, new RegExp(path.replace(/\//g, "\\/")));
  }
  assert.match(page, /same public/);
  assert.doesNotMatch(page, /\/v1\/admin\//);
});

test("account menu API docs link targets /docs", () => {
  assert.match(source("components/dash/shell/AccountMenu.tsx"), /href=\{\`\$\{API\}\/docs\`\}/);
});

test("api-contract routes are public /v1 (plus health); no website-only private API", () => {
  const contract = JSON.parse(source("lib/api-contract.json"));
  const paths = contract.routes.map((r) => r.path);
  assert.ok(paths.every((p) => p === "/health" || p.startsWith("/v1/")));
  assert.ok(!paths.some((p) => p.startsWith("/private/") || p.startsWith("/internal/") || p.startsWith("/website/")));
  // Admin trust cases are public OpenAPI routes with admin auth — not a separate website backend.
  assert.ok(paths.some((p) => p.startsWith("/v1/admin/trust/")));
  // Site discovers optional routes from the public schema.
  assert.match(source("lib/routes.ts"), /api<Spec>\("\/openapi\.json"/);
  // Every /v1 path the site source names is still under /v1 (scanner only matches /v1).
  const used = new Set();
  for (const f of ["app", "components", "lib"].flatMap((d) => files(join(root, d)))) {
    for (const p of usedPaths(readFileSync(f, "utf8"))) used.add(p);
  }
  assert.ok([...used].every((p) => p.startsWith("/v1/")));
  assert.ok(used.size > 20);
});
