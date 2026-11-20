"use client";
import { useEffect, useRef, useState } from "react";
import { MediaItem, MediaSection, mediaUrl, useMedia } from "@/lib/media";
import { useInView, useReducedMotion } from "./motion";

// Real footage from the media pipeline (public/media/<section>/manifest.json, read through lib/media.ts). Until a
// section has a manifest, every demo draws its labelled placeholder instead.

// Fields the media pipeline sends that lib/media.ts's MediaItem does not name yet: the hook line, and the data
// files next to an item (`peaks`: its audio levels; `signals`: the engine's highlight score along a stream).
export type Item = MediaItem & { hook?: string; peaks?: string; signals?: string };
export type Word = { start: number; end: number; text: string };

export function useItem(section: MediaSection, id: string): Item | null {
  const m = useMedia(section);
  return (m?.items.find((i) => i.id === id) as Item | undefined) ?? null;
}
export function useItems(section: MediaSection): Item[] {
  return (useMedia(section)?.items as Item[] | undefined) ?? [];
}

// A JSON file next to an item, read with `pick`; null until loaded, or when the item has no such file.
function useItemJson<T>(section: MediaSection, path: string | undefined, pick: (j: any) => T | null): T | null {
  const [v, setV] = useState<T | null>(null);
  useEffect(() => {
    if (!path) return;
    let on = true;
    fetch(mediaUrl(section, path)).then((r) => (r.ok ? r.json() : null)).then((j) => on && setV(j ? pick(j) : null)).catch(() => {});
    return () => { on = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, path]);
  return v;
}
const levels = (a: unknown): number[] | null =>
  Array.isArray(a) && a.length > 0 && a.every((n) => typeof n === "number" && n >= 0 && n <= 1) ? a : null;

// An item's word timings ({"words": [{start, end, text}]}), [] until loaded or when it has none.
export function useWords(section: MediaSection, item: Item | null): Word[] {
  return useItemJson(section, item?.words, (j) => Array.isArray(j?.words)
    ? j.words.filter((w: Word) => typeof w?.text === "string" && w.text.trim() && typeof w.start === "number" && typeof w.end === "number") : null) ?? [];
}
// An item's audio levels ({"peaks": [0..1]}), evenly spaced over the clip.
export function usePeaks(section: MediaSection, item: Item | null): number[] | null {
  return useItemJson(section, item?.peaks, (j) => levels(j?.peaks));
}
// The engine's highlight score along a stream ({"step_sec", "values": [0..1]}).
export function useSignals(section: MediaSection, item: Item | null): { step: number; values: number[] } | null {
  return useItemJson(section, item?.signals, (j) => typeof j?.step_sec === "number" && j.step_sec > 0 && levels(j?.values)
    ? { step: j.step_sec, values: j.values } : null);
}

// The AI rating is shown only when the AI judge rated the clip; a clip ranked on signals alone has none (the app
// says the same on its clip cards).
export const aiRated = (item: Item | null) => typeof item?.rating === "number" && item.rating_source === "ai";

// One item: the poster, then a muted loop once it is on screen and playing. Never sound, never for reduced motion.
// Its credit is not drawn on the frame: each card names every creator it shows once, in <Credits>.
// `videoRef`: the playing video element, for demos that follow its time (captions on the real words).
export function Footage({ section, item, play, className = "", videoRef }: {
  section: MediaSection; item: Item; play: boolean; className?: string; videoRef?: React.Ref<HTMLVideoElement> }) {
  const box = useRef<HTMLSpanElement>(null), seen = useInView(box), reduced = useReducedMotion();
  const live = item.kind === "video" && seen && play && !reduced;
  return (
    <span ref={box} className={`absolute inset-0 overflow-hidden bg-black ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {(item.poster || item.kind === "image") && <img src={mediaUrl(section, item.poster || item.src)} alt={item.label} loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover" />}
      {live && <video ref={videoRef} muted loop playsInline autoPlay preload="none" poster={item.poster ? mediaUrl(section, item.poster) : undefined}
        className="absolute inset-0 h-full w-full object-cover" aria-hidden="true">
        {item.webm && <source src={mediaUrl(section, item.webm)} type="video/webm" />}
        <source src={mediaUrl(section, item.src)} type="video/mp4" />
      </video>}
    </span>
  );
}

// The one credit line of a card: every creator whose footage the card shows, as the permission asks.
export function Credits({ items, className = "" }: { items: (Item | null | undefined)[]; className?: string }) {
  const names = [...new Set(items.map((i) => i?.credit?.replace(/^Footage:\s*/, "").trim()).filter(Boolean))];
  return names.length ? <p className={`text-center text-[11px] text-white/50 ${className}`}>Footage: {names.join(", ")}</p> : null;
}
