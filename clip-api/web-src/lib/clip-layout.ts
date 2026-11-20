export type ClipLayout = "grid" | "list";
export const CLIP_LAYOUT_KEY = "clutchclips.clipLayout";

export function parseClipLayout(raw: string | null | undefined): ClipLayout {
  return raw === "list" ? "list" : "grid";
}
