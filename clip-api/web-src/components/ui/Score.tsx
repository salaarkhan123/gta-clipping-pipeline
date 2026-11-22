// The one score mark, wherever a clip shows one: a small label over a number in the accent colour, on a dark
// chip, bottom-left of the picture. `kind` says where the number comes from and sets the label:
// "ai" is the AI's rating of the clip, "sample" a demo number, "rank" the clip's place in its run when the AI
// did not rate it. Never a view forecast.
export type ScoreKind = "ai" | "sample" | "rank";
export type ScoreSize = "sm" | "md";

export const SCORE_LABEL: Record<ScoreKind, string> = { ai: "AI score", sample: "Sample", rank: "Rank" };

const SIZE: Record<ScoreSize, { box: string; label: string; value: string }> = {
  sm: { box: "min-w-[34px] rounded-[8px] px-[7px] pb-[5px] pt-[5px]", label: "text-[7px]", value: "text-[15px]" },
  md: { box: "min-w-[44px] rounded-[10px] px-[9px] pb-[6px] pt-[6px]", label: "text-[8px]", value: "text-[20px]" },
};

export function Score({ value, kind = "ai", size = "md", of, className = "" }: {
  value: number; kind?: ScoreKind; size?: ScoreSize; of?: number | null; className?: string;
}) {
  const n = Math.round(value), s = SIZE[size], label = SCORE_LABEL[kind];
  return (
    <span className={`inline-flex flex-col items-start gap-[3px] bg-black/70 font-sans leading-none [backdrop-filter:blur(8px)] ${s.box} ${className}`}
      aria-label={kind === "rank" ? `Number ${n}${of ? ` of ${of}` : ""} in this run` : `${label} ${n}`}>
      <span className={`${s.label} font-semibold uppercase tracking-[.08em] text-white/60`}>{label}</span>
      <b className={`${s.value} font-semibold tabular-nums tracking-[-0.02em] ${kind === "rank" ? "text-white" : "text-lime"}`}>
        {kind === "rank" ? `#${n}` : n}</b>
    </span>
  );
}
