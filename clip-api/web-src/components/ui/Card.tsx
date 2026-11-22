import type { HTMLAttributes } from "react";

// A surface one step above the canvas. No shadow; a hairline only where the canvas is black (the public site).
export function Card({ className = "", pad = true, ...rest }: HTMLAttributes<HTMLDivElement> & { pad?: boolean }) {
  return <div {...rest} className={`rounded-card bg-card shadow-card ${pad ? "p-8 narrow:p-5" : ""} ${className}`} />;
}
