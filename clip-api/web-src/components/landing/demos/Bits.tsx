// Small pieces the demos and sections share.

// The AI rating on a clip: the AI's opinion of it, scaled across one video's clips. Never a forecast of views.
export function AiRating({ value, className = "" }: { value: number; className?: string }) {
  return (
    <span className={`inline-flex flex-col items-start rounded-[7px] bg-black/70 px-1.5 py-0.5 leading-none ${className}`} aria-label={`AI rating ${value}`}>
      <span className="text-[7.5px] font-semibold uppercase tracking-[.08em] text-white/60">AI rating</span>
      <b className="text-[17px] font-bold text-lime">{value}</b>
    </span>
  );
}

// A label under a frame: "Before", a layout's name.
export function Pill({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`inline-flex items-center rounded-full bg-white/10 px-3.5 py-1.5 text-[13px] font-medium text-white/90 backdrop-blur ${className}`}>{children}</span>;
}

export function LinkIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1" /><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" />
    </svg>
  );
}
