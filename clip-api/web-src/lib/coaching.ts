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
  intensity: {
    strong: "High stakes energy — the peak feels urgent.",
    mid: "Some heat; tighten around the most intense beat.",
    weak: "Low intensity — cut filler so the peak hits harder.",
  },
  kills_clutches: {
    strong: "Clear skilled play or clutch landing — the win reads cleanly.",
    mid: "Skilled play is there; make the clutch or wipe more obvious.",
    weak: "Little skilled-play payoff — lead with the decisive action or drop the claim.",
  },
  funny: {
    strong: "The comedy lands — punchline and timing work.",
    mid: "Mildly funny; trim to the joke and reaction.",
    weak: "Not reading as comedy — cut or reframe if humour is the hook.",
  },
  reactions: {
    strong: "Reaction is the star — timed tightly to the payoff.",
    mid: "Reaction helps; keep more of the peak response.",
    weak: "Weak or missing reaction — hold for the response or cut sooner.",
  },
  audio: {
    strong: "Sound sells the moment — voice and mix carry the beat.",
    mid: "Audio is fine; lift the loudest or clearest beat.",
    weak: "Audio underplays it — favour the clearest line or burst.",
  },
  chat: {
    strong: "Chat energy backs the moment without drowning it.",
    mid: "Some chat heat; keep the spike near the payoff.",
    weak: "Little chat contribution — do not lean on chat for this cut.",
  },
  unexpected: {
    strong: "Genuine surprise or reversal for this game.",
    mid: "Mildly unusual; frame the twist earlier.",
    weak: "Feels routine — find a fresher angle or shorter cut.",
  },
  game_context: {
    strong: "Cold viewers can read the game situation.",
    mid: "Mostly clear; trim jargon-heavy setup.",
    weak: "Needs stream context — open on a readable game beat.",
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
