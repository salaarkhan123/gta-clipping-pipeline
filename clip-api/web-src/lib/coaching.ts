// Fixed ClutchClips coaching lines for AI rating sub-scores. Derived only from the numeric
// part the API already returns (clip.scores / clip.virality) — no new backend tip fields.
// Honest AI opinion; never a view forecast or a letter grade.

export type ScoreBand = "strong" | "mid" | "weak";

// Bands on the 0–100 sub-score: strong enough to keep, mid to tighten, weak to fix first.
export function scoreBand(value: number): ScoreBand {
  if (!Number.isFinite(value)) return "weak";
  if (value >= 75) return "strong";
  if (value >= 45) return "mid";
  return "weak";
}

type BandCopy = Record<ScoreBand, string>;

// One short sentence per known dimension × band. Unknown keys fall back to a generic line.
const COPY: Record<string, BandCopy> = {
  hook: {
    strong: "Opens with a clear grab — the AI thinks viewers know why to stay.",
    mid: "The open is serviceable; a sharper first beat would land harder.",
    weak: "The open is soft — lead with the punch or a payoff tease.",
  },
  payoff: {
    strong: "Pays off what it promises — the turn lands cleanly.",
    mid: "The ending works; tighten the beat so the punch hits sooner.",
    weak: "The payoff fizzles — cut sooner or make the turn clearer.",
  },
  clarity: {
    strong: "Easy to follow — the moment reads without explanation.",
    mid: "Mostly clear; trim dead air or muddy lines that slow the read.",
    weak: "Hard to follow — cut clutter so the beat is obvious.",
  },
  emotion: {
    strong: "Strong reaction energy — the feel of the moment comes through.",
    mid: "Some heat; lean harder into the biggest reaction.",
    weak: "Flat energy — keep the biggest reaction and cut the quiet.",
  },
  pacing: {
    strong: "Moves at a clip-friendly pace — little drag between beats.",
    mid: "Pace is okay; shave the lulls between the peaks.",
    weak: "Drags — cut pauses so the clip keeps moving.",
  },
  flow: {
    strong: "Beats connect smoothly — the clip feels continuous.",
    mid: "Flow is fine; smoother joins between moments would help.",
    weak: "Choppy — re-cut so each beat leads into the next.",
  },
  value: {
    strong: "Feels worth watching on its own — a complete beat.",
    mid: "Decent value; make the one reason to watch clearer.",
    weak: "Thin on its own — sharpen what makes this moment matter.",
  },
  trend: {
    strong: "Fits what travels in gaming clips right now, in the AI's view.",
    mid: "Somewhat timely; lean into the more recognisable beat.",
    weak: "Feels dated or niche — frame the moment for a wider gaming crowd.",
  },
};

const FALLBACK: BandCopy = {
  strong: "This part scores well in the AI's opinion — keep it.",
  mid: "This part is mid-pack — a small edit could lift it.",
  weak: "This part scores low — fix it before the others.",
};

/** One coaching sentence for a sub-score part, or null when there is no numeric value. */
export function coachingFor(key: string, value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const band = scoreBand(value);
  return (COPY[key] ?? FALLBACK)[band];
}
