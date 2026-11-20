// Global Find (Cmd+K / Ctrl+K): pure helpers for the dashboard shell palette.
// Instant matches use GET /v1/uploads/{id}/search; indexing and clip cuts use POST /v1/find.

export type FindMatch = { start: number; text: string; kind?: string };

export type GlobalFindPhase =
  | { status: "idle" }
  | { status: "searching" }
  | { status: "matches"; query: string; uploadId: string; matches: FindMatch[] }
  | { status: "empty"; query: string; uploadId: string }
  | { status: "needs_index"; query: string; uploadId: string }
  | { status: "starting"; query: string; uploadId: string }
  | { status: "error"; message: string };

export const projectIdFromLocation = (search: string): string | null => {
  try { return new URLSearchParams(search).get("id"); } catch { return null; }
};

// Soft-nav handoff: tool=find opens the tab; q prefills the query (max 200).
export type FindHandoff = { openFind: boolean; query: string };
export type FindHandoffState = { view: "clips" | "find"; query: string };

export const findHandoffFromSearch = (search: string): FindHandoff => {
  const params = new URLSearchParams(search);
  return {
    openFind: params.get("tool") === "find",
    query: (params.get("q") || "").slice(0, 200),
  };
};

// Re-apply tool/q after the project page is already mounted (same-path router.push).
export const applyFindHandoff = (current: FindHandoffState, search: string): FindHandoffState => {
  const handoff = findHandoffFromSearch(search);
  if (!handoff.openFind) return current;
  return { view: "find", query: handoff.query };
};

export const searchPath = (uploadId: string, query: string, limit = 10) =>
  `/v1/uploads/${uploadId}/search?q=${encodeURIComponent(query.trim())}&limit=${limit}`;

export const findProjectHref = (uploadId: string, query?: string) => {
  const q = new URLSearchParams({ id: uploadId, tool: "find" });
  const trimmed = query?.trim();
  if (trimmed) q.set("q", trimmed);
  return `/dashboard/project/?${q}`;
};

export const isFindShortcut = (e: KeyboardEvent) =>
  (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k";

export const shortcutLabel = () =>
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "") ? "⌘K" : "Ctrl+K";

// Same framing FindPanel sends when the user skips the options form.
export const defaultFindBody = (uploadId: string, query: string, makeClips: boolean) => ({
  upload_id: uploadId,
  query: query.trim(),
  mode: "auto" as const,
  max_results: 5,
  make_clips: makeClips,
  clip_length: 30,
  options: {
    vertical: true,
    aspect: "9:16",
    layout: "auto",
    facecam_region: "auto",
    zoom: 1,
    chat_region: "none",
    caption_style: "pop",
    censor: false,
    captions: true,
  },
});

export const filterProjects = <T extends { filename?: string }>(projects: T[], needle: string): T[] => {
  const q = needle.trim().toLowerCase();
  if (!q) return projects;
  return projects.filter((p) => (p.filename || "").toLowerCase().includes(q));
};
