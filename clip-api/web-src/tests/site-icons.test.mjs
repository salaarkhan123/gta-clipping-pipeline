// node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const web = fileURLToPath(new URL("../", import.meta.url));
const file = (path) => readFileSync(join(web, path));

test("the tab icon is the header's logo, in every format a browser asks for", () => {
  const svg = file("app/icon.svg").toString();
  assert.match(svg, /#b8ff3c/);
  assert.doesNotMatch(svg, /#ff4f8b/i);

  const ico = file("app/favicon.ico");
  assert.deepEqual([...ico.subarray(0, 4)], [0, 0, 1, 0]);
  const sizes = Array.from({ length: ico.readUInt16LE(4) }, (_, i) => ico[6 + i * 16] || 256).sort((a, b) => a - b);
  assert.deepEqual(sizes, [16, 32, 48]);

  const png = file("app/apple-icon.png");
  assert.equal(png.subarray(1, 4).toString(), "PNG");
  assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [180, 180]);
});
