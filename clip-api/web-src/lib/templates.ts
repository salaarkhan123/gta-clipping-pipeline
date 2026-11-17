import { API, api, ApiError } from "./api";
import { allows, layoutsFor, Listed } from "./options";

// Display names for the game ids the API may send. An id that is not listed here is shown tidied up.
const GAMES: Record<string, string> = { gta: "GTA", gta5: "GTA 5", lol: "League of Legends", wow: "World of Warcraft", ow2: "Overwatch 2",
  minecraft: "Minecraft", apex: "Apex Legends", valorant: "Valorant", fortnite: "Fortnite", dota2: "Dota 2", rust: "Rust", cs2: "CS2", other: "Other games" };
export const tidy = (v: string) => v.replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());
export const gameName = (id: string) => GAMES[id] || tidy(id);
export const gameOf = (t: any): string => (typeof t.game === "string" && t.game) || "other";
export const isPreset = (t: any) => t?.kind === "preset";

// Layouts by name. Gameplay A and B are provisional until they have been compared with real output.
const LAYOUT_NAMES: Record<string, string> = { auto: "Automatic", split2: "Split in two", pip: "Picture in picture",
  gameplay_a: "Gameplay A", gameplay_b: "Gameplay B", classic: "Classic (blurred sides)" };
const PROVISIONAL_LAYOUTS = ["gameplay_a", "gameplay_b"];
const SAME_AS: Record<string, string> = { split: "split2", fill: "full" };       // older names for the same layout
const TWO_PANELS = ["split", "split2", "screen_first", "gameplay_a", "gameplay_b"];
export const layoutName = (id: string) => (LAYOUT_NAMES[id] || tidy(id)) + (PROVISIONAL_LAYOUTS.includes(id) ? " (provisional)" : "");
export const hasPanels = (layout: string) => TWO_PANELS.includes(layout);
// The layouts to offer for an aspect: an older name is left out when its newer twin is offered, unless it is chosen.
export const layoutChoices = (listed: Listed, aspect: string, chosen: string) => {
  const all = layoutsFor(listed, aspect);
  return all.filter((l) => l === chosen || !(SAME_AS[l] && all.includes(SAME_AS[l])));
};
// Every game-type preset is provisional, and so is anything drawn with Gameplay A or B.
export const isProvisional = (t: any) => isPreset(t) || t?.provisional === true || PROVISIONAL_LAYOUTS.includes(t?.layout);

// A template's picture or clip: a full link as it is, a path starting with "/" on the API. Anything else (a bare
// storage path) has no address the browser can load, so the caller draws our sketch instead of a broken picture.
export const mediaUrl = (v: unknown): string | null =>
  typeof v !== "string" ? null : /^https?:\/\//.test(v) ? v : v.startsWith("/") && !v.startsWith("//") ? API + v : null;

// The look a clip is given: everything Pre-editing sets, under the API's own option names. Saved looks hold these.
export type Look = { vertical: boolean; aspect: string; layout: string; camera: string | null; split_ratio: number | null;
  captions: boolean; caption_style: string; caption_position: string; caption_accent: string | null; caption_emoji: boolean; censor: boolean;
  hook_overlay: boolean; tighten: boolean; punch_zoom: boolean; flash_forward: boolean };
export const LOOK_KEYS = ["vertical", "aspect", "layout", "camera", "split_ratio", "captions", "caption_style", "caption_position",
  "caption_accent", "caption_emoji", "censor", "hook_overlay", "tighten", "punch_zoom", "flash_forward"] as const;
const SWITCHES = ["vertical", "captions", "caption_emoji", "censor", "hook_overlay", "tighten", "punch_zoom", "flash_forward"] as const;
// Never taken from a template's options: how many clips, which part of the video, the export size, where things
// sit on this streamer's screen.
const NOT_A_LOOK = ["template", "max_clips", "clip_length", "limit", "duration", "range", "prompt", "render", "resolution",
  "source_lang", "target_lang", "project_name", "chat_region", "facecam_region", "facecam_box", "zoom"];

// The look a new job starts with. These are the dashboard's own choices, not the API's defaults: every one of them
// is sent with the request.
export function startLook(listed: Listed): Look {
  const styles: string[] = listed.caption_style?.values || [], aspects: string[] = listed.aspect?.values || [];
  return { vertical: true, aspect: aspects.includes("9:16") ? "9:16" : aspects[0] || "9:16", layout: "auto", camera: null, split_ratio: null,
    captions: true, caption_style: ["impact", "pop"].find((s) => styles.includes(s)) || styles[0] || "pop",
    caption_position: "auto", caption_accent: null, caption_emoji: false, censor: false,
    hook_overlay: true, tighten: true, punch_zoom: true, flash_forward: true };
}
// Pre-editing switched off: the clip is cut out and left as it is.
export const AS_IT_IS: Partial<Look> = { vertical: false, layout: "auto", camera: null, split_ratio: null, captions: false, caption_emoji: false,
  censor: false, hook_overlay: false, tighten: false, punch_zoom: false, flash_forward: false };

// The camera and split a two-panel layout starts from when a template does not say: gameplay 60% over the camera.
export const DEFAULT_PANELS = { camera: "bottom", split_ratio: 0.6 };
const ratioIn = (listed: Listed, v: unknown): number | null => typeof v !== "number" ? null
  : Math.min(listed.split_ratio?.maximum ?? 0.75, Math.max(listed.split_ratio?.minimum ?? 0.25, v));

// The layout a template asks for, if this aspect takes it. `layout` on the template is the one it was designed
// for; `options.layout` is what it could send before the API took that one.
export const layoutOf = (t: any, listed: Listed, aspect: string): string | null =>
  [t?.layout, t?.options?.layout].find((l) => typeof l === "string" && layoutsFor(listed, aspect).includes(l)) || null;

// The part of a look a template or a saved look sets, keeping only values the API accepts today. A game template
// keeps the chosen aspect; a saved look brings its own.
export function lookFrom(t: any, listed: Listed, aspect: string): Partial<Look> {
  const o = t?.options && typeof t.options === "object" ? t.options : {}, out: Record<string, any> = {};
  for (const k of SWITCHES) if (typeof o[k] === "boolean" && k in listed) out[k] = o[k];
  if (typeof o.aspect === "string" && allows(listed, "aspect", o.aspect) && !t?.game && !isPreset(t)) out.aspect = o.aspect;
  out.layout = layoutOf(t, listed, out.aspect || aspect) || "auto";
  const style = [o.caption_style, t?.caption_style].find((s) => typeof s === "string" && allows(listed, "caption_style", s));
  if (style) out.caption_style = style;
  if (typeof o.caption_position === "string" && allows(listed, "caption_position", o.caption_position)) out.caption_position = o.caption_position;
  if ("caption_accent" in listed && (o.caption_accent === null || /^#[0-9a-f]{6}$/i.test(o.caption_accent || ""))) out.caption_accent = o.caption_accent;
  // A game template or a preset is made to be reframed and captioned; a saved look says so itself.
  if (!("vertical" in out)) out.vertical = true;
  if (style && !("captions" in out)) out.captions = true;
  // Panel sizes are used only once the API takes both of them, and only by layouts with two panels.
  if ("camera" in listed && "split_ratio" in listed) {
    const p = t?.panels && typeof t.panels === "object" ? t.panels : o, two = hasPanels(out.layout);
    out.camera = two && typeof p.camera === "string" && allows(listed, "camera", p.camera) ? p.camera : null;
    out.split_ratio = two && out.camera ? ratioIn(listed, p.split_ratio) : null;
  }
  return out;
}
// Options a template carries that this form has no control for (its hook style, say): sent along with the
// template while it is chosen, once the API lists them. Never anything that sets a count, a range or a size.
export function extrasFrom(t: any, listed: Listed): Record<string, unknown> {
  const o = t?.options && typeof t.options === "object" ? t.options : {}, hook = t?.hook && typeof t.hook === "object" ? t.hook : {};
  const all = { hook_style: hook.style, hook_position: hook.position, ...o };
  return Object.fromEntries(Object.entries(all).filter(([k, v]) => v !== undefined && v !== null && !NOT_A_LOOK.includes(k)
    && !(LOOK_KEYS as readonly string[]).includes(k) && allows(listed, k, v)));
}
// What a saved look stores: the look and nothing else, under the names the API lists.
export const lookOptions = (look: Look, listed: Listed): Record<string, unknown> =>
  Object.fromEntries(LOOK_KEYS.filter((k) => k in listed).map((k) => [k, look[k]]));

// The game-type presets and the per-game templates. `GET /v1/templates?kind=preset` is being built: an API without
// it ignores the filter and answers with the per-game list, so presets are told apart by their `kind`.
export async function loadTemplates(): Promise<{ presets: any[]; games: any[] }> {
  const list = (r: any): any[] => (Array.isArray(r?.templates) ? r.templates.filter((t: any) => t && typeof t.id === "string") : []);
  const [all, preset] = await Promise.all([api("/v1/templates", { auth: false }).then(list),
    api("/v1/templates?kind=preset", { auth: false }).then(list).catch(() => [])]);
  const seen = new Set<string>(), each = [...preset, ...all].filter((t) => !seen.has(t.id) && !!seen.add(t.id));
  return { presets: each.filter(isPreset), games: each.filter((t) => !isPreset(t)) };
}

// Saved looks ("My templates"). `null` means this API has no saved looks yet (404 or 405), and the page hides
// the controls for them.
export type Saved = { id: string; name: string; options: Record<string, unknown> };
export async function loadCustom(): Promise<Saved[] | null> {
  try {
    const r = await api("/v1/templates/custom");
    const rows = Array.isArray(r) ? r : Array.isArray(r?.templates) ? r.templates : Array.isArray(r?.custom) ? r.custom : [];
    return rows.filter((t: any) => t && (typeof t.id === "string" || typeof t.id === "number"))
      .map((t: any) => ({ id: String(t.id), name: typeof t.name === "string" && t.name ? t.name : "Untitled", options: t.options && typeof t.options === "object" ? t.options : {} }));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return null;
    throw e;
  }
}
export const NAME_MAX = 80;
export const saveCustom = (name: string, options: Record<string, unknown>) => api("/v1/templates/custom", { body: { name, options } });
export const renameCustom = (id: string, name: string) => api(`/v1/templates/custom/${encodeURIComponent(id)}`, { method: "PATCH", body: { name } });
export const deleteCustom = (id: string) => api(`/v1/templates/custom/${encodeURIComponent(id)}`, { method: "DELETE" });
