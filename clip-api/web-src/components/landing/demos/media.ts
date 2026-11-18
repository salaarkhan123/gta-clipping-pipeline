// Real footage for the landing demos, once the owner supplies it (~/ClutchClips-eval/website-media/<section>/).
// Each file is cut with ffmpeg into public/landing/<section>/: a muted loop under ~1.5 MB and a poster frame.
// A key without an entry draws the labelled placeholder from Frames.tsx instead.
export type MediaKey = "hero-long" | "hero-clip" | "captions" | "reframe" | "hook" | "editor" | "clip-finding";
export type Loop = { poster: string; video?: string };

export const MEDIA: Partial<Record<MediaKey, Loop>> = {};
