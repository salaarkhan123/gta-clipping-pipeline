// node scripts/design-audit.mjs [dir]   Counts the design values written into the source (app/ and components/ under
// `dir`, default the current folder): how many different font sizes, corner radii, colour literals, hand-built
// buttons and score marks exist. Run it before and after a design change; fewer distinct values is more consistent.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const root = process.argv[2] || ".";
const files = (dir) => readdirSync(dir).flatMap((n) => { const p = join(dir, n);
  return statSync(p).isDirectory() ? files(p) : /\.(tsx?|css)$/.test(n) ? [p] : []; });
const all = ["app", "components"].flatMap((d) => files(join(root, d))).filter((f) => !f.includes("/design/"));
const text = Object.fromEntries(all.map((f) => [f, readFileSync(f, "utf8")]));
const count = (re, pick = (m) => m[0]) => { const seen = new Map();
  for (const t of Object.values(text)) for (const m of t.matchAll(re)) { const k = pick(m); seen.set(k, (seen.get(k) || 0) + 1); }
  return seen; };
const top = (m, n = 8) => [...m].sort((a, b) => b[1] - a[1]).slice(0, n).map(([k, v]) => `${k} x${v}`).join(", ");

const sizes = count(/text-\[(\d+(?:\.\d+)?)px\]|font-size:\s*(\d+(?:\.\d+)?)px|font:\s*[^;]*?\b(\d+(?:\.\d+)?)px/g, (m) => `${m[1] || m[2] || m[3]}px`);
const radii = count(/rounded(?:-[trbl]{1,2})?-\[(\d+(?:\.\d+)?)px\]|border-radius:\s*(\d+(?:\.\d+)?)px/g, (m) => `${m[1] || m[2]}px`);
const hex = count(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/g, (m) => m[0].toLowerCase());
const rgba = count(/rgba?\([^)]*\)/g, (m) => m[0].replace(/\s+/g, ""));
const borders = count(/\bborder-solid\b|\bborder:\s*\d/g, () => "border");
// A hand-built button: a <button> or link styled with its own background and radius instead of the shared .btn classes.
const handButtons = count(/<(?:button|Link|a)\b[^>]*className=(?:"|\{`)(?![^"`]*\bbtn\b)[^"`]*\brounded-[^"`]*\bbg-(?!transparent)[^"`]*/g, () => "hand-built");
const sharedButtons = count(/className=(?:"|\{`)[^"`]*\bbtn\b/g, () => "shared");
// Places that draw a score number themselves (lime, tabular) rather than through one component.
const scoreFiles = Object.entries(text).filter(([, t]) => /tabular-nums[^"`]*text-lime|text-lime[^"`]*tabular-nums|\.score\b|score-badge/.test(t)).map(([f]) => f.replace(root + "/", ""));
const scoreComponents = Object.entries(text).filter(([, t]) => /export function (ScoreOverlay|Score|AiRating|RatingBadge|ScoreBadge)\b/.test(t)).map(([f]) => f.replace(root + "/", ""));

console.log(`files scanned: ${all.length}`);
console.log(`distinct font sizes: ${sizes.size}  (most used: ${top(sizes)})`);
console.log(`distinct corner radii: ${radii.size}  (most used: ${top(radii)})`);
console.log(`distinct hex colours: ${hex.size}; distinct rgb()/rgba() literals: ${rgba.size}`);
console.log(`explicit borders: ${[...borders.values()][0] || 0}`);
console.log(`buttons: ${[...sharedButtons.values()][0] || 0} use the shared classes, ${[...handButtons.values()][0] || 0} are hand-built`);
console.log(`files that draw a score number by hand: ${scoreFiles.length}  ${scoreFiles.join(", ")}`);
console.log(`score components: ${scoreComponents.length}  ${scoreComponents.join(", ")}`);
