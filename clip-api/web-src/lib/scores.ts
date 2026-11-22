// The one map of AI sub-score names, for every judge the API has used.
// Judge v3 gaming: `clip.gaming_scores` / display `clip.scores` with nine highlight-quality keys
// (`scoring_version` "judge-v3-gaming"). Judge v2: five editorial keys (`judge-v2-equal`).
// Judge v1: four parts inside `clip.virality` ("judge-v1").
// tests/scores.test.mjs fails when app/gaming_rating.py or ranking.SCORES names a score this map does not.
export const V2_SCORES = ["hook", "payoff", "clarity", "emotion", "pacing"] as const;
export const V1_SCORES = ["hook", "flow", "value", "trend"] as const;
export const GAMING_SCORES = [
  "hook", "intensity", "kills_clutches", "funny", "reactions", "audio", "chat", "unexpected", "game_context",
] as const;

export const SCORE_LABELS: Record<string, string> = {
  hook: "Hook", payoff: "Payoff", clarity: "Clarity", emotion: "Emotion", pacing: "Pacing",
  flow: "Flow", story: "Story", value: "Value", trend: "Trend", engagement: "Engagement", reach: "Reach",
  intensity: "Intensity", kills_clutches: "Kills / clutches", funny: "Funny", reactions: "Reactions",
  audio: "Audio", chat: "Chat", unexpected: "Unexpected", game_context: "Game context",
};

// A readable name for any sub-score key, including one a newer judge adds before this map knows it.
export const scoreLabel = (key: string) => SCORE_LABELS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
