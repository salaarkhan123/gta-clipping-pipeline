// The dead air a clip's run cut out, as editor cuts: the gaps between the source parts it was rendered from
// (`clip.segments`, in playing order). A flash-forward is the first part when it starts after the second one;
// it is a copy of the peak, so it is left aside. Only gaps inside [start, end] are returned, in source seconds.
// The same rule as the API's exports.dead_air, so the editor opens on the cut the clip was made with.
export type Gap = [number, number];

export function deadAir(segments: unknown, start: number, end: number): Gap[] {
  if (!Array.isArray(segments) || !segments.every((s) => Array.isArray(s) && s.length === 2 && s.every((x) => typeof x === "number"))) return [];
  const parts = segments as Gap[];
  const flash = parts.length > 1 && parts[0][0] >= parts[1][0];
  const body = (flash ? parts.slice(1) : parts).slice().sort((a, b) => a[0] - b[0]);
  const out: Gap[] = [];
  for (let i = 1; i < body.length; i++) {
    const a = Math.max(body[i - 1][1], start), b = Math.min(body[i][0], end);
    if (b - a > 0.05) out.push([Math.round(a * 1000) / 1000, Math.round(b * 1000) / 1000]);
  }
  return out;
}
