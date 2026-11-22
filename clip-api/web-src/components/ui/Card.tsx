import type { HTMLAttributes } from "react";

// A surface one step above the canvas. No shadow; a hairline only where the canvas is black (the public site).
export function Card({ className = "", pad = true, ...rest }: HTMLAttributes<HTMLDivElement> & { pad?: boolean }) {
  return <div {...rest} className={`rounded-card bg-card shadow-card ${pad ? "p-8 narrow:p-5" : ""} ${className}`} />;
}

// One number with its label: a balance, a total. `tone` colours the number (the accent for a balance).
export function StatCard({ label, value, hint, tone = "text-text" }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className="grid content-start gap-1 rounded-16 bg-card p-5">
      <span className="text-[14px] text-fg-2">{label}</span>
      <span className={`font-sans text-[28px] font-semibold leading-[1.1] tracking-[-0.02em] tabular-nums ${tone}`}>{value}</span>
      {hint && <span className="text-[12.5px] text-fg-3">{hint}</span>}
    </div>
  );
}
