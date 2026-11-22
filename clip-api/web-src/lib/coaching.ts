// Fixed ClutchClips coaching lines for AI rating sub-scores. Derived only from the numeric
// part the API already returns (clip.scores / clip.virality) — no new backend tip fields.
// Honest AI opinion of highlight quality for gaming clips; never a view forecast or a letter grade.

export type ScoreBand = "strong" | "mid" | "weak";

// Bands on the 0–100 sub-score: strong enough to keep, mid to tighten, weak to fix first.
export function scoreBand(value: number): ScoreBand {
  if (!Number.isFinite(value)) return "weak";
  if (value >= 75) return "strong";
  if (value >= 45) return "mid";
  return "weak";
}

type BandCopy = Record<ScoreBand, string>;

// One short sentence per known dimension × band. Gaming verbs; unknown keys fall back.
const COPY: Record<string, BandCopy> = {
  hook: {
    strong: "Opens hard — crash, kill, yell, or fail lands in the first seconds.",
    mid: "The open is serviceable; lead sooner with the punch or a payoff tease.",
    weak: "Soft open — cut the lobby or drive-up and start on the beat.",
  },
  payoff: {
    strong: "Pays off cleanly — clutch, fail, punchline, or chase ending lands.",
    mid: "The ending works; tighten so the turn hits sooner.",
    weak: "Payoff fizzles — cut sooner or make the turn clearer.",
  },
  clarity: {
    strong: "Cold viewers get the stakes — the beat reads without the rest of the VOD.",
    mid: "Mostly clear; trim muddy lines or missing setup that slow the read.",
    weak: "Hard to follow cold — keep the line that names who, what, and the turn.",
  },
  emotion: {
    strong: "Strong reaction energy — laugh, rage, hype, or shock comes through.",
    mid: "Some heat; lean harder into the biggest streamer reaction.",
    weak: "Flat energy — keep the biggest reaction and cut the quiet.",
  },
  pacing: {
    strong: "Clip-friendly pace — little dead air between gaming beats.",
    mid: "Pace is okay; shave lulls between the peaks.",
    weak: "Drags — cut pauses and post-payoff hang so it keeps moving.",
  },
  flow: {
    strong: "Beats connect smoothly — the clip feels continuous.",
    mid: "Flow is fine; smoother joins between moments would help.",
    weak: "Choppy — re-cut so each beat leads into the next.",
  },
  value: {
    strong: "Feels worth watching on its own — a complete gaming beat.",
    mid: "Decent value; make the one reason to watch clearer.",
    weak: "Thin on its own — sharpen what makes this moment matter.",
  },
  trend: {
    strong: "Fits what travels in gaming Shorts right now, in the AI's view.",
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
