// Every API path the website's source names is declared in lib/api-contract.json, which the backend checks against
// its own /openapi.json (clip-api/tests/test_web_contract.py). A new call without a contract entry fails here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const contract = JSON.parse(readFileSync(join(root, "lib/api-contract.json"), "utf8"));

function files(dir) {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.(ts|tsx)$/.test(f) ? [p] : [];
  });
}

// "/v1/clips/${clip.id}/feedback" -> "/v1/clips/{}/feedback"; query strings and trailing slashes dropped.
export function usedPaths(source) {
  const out = new Set();
  for (const m of source.matchAll(/(?:["'`]|\})(\/v1\/(?:[^"'`$?\s]|\$\{(?:[^{}]|\{[^{}]*\})*\})*)/g)) {
    const path = m[1].replace(/\$\{(?:[^{}]|\{[^{}]*\})*\}/g, "{}").replace(/\/+$/, "");
    if (path !== "/v1") out.add(path);
  }
  return out;
}

const declared = contract.routes.map((r) => r.path.replace(/\{[^}]+\}/g, "{}"));
// A used segment "{}" stands for any declared segment ("/v1/auth/{}" is /v1/auth/signup and /v1/auth/login).
const matches = (used) => declared.some((d) => {
  const a = used.split("/"), b = d.split("/");
  return a.length === b.length && a.every((s, i) => s === b[i] || s === "{}" || b[i] === "{}");
});

test("every API path the site uses is in the contract", () => {
  const missing = [];
  for (const f of ["app", "components", "lib"].flatMap((d) => files(join(root, d)))) {
    for (const p of usedPaths(readFileSync(f, "utf8"))) if (!matches(p)) missing.push(`${p} (${f.slice(root.length)})`);
  }
  assert.deepEqual(missing, [], "add these to lib/api-contract.json (route, method, body and query fields)");
});

test("the scanner reads template paths", () => {
  const src = 'api(`/v1/clips/${clip.id}/feedback`); fetch(`${API}/v1/clips/${c.id}/subtitles?format=${f}`); api("/v1/imports?limit=5")';
  assert.deepEqual([...usedPaths(src)].sort(), ["/v1/clips/{}/feedback", "/v1/clips/{}/subtitles", "/v1/imports"]);
});

test("every contract route is well formed", () => {
  for (const r of contract.routes) {
    assert.match(r.method, /^(GET|POST|PATCH|PUT|DELETE)$/);
    assert.match(r.path, /^\/(v1\/|health$)/);
  }
});
