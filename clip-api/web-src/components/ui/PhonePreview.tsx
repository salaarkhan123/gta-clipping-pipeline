// The live preview frame: a rounded screen in the chosen shape, with whatever plays inside it.
// The tall shapes read as a phone; 16:9 and 1:1 keep the same corners at their own ratio.
export type PreviewRatio = "9:16" | "16:9" | "1:1" | "4:5";
export const PREVIEW_RATIOS: PreviewRatio[] = ["9:16", "16:9", "1:1", "4:5"];
const RATIO: Record<PreviewRatio, string> = { "9:16": "aspect-[9/16]", "16:9": "aspect-video", "1:1": "aspect-square", "4:5": "aspect-[4/5]" };

export function PhonePreview({ ratio = "9:16", children, className = "", label }: {
  ratio?: PreviewRatio; children: React.ReactNode; className?: string; label?: string;
}) {
  return (
    <div role="img" aria-label={label} className={`relative w-full overflow-hidden rounded-[14px] bg-black transition-[aspect-ratio] duration-slow ease-out ${RATIO[ratio]} ${className}`}>
      {children}
    </div>
  );
}
