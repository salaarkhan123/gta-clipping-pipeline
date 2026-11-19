"use client";
import { useEffect, useRef, useState } from "react";
import { MediaItem, MediaSection, mediaUrl, useMedia } from "@/lib/media";
import { useInView, useReducedMotion } from "./motion";

// Real footage from the media pipeline (public/media/<section>/manifest.json, read through lib/media.ts). Until a
// section has a manifest, every demo draws its labelled placeholder instead.

// Fields the media pipeline sends that lib/media.ts's MediaItem does not name yet.
export type Item = MediaItem & { hook?: string };
export type Word = { start: number; end: number; text: string };

export function useItem(section: MediaSection, id: string): Item | null {
  const m = useMedia(section);
  return (m?.items.find((i) => i.id === id) as Item | undefined) ?? null;
}
export function useItems(section: MediaSection): Item[] {
  return (useMedia(section)?.items as Item[] | undefined) ?? [];
}

// An item's word timings ({"words": [{start, end, text}]}), [] until loaded or when it has none.
export function useWords(section: MediaSection, item: Item | null): Word[] {
  const [words, setWords] = useState<Word[]>([]);
  useEffect(() => {
    if (!item?.words) return;
    let on = true;
    fetch(mediaUrl(section, item.words)).then((r) => (r.ok ? r.json() : null))
      .then((j) => on && Array.isArray(j?.words) && setWords(j.words.filter((w: Word) => typeof w?.text === "string" && w.text.trim())))
      .catch(() => {});
    return () => { on = false; };
  }, [section, item?.words]);
  return words;
}

// The AI rating is shown only when the AI judge rated the clip; a clip ranked on signals alone has none (the app
// says the same on its clip cards).
export const aiRated = (item: Item | null) => typeof item?.rating === "number" && item.rating_source === "ai";

// One item: the poster, then a muted loop once it is on screen and playing. Never sound, never for reduced motion.
// The footage credit the permission asks for sits in a corner.
// `videoRef`: the playing video element, for demos that follow its time (captions on the real words).
export function Footage({ section, item, play, credit = true, className = "", videoRef }: {
  section: MediaSection; item: Item; play: boolean; credit?: boolean; className?: string; videoRef?: React.Ref<HTMLVideoElement> }) {
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
      {credit && item.credit && <span className="absolute right-1 top-1 z-10 max-w-[70%] truncate rounded-[4px] bg-black/60 px-1 text-[9px] leading-[14px] text-white/80">{item.credit}</span>}
    </span>
  );
}
