// One-click Generate Highlights: how many clips Auto aims for from source length.
// Mirrors clip-api/app/pipeline/highlights.py — keep the constants in sync.
export const MAX_CLIPS = 50;
export const SEC_PER_SLOT = 180;
export const MIN_WANT = 3;

/** Upper bound for Auto discovery from analysed length (seconds). Quality floor still filters. */
export function suggestWant(spanSec: number): number {
  if (!(spanSec > 0)) return MIN_WANT;
  return Math.max(MIN_WANT, Math.min(MAX_CLIPS, Math.round(spanSec / SEC_PER_SLOT)));
}
