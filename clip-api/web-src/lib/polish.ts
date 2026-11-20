import type { IconName } from "@/components/dash/Icon";
import type { Look } from "./templates";

// "Polish clips with" on Home's start card: switches that preset the job-setup screen. Each built one is one
// option of POST /v1/clips; B-roll is planned and never sent. The address carries the chosen ones as
// `polish=captions,tighten,hook`, so a link or an upload opens the job-setup screen with them already set.
export type PolishId = "captions" | "broll" | "tighten" | "hook";
export type Polish = Partial<Record<PolishId, boolean>>;
export const POLISH: { id: PolishId; name: string; icon: IconName; built: boolean; option?: keyof Look }[] = [
  { id: "captions", name: "Captions", icon: "captions", built: true, option: "captions" },
  { id: "broll", name: "B-roll", icon: "image", built: false },
  { id: "tighten", name: "Speech cleanup", icon: "mic", built: true, option: "tighten" },
  { id: "hook", name: "Hook", icon: "hook", built: true, option: "hook_overlay" },
];

export const polishQuery = (p: Polish) => `polish=${POLISH.filter((x) => x.built && p[x.id]).map((x) => x.id).join(",")}`;

// The look the address asks for, or {} when it says nothing (the job-setup screen's own defaults).
export function polishLook(search: string): Partial<Look> {
  const raw = new URLSearchParams(search).get("polish");
  if (raw === null) return {};
  const on = new Set(raw.split(",").filter(Boolean));
  return Object.fromEntries(POLISH.filter((x) => x.built && x.option).map((x) => [x.option!, on.has(x.id)]));
}
