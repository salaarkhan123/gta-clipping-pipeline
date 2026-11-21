// Refuses a production build that would publish unconfirmed facts: any built page (HTML or its RSC payload) that
// still renders an [OWNER …] placeholder, marked by components/LegalPage.tsx with `data-owner-placeholder`.
// `npm run build` runs it after `next build`. LEGAL_PREVIEW=1 builds the drafts for review and skips it.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { pathToFileURL } from "node:url";

export const MARKER = "data-owner-placeholder";

// Every built file under `dir` that contains the placeholder marker, relative to `dir`.
export function findPlaceholders(dir) {
  const hits = [];
  const walk = (d) => {
    for (const name of readdirSync(d)) {
      const p = join(d, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(html|txt)$/.test(name) && readFileSync(p, "utf8").includes(MARKER)) hits.push(relative(dir, p));
    }
  };
  walk(dir);
  return hits.sort();
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  if (process.env.LEGAL_PREVIEW === "1") {
    console.log("check-legal: LEGAL_PREVIEW=1, draft legal pages built for review. Do not deploy this build.");
    process.exit(0);
  }
  const out = process.argv[2] || "out";
  const hits = findPlaceholders(out);
  if (hits.length) {
    console.error(`check-legal: ${hits.length} built file(s) still show an [OWNER …] placeholder; a production build must not:`);
    for (const h of hits) console.error(`  ${h}`);
    process.exit(1);
  }
  console.log("check-legal: no [OWNER …] placeholder in the build.");
}
