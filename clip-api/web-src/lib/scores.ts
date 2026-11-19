// The one map of AI sub-score names, for every judge the API has used. Judge v2 sends `clip.scores` with the five
// keys of app/ai.py SCORES (`scoring_version` "judge-v2-equal"); clips rated before it carry judge v1's parts inside
// `clip.virality` ("judge-v1"). tests/scores.test.mjs fails when app/ai.py names a score this map does not.
export const V2_SCORES = ["hook", "payoff", "clarity", "emotion", "pacing"] as const;
export const V1_SCORES = ["hook", "flow", "value", "trend"] as const;

export const SCORE_LABELS: Record<string, string> = {
  hook: "Hook", payoff: "Payoff", clarity: "Clarity", emotion: "Emotion", pacing: "Pacing",
  flow: "Flow", story: "Story", value: "Value", trend: "Trend", engagement: "Engagement", reach: "Reach",
};

// A readable name for any sub-score key, including one a newer judge adds before this map knows it.
export const scoreLabel = (key: string) => SCORE_LABELS[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
