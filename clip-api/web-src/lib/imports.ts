// What an import is doing, in words, for every screen that follows one (the link chooser, the import box).
// `stage` is GET /v1/imports/{id} `stage`, or the `import` object on a URL-clipping job: "reading" (asking the site
// about the video), "downloading", "copying", "merging" (joining picture and sound), then "checking" and "storing".
// "importing" is the clip job's own stage while it waits for its import (and older APIs' download stage).
const STAGES: Record<string, string> = {
  queued: "Waiting to start", reading: "Reading the link", downloading: "Downloading the video", copying: "Copying the video",
  merging: "Joining picture and sound", importing: "Downloading the video", checking: "Checking the video", storing: "Saving the video",
  done: "Done",
};

// Self-service import takedown body (POST /v1/imports/takedown, PR #239). Account-scoped; consent required;
// exactly one of url or all_imports. Pure so node tests can import it; the form calls `api` with this body.
export type TakedownChoice = { consent: boolean; url?: string; all_imports?: boolean };
export type TakedownBody = { consent: true; url: string } | { consent: true; all_imports: true };

export function takedownBody(input: TakedownChoice): TakedownBody {
  if (input.consent !== true) throw new Error("Tick the consent box to remove imported videos from this account.");
  const url = (input.url || "").trim();
  const all = input.all_imports === true;
  if (!!url === all) {
    throw new Error("Choose a source URL or remove all of your imports — not both, and not neither.");
  }
  return url ? { consent: true, url } : { consent: true, all_imports: true };
}

// A link that could not be imported: the user uploads the original file and the same job is asked for on it. The
// options are the ones chosen for the link. A part picked for the import (sent there as start_sec / end_sec, with
// `range` null) becomes the job's own `range` on the upload, so the same part of the video is clipped.
export function optionsForUpload<T extends Record<string, unknown>>(options: T, picked: { start: number; end: number } | null | undefined): T {
  return picked ? { ...options, range: { start: picked.start, end: picked.end } } : options;
}

const mb = (n: number) => Math.max(0.1, n / 1e6).toFixed(n >= 1e8 ? 0 : 1);

// "Downloading the video · 12.0 of 24.0 MB" when the API sends byte counts, else just the stage.
export function importStep(imp: { status?: string; stage?: string | null; bytes_done?: number | null; bytes_total?: number | null } | null | undefined,
  fallback = "Getting the video"): string {
  if (!imp) return fallback;
  if (imp.status === "QUEUED") return STAGES.queued;
  const text = (imp.stage && STAGES[imp.stage]) || fallback;
  const done = imp.bytes_done, total = imp.bytes_total;
  return typeof done === "number" && typeof total === "number" && total > 0 && imp.stage === "downloading"
    ? `${text} · ${mb(done)} of ${mb(total)} MB` : text;
}
