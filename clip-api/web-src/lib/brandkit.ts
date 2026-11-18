// A brand kit is a saved look (GET/POST/PATCH/DELETE /v1/templates/custom): how clips are framed and captioned,
// the hook's tone and the editing switches. Nothing here sets what a job costs: the API refuses priced options in
// a saved look, and a kit is free to save. Logos, intros and outros, music and per-shape layouts are not stored by
// the API yet, so the page shows them as Coming soon and never sends them.
import { api } from "./api";
import { allows, Listed } from "./options";
import { Look, lookFrom, lookOptions, startLook } from "./templates";

export type Kit = Look & { hook_style: string };
export type SavedKit = { id: string; name: string; options: Record<string, unknown> };
export type Kits = { kits: SavedKit[]; limit: number | null };

export const KIT_NAME_MAX = 80;
export const FIRST_KIT_NAME = "My brand kit";

export async function loadKits(): Promise<Kits> {
  const r = await api("/v1/templates/custom");
  const rows: any[] = Array.isArray(r?.templates) ? r.templates : [];
  return {
    kits: rows.filter((t) => t && (typeof t.id === "string" || typeof t.id === "number"))
      .map((t) => ({ id: String(t.id), name: typeof t.name === "string" && t.name ? t.name : "Untitled", options: t.options && typeof t.options === "object" ? t.options : {} })),
    limit: typeof r?.limit === "number" ? r.limit : null,
  };
}

const hookDefault = (listed: Listed) => String(listed.hook_style?.default || listed.hook_style?.values?.[0] || "serious");

// A new kit: the dashboard's starting look.
export const blankKit = (listed: Listed): Kit => ({ ...startLook(listed), hook_style: hookDefault(listed) });

// A saved kit read back, keeping only values this API accepts today.
export function kitFrom(saved: SavedKit, listed: Listed): Kit {
  const base = blankKit(listed), o = saved.options;
  const look = { ...base, ...lookFrom(saved, listed, base.aspect) };
  // A saved look may leave switches out; lookFrom only copies what it says.
  const hook = typeof o.hook_style === "string" && allows(listed, "hook_style", o.hook_style) ? o.hook_style : base.hook_style;
  return { ...look, hook_style: hook };
}

// What is sent to save a kit: the look under the API's names, plus the hook tone when the API takes it.
export function kitOptions(kit: Kit, listed: Listed): Record<string, unknown> {
  const out = lookOptions(kit, listed);
  if ("hook_style" in listed) out.hook_style = kit.hook_style;
  return out;
}

export const sameKit = (a: Kit, b: Kit, listed: Listed) => JSON.stringify(kitOptions(a, listed)) === JSON.stringify(kitOptions(b, listed));

export const createKit = (name: string, kit: Kit, listed: Listed) =>
  api<SavedKit>("/v1/templates/custom", { body: { name, options: kitOptions(kit, listed) } });
export const updateKit = (id: string, patch: { name?: string; kit?: Kit }, listed: Listed) =>
  api<SavedKit>(`/v1/templates/custom/${encodeURIComponent(id)}`, { method: "PATCH",
    body: { ...(patch.name !== undefined ? { name: patch.name } : {}), ...(patch.kit ? { options: kitOptions(patch.kit, listed) } : {}) } });
export const deleteKit = (id: string) => api(`/v1/templates/custom/${encodeURIComponent(id)}`, { method: "DELETE" });
