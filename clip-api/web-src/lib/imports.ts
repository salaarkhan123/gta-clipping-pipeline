// What an import is doing, in words, for every screen that follows one (the link chooser, the import box).
// `stage` is GET /v1/imports/{id} `stage`, or the `import` object on a URL-clipping job: "reading" (asking the site
// about the video), "downloading", "copying", "merging" (joining picture and sound), then "checking" and "storing".
// "importing" is the clip job's own stage while it waits for its import (and older APIs' download stage).
const STAGES: Record<string, string> = {
  queued: "Waiting to start", reading: "Reading the link", downloading: "Downloading the video", copying: "Copying the video",
  merging: "Joining picture and sound", importing: "Downloading the video", checking: "Checking the video", storing: "Saving the video",
  done: "Done",
};

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
