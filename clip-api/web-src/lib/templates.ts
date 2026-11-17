import { API, api, ApiError } from "./api";
import { allows, Listed } from "./options";

// Display names for the game ids the API may send. An id that is not listed here is shown tidied up.
const GAMES: Record<string, string> = { gta: "GTA", gta5: "GTA 5", lol: "League of Legends", wow: "World of Warcraft", ow2: "Overwatch 2",
  minecraft: "Minecraft", apex: "Apex Legends", valorant: "Valorant", fortnite: "Fortnite", dota2: "Dota 2", rust: "Rust", cs2: "CS2", other: "Other games" };
export const tidy = (v: string) => v.replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());
export const gameName = (id: string) => GAMES[id] || tidy(id);
export const gameOf = (t: any): string => (typeof t.game === "string" && t.game) || "other";
export const isPreset = (t: any) => t?.kind === "preset";

// A template's picture or clip: a full link as it is, a path starting with "/" on the API. Anything else (a bare
// storage path) has no address the browser can load, so the caller draws our sketch instead of a broken picture.
export const mediaUrl = (v: unknown): string | null =>
  typeof v !== "string" ? null : /^https?:\/\//.test(v) ? v : v.startsWith("/") && !v.startsWith("//") ? API + v : null;

// The look a clip is given: everything Pre-editing sets. Saved looks ("My templates") hold exactly these.
export type Look = { vertical: boolean; aspect: string; layout: string; captions: boolean; caption_style: string; censor: boolean;
  caption_emoji: boolean; hook_overlay: boolean; tighten: boolean; punch_zoom: boolean; flash_forward: boolean;
  camera: string | null; split_ratio: number | null };
export const LOOK_KEYS = ["vertical", "aspect", "layout", "captions", "caption_style", "censor", "caption_emoji", "hook_overlay",
  "tighten", "punch_zoom", "flash_forward", "camera", "split_ratio"] as const;
const SWITCHES = ["vertical", "captions", "censor", "caption_emoji", "hook_overlay", "tighten", "punch_zoom", "flash_forward"] as const;
// Never taken from a template: what sets how many clips, which part of the video, or what a job costs.
const NOT_A_LOOK = ["template", "max_clips", "clip_length", "limit", "duration", "range", "prompt", "render", "resolution",
  "source_lang", "target_lang", "project_name", "chat_region", "facecam_region", "facecam_box", "zoom"];

// The part of a look a template (or a saved look) sets, keeping only values the API accepts today.
export function lookFrom(options: any, listed: Listed, panels?: any): Partial<Look> {
  const o = options && typeof options === "object" ? options : {}, out: Record<string, any> = {};
  for (const k of SWITCHES) if (typeof o[k] === "boolean" && k in listed) out[k] = o[k];
  for (const k of ["aspect", "layout", "caption_style"]) if (typeof o[k] === "string" && allows(listed, k, o[k])) out[k] = o[k];
  if (out.aspect && !("vertical" in out)) out.vertical = true;
  if (out.caption_style && !("captions" in out)) out.captions = true;
  // Panel sizes are sent only once the API takes both of them.
  const p = panels && typeof panels === "object" ? panels : o;
  if ("camera" in listed && "split_ratio" in listed) {
    out.camera = typeof p.camera === "string" && allows(listed, "camera", p.camera) ? p.camera : null;
    out.split_ratio = typeof p.split_ratio === "number" ? p.split_ratio : null;
  }
  return out;
}
// Options a template carries that this form has no control for (a hook style, a caption position): sent along with
// the template while it is chosen, once the API lists them.
export function extrasFrom(options: any, listed: Listed): Record<string, unknown> {
  const o = options && typeof options === "object" ? options : {};
  return Object.fromEntries(Object.entries(o).filter(([k, v]) => k in listed && !NOT_A_LOOK.includes(k) && !(LOOK_KEYS as readonly string[]).includes(k)
    && (!listed[k].values || listed[k].values!.includes(v))));
}

// The game-type presets and the per-game templates. `GET /v1/templates?kind=preset` is being built: an API without
// it ignores the filter and answers with the per-game list, so presets are told apart by their `kind`.
export async function loadTemplates(): Promise<{ presets: any[]; games: any[] }> {
  const list = (r: any): any[] => (Array.isArray(r?.templates) ? r.templates.filter((t: any) => t && typeof t.id === "string") : []);
  const [all, preset] = await Promise.all([api("/v1/templates", { auth: false }).then(list),
    api("/v1/templates?kind=preset", { auth: false }).then(list).catch(() => [])]);
  const seen = new Set<string>(), each = [...preset, ...all].filter((t) => !seen.has(t.id) && !!seen.add(t.id));
  return { presets: each.filter(isPreset), games: each.filter((t) => !isPreset(t)) };
}

// Saved looks. `null` means this API has no saved looks yet (404 or 405), and the page hides the controls for them.
export async function loadCustom(): Promise<any[] | null> {
  try {
    const r = await api("/v1/templates/custom");
    const rows = Array.isArray(r) ? r : Array.isArray(r?.templates) ? r.templates : Array.isArray(r?.custom) ? r.custom : [];
    return rows.filter((t: any) => t && (typeof t.id === "string" || typeof t.id === "number"));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}
