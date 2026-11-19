// A neutral stand-in for footage that has not arrived yet (~/ClutchClips-eval/website-media/): a dark gradient
// frame with a label saying what goes there. Swap for a <video>/<img> of the same aspect ratio when the file lands.
export function MediaFrame({ label, ratio = "16 / 9", className = "", children }: { label: string; ratio?: string; className?: string; children?: React.ReactNode }) {
  return (
    <div role="img" aria-label={label} style={{ aspectRatio: ratio }}
      className={`relative grid place-items-center overflow-hidden rounded-16 bg-[radial-gradient(120%_90%_at_25%_15%,#2b2b2b_0%,#151515_55%,#0b0b0b_100%)] shadow-card ${className}`}>
      <span className="max-w-[90%] truncate rounded-pill bg-[rgba(0,0,0,.55)] px-3 py-[6px] font-mono text-caption text-fg-2">{label}</span>
      {children}
    </div>
  );
}
