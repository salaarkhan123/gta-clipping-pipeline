"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

// One option of POST /v1/clips as GET /v1/options describes it. `by_aspect` (layout only) lists the values each
// aspect accepts. `catalogue` is optional (hook_style from C2): {id, label, description}[] when the API sends it.
export type Option = { type?: string; values?: any[]; default?: any; minimum?: number; maximum?: number; maxLength?: number;
  nullable?: boolean; by_aspect?: Record<string, string[]>; catalogue?: { id: string; label: string; description?: string }[] };
export type Listed = Record<string, Option>;

// Asked once per visit and shared by every form. A failed request is not remembered, so the next try asks again.
// There is no built-in fallback list: a form waits ("Loading the options…") rather than show options the API may refuse.
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
  return asked;
}

// null while loading. A form waits for it, so no control appears and then disappears.
export function useClipOptions(): Listed | null {
  const [listed, setListed] = useState<Listed | null>(null);
  useEffect(() => {
    let on = true, retry: ReturnType<typeof setTimeout> | undefined;
    const get = () => clipOptions().then((l) => { if (on) setListed(l); }, () => { if (on) retry = setTimeout(get, 5000); });
    get();
    return () => { on = false; clearTimeout(retry); };
  }, []);
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

// Clip lengths offered: the automatic one ("0-90") and the buckets that end at 60 s or sooner (owner, 2026-11-18).
export const offeredBucket = (b: string) => b === "0-90" || +b.split("-")[1] <= 60;
// New website jobs start with previews (the API's own default stays "full" for API customers); each card's Export
// button renders full quality.
export const RENDER = "preview";
