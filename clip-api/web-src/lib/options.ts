"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

// One option of POST /v1/clips as GET /v1/options describes it. `by_aspect` (layout only) lists the values each
// aspect accepts.
export type Option = { type?: string; values?: any[]; default?: any; minimum?: number; maximum?: number; maxLength?: number;
  nullable?: boolean; by_aspect?: Record<string, string[]> };
export type Listed = Record<string, Option>;

// The options the API accepted when this was written. Used only when the list cannot be fetched, so the form
// still shows the controls that exist today and never one the API might refuse.
const LAYOUTS = ["auto", "full", "fit", "split2", "pip", "screen_first", "gameplay_a", "gameplay_b", "split", "fill", "classic"];
const SQUARE = ["auto", "full", "fit", "split", "fill", "classic"], WIDE = LAYOUTS.filter((l) => !l.startsWith("gameplay_"));
export const TODAY: Listed = {
  vertical: { type: "boolean" },
  aspect: { type: "string", values: ["9:16", "4:5", "1:1", "16:9"] },
  chat_region: { type: "string", values: ["none", "top-right", "top-center", "top-left", "bottom-right", "bottom-left"] },
  zoom: { type: "number", minimum: 1, maximum: 1.6 },
  captions: { type: "boolean" },
  caption_style: { type: "string", values: ["pop", "bold", "neon", "boxed", "clean"] },
  censor: { type: "boolean" },
  layout: { type: "string", values: LAYOUTS, by_aspect: { "9:16": LAYOUTS, "4:5": LAYOUTS, "1:1": SQUARE, "16:9": WIDE } },
  resolution: { type: "string", values: ["480", "720", "1080", "2k", "4k"] },
  facecam_region: { type: "string", values: ["auto", "top-left", "top-right", "bottom-left", "bottom-right"], nullable: true },
  max_clips: { type: "integer", minimum: 1, maximum: 10 },
  clip_length: { type: "integer", minimum: 10, maximum: 60 },
  tighten: { type: "boolean" },
  punch_zoom: { type: "boolean" },
  flash_forward: { type: "boolean" },
  hook_overlay: { type: "boolean" },
  template: { type: "string", nullable: true },
};

// Asked once per visit and shared by every form. A failed request is not remembered, so the next form tries again.
let asked: Promise<Listed> | null = null;
export function clipOptions(): Promise<Listed> {
  if (!asked) {
    asked = api("/v1/options", { auth: false }).then((r) => {
      const list = r?.clips;
      if (!list || typeof list !== "object" || !Object.keys(list).length) throw new Error("empty");
      return list as Listed;
    });
    asked.catch(() => { asked = null; });
  }
  return asked.catch(() => TODAY);
}

// null while loading. A form waits for it, so no control appears and then disappears.
export function useClipOptions(): Listed | null {
  const [listed, setListed] = useState<Listed | null>(null);
  useEffect(() => { let on = true; clipOptions().then((l) => on && setListed(l)); return () => { on = false; }; }, []);
  return listed;
}

// Whether the API takes this value for this option (an option without a value list takes anything of its type).
export const allows = (listed: Listed, key: string, value: unknown) =>
  key in listed && (value === null ? !!listed[key].nullable : !listed[key].values || listed[key].values!.includes(value));
// The numbers from `wanted` that fall inside the option's limits.
export const inside = (o: Option | undefined, wanted: number[]) =>
  wanted.filter((n) => n >= (o?.minimum ?? -Infinity) && n <= (o?.maximum ?? Infinity));
// The layouts one aspect accepts.
export const layoutsFor = (listed: Listed, aspect: string): string[] =>
  listed.layout?.by_aspect?.[aspect] || listed.layout?.values || ["auto"];
// Keeps only what the API accepts: an option that is not listed is never sent.
export function onlyListed(listed: Listed, options: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(options).filter(([k]) => k in listed));
}
