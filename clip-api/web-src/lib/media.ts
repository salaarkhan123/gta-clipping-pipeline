"use client";
// Site media made by the media pipeline: public/media/<section>/manifest.json lists that section's files, which sit
// next to it. A section with no manifest yet (or an empty one) gets null, and the page shows its placeholder
// (components/site/MediaFrame.tsx). Sections match ~/ClutchClips-eval/website-media/ folder names.
import { useEffect, useState } from "react";

export type MediaSection = "hero-long-video" | "hero-vertical-clips" | "captions" | "reframe" | "hook" | "editor" | "clip-finding" | "templates" | "brand";

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
  game?: string;
};
export type MediaManifest = { section: MediaSection; version: number; items: MediaItem[] };

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
