// The one on-picture score chip: same type, weight, size, padding, radius and background wherever a score sits on
// media (landing demos, results tiles). Never a view forecast — "AI quality" for real ratings,
// "Sample score" for decorative demo numbers.

export type ScoreKind = "ai" | "sample";

const LABEL: Record<ScoreKind, string> = {
  ai: "AI quality",
  sample: "Sample score",
};

const CHIP =
  "inline-flex flex-col items-start rounded-[7px] border-0 bg-black/70 px-1.5 py-0.5 font-sans leading-none " +
  "shadow-[inset_0_0_0_1px_rgba(255,255,255,.12)] [backdrop-filter:blur(8px)]";

export function ScoreOverlay({
  value,
  kind = "ai",
  className = "",
}: {
  value: number;
  kind?: ScoreKind;
  className?: string;
}) {
  const n = Math.round(value);
  const label = LABEL[kind];
  return (
    <span className={`${CHIP} ${className}`} aria-label={`${label} ${n}`}>
      <span className="text-[7.5px] font-semibold uppercase tracking-[.08em] text-white/60">{label}</span>
      <b className="text-[17px] font-bold tabular-nums tracking-[-0.02em] text-lime">{n}</b>
    </span>
  );
}
