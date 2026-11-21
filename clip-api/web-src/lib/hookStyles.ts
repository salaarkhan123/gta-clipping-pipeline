// Hook tone labels for UI. Prefer GET /v1/options → clips.hook_style.catalogue when present
// (C2 shape: {id, label, description}); fall back to title-cased ids when main has no catalogue yet.

export type HookCatalogueEntry = { id: string; label: string; description?: string };

// Same title-case as lib/templates.tidy — kept local so node --test can load this module alone.
const titleCase = (v: string) => v.replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());

// Defensive: tolerate missing/malformed catalogue so stacking with C2 works without a rebase.
export function hookCatalogueOf(raw: unknown): HookCatalogueEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: HookCatalogueEntry[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const id = (row as { id?: unknown }).id;
    const label = (row as { label?: unknown }).label;
    if (typeof id !== "string" || !id || typeof label !== "string" || !label) continue;
    const description = (row as { description?: unknown }).description;
    out.push({
      id,
      label,
      ...(typeof description === "string" && description ? { description } : {}),
    });
  }
  return out;
}

export function hookToneLabel(id: string, catalogue?: HookCatalogueEntry[] | null): string {
  const hit = catalogue?.find((e) => e.id === id);
  return hit?.label || titleCase(id);
}

export function hookToneDescription(id: string, catalogue?: HookCatalogueEntry[] | null): string | undefined {
  return catalogue?.find((e) => e.id === id)?.description;
}
