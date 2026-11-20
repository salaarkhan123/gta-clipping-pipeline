// Upload soft-delete + self-service import takedown UI (CPR-19 A3-FE). Routes land with PR #239; until then the
// UI must surface ApiError and never invent success.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { takedownBody } from "../lib/imports.ts";
import { uploadDeletePath } from "../lib/uploads.ts";

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("delete path encodes the upload id", () => {
  assert.equal(uploadDeletePath("up_1"), "/v1/uploads/up_1");
  assert.equal(uploadDeletePath("a/b"), "/v1/uploads/a%2Fb");
});

test("takedown body requires consent and exactly one target", () => {
  assert.throws(() => takedownBody({ consent: false, url: "https://cdn.test/v.mp4" }), /consent/i);
  assert.throws(() => takedownBody({ consent: true }), /Choose a source URL/);
  assert.throws(() => takedownBody({ consent: true, url: "https://cdn.test/v.mp4", all_imports: true }), /not both/i);
  assert.deepEqual(takedownBody({ consent: true, url: "  https://cdn.test/v.mp4  " }),
    { consent: true, url: "https://cdn.test/v.mp4" });
  assert.deepEqual(takedownBody({ consent: true, all_imports: true }), { consent: true, all_imports: true });
});

test("delete control: explicit confirm, DELETE via api helper, errors shown, success only after deleted:true", () => {
  const ctrl = source("components/dash/DeleteUploadControl.tsx");
  assert.match(ctrl, /uploadDeletePath\(uploadId\)/);
  assert.match(ctrl, /method: "DELETE"/);
  assert.match(ctrl, /from "@\/lib\/api"/);
  assert.match(ctrl, /setAsk\(true\)/);
  assert.match(ctrl, /aria-label=\{`Delete \$\{name \|\| "this video"\}\?`\}/);
  assert.match(ctrl, /\{busy \? "Deleting…" : "Delete"\}/);
  assert.match(ctrl, /if \(!r\?\.deleted\) throw/);
  assert.match(ctrl, /setProblem\(e instanceof Error \? e\.message/);
  assert.doesNotMatch(ctrl, /window\.confirm/);
});

test("ProjectCard and assets wire delete then refresh the list", () => {
  const card = source("components/dash/ProjectCard.tsx");
  assert.match(card, /DeleteUploadControl/);
  assert.match(card, /onDeleted=\{onDeleted\}/);
  assert.match(source("components/dash/ProjectCard.tsx"), /onDeleted\?: \(uploadId: string\) => void/);
  const home = source("app/dashboard/page.tsx");
  assert.match(home, /onDeleted=\{\(id\) => setProjects/);
  const library = source("app/dashboard/library/page.tsx");
  assert.match(library, /onDeleted=\{\(id\) => setProjects/);
  const assets = source("app/dashboard/assets/page.tsx");
  assert.match(assets, /DeleteUploadControl/);
  assert.match(assets, /onDeleted=\{\(id\) => setList/);
});

test("import takedown: consent checkbox, confirm step, POST /v1/imports/takedown, no fake success", () => {
  const form = source("components/dash/ImportTakedown.tsx");
  assert.match(form, /takedownBody/);
  assert.match(form, /api\("\/v1\/imports\/takedown"/);
  assert.match(form, /from "@\/lib\/imports"/);
  assert.match(form, /type="checkbox" checked=\{consent\}/);
  assert.match(form, /setAsk\(true\)/);
  assert.match(form, /Confirm removal/);
  assert.match(form, /disabled=\{busy \|\| !consent\}/);
  assert.match(form, /all_imports: true/);
  assert.match(form, /setProblem\(e instanceof ApiError \|\| e instanceof Error \? e\.message/);
  assert.doesNotMatch(form, /window\.confirm/);
  // Public copyright report form and admin cases stay separate.
  assert.doesNotMatch(form, /\/v1\/trust\/reports/);
  assert.doesNotMatch(form, /\/v1\/admin\/trust/);
});

test("takedown surfaces on imports home and trust cases; account menu links there", () => {
  assert.match(source("components/dash/SourceBar.tsx"), /ImportTakedown/);
  assert.match(source("app/dashboard/cases/page.tsx"), /id="remove-imports"/);
  assert.match(source("app/dashboard/cases/page.tsx"), /ImportTakedown/);
  assert.match(source("components/dash/shell/AccountMenu.tsx"),
    /href="\/dashboard\/cases\/#remove-imports"[^>]*>Remove my imports</);
});

test("api contract lists delete and takedown as optional until #239 lands on this API", () => {
  const contract = JSON.parse(source("lib/api-contract.json"));
  const del = contract.routes.find((r) => r.method === "DELETE" && r.path === "/v1/uploads/{upload_id}");
  const td = contract.routes.find((r) => r.method === "POST" && r.path === "/v1/imports/takedown");
  assert.equal(del?.optional, true);
  assert.equal(td?.optional, true);
  assert.deepEqual(td.body, ["consent"]);
  assert.ok(td.optional_body.includes("url") && td.optional_body.includes("all_imports"));
  assert.match(source("lib/uploads.ts"), /\/v1\/uploads\/\$\{encodeURIComponent\(uploadId\)\}/);
  assert.match(source("components/dash/DeleteUploadControl.tsx"), /method: "DELETE"/);
  assert.match(source("components/dash/ImportTakedown.tsx"), /api\("\/v1\/imports\/takedown"/);
});
