// A small state mark. "Soon": planned, not built, never a link. "Unavailable": built but not usable here.
// "New": shipped recently. "Neutral": a plain tag (a plan name, "Default").
export type BadgeTone = "soon" | "unavailable" | "new" | "neutral";

const TONE: Record<BadgeTone, string> = {
  soon: "bg-control text-fg-2",
  unavailable: "bg-control text-fg-3",
  new: "bg-lime/[.14] text-lime",
  neutral: "bg-control text-text",
};
const WORD: Partial<Record<BadgeTone, string>> = { soon: "Soon", unavailable: "Unavailable", new: "New" };

export function Badge({ tone = "neutral", children, className = "" }: { tone?: BadgeTone; children?: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-5 flex-none items-center whitespace-nowrap rounded-[6px] px-[7px] font-sans text-[11px] font-medium leading-none ${TONE[tone]} ${className}`}>
      {children ?? WORD[tone]}
    </span>
  );
}
