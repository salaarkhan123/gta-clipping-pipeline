"use client";
// Site media made by the media pipeline: public/media/<section>/manifest.json lists that section's files, which sit
// next to it. A section with no manifest yet (or an empty one) gets null, and the page shows its placeholder
// (components/site/MediaFrame.tsx). Sections match ~/ClutchClips-eval/website-media/ folder names.
import { useEffect, useState } from "react";

export type MediaSection = "hero-long-video" | "hero-vertical-clips" | "captions" | "reframe" | "hook" | "editor" | "clip-finding" | "templates" | "brand"
  | "setup"                  // job-setup screen stills (app screens)
  | "kit-preview"            // brand kit: one real render per shape and layout (scripts/make_kit_previews.py)
  | "hero-clean";            // the hero row: one clean gameplay cut per platform shape (scripts/make-hero-clean.py)

export type MediaItem = {
  id: string;               // stable key, e.g. "clip-1" or a template id
  label: string;            // what it shows, also the alt text
  kind: "video" | "image";
  src: string;              // path under /media/<section>/: MP4 (H.264) for video, WebP/PNG/SVG for images
  webm?: string;            // optional smaller VP9/AV1 copy, tried first
  poster?: string;          // still frame for a video, same size
  width: number; height: number;
  duration_sec?: number;
  rating?: number;          // AI rating shown on a clip card (0 to 100), when the item is a finished clip
  rating_source?: "signals" | "ai";
  rank?: number;
  game?: string;
  aspect?: string;          // "9:16", "16:9", "4:5", "1:1"
  platform?: string;        // hero-clean: the destination this shape is for (youtube, tiktok, instagram, facebook)
  credit?: string;          // e.g. "Footage: <creator>". Shown wherever the footage is shown.
  words?: string;           // path to a word-timings JSON (captions and editor demos)
  source?: { creator: string; url: string; start_sec?: number; end_sec?: number };
};
export type MediaManifest = { section: MediaSection; version: number; items: MediaItem[];
  permission?: string; credits?: { creator: string; url: string }[] };

const asked: Partial<Record<MediaSection, Promise<MediaManifest | null>>> = {};
export function loadMedia(section: MediaSection): Promise<MediaManifest | null> {
  asked[section] ??= fetch(`/media/${section}/manifest.json`).then((r) => (r.ok ? r.json() : null))
    .then((m: MediaManifest | null) => (m && Array.isArray(m.items) && m.items.length ? m : null)).catch(() => null);
  return asked[section]!;
}

// null while asking and when the section has no media yet.
export function useMedia(section: MediaSection): MediaManifest | null {
  const [m, setM] = useState<MediaManifest | null>(null);
  useEffect(() => { let on = true; loadMedia(section).then((x) => on && setM(x)); return () => { on = false; }; }, [section]);
  return m;
}

// A file's URL from its manifest path.
export const mediaUrl = (section: MediaSection, path: string) => `/media/${section}/${path.replace(/^\/+/, "")}`;
