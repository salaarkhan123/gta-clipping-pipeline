"use client";
import { useId, useState } from "react";
import { Icon } from "@/components/dash/Icon";

// A settings group: a card with a small uppercase label and a chevron that folds it away.
// `hint` is the one grey sentence under the label.
export function SectionCard({ label, hint, defaultOpen = true, children, className = "" }: {
  label: string; hint?: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode; className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const body = useId();
  return (
    <section className={`rounded-card bg-card ${className}`} aria-label={label}>
      <button type="button" aria-expanded={open} aria-controls={body} onClick={() => setOpen(!open)}
        className="flex h-[68px] w-full cursor-pointer items-center justify-between rounded-card border-0 bg-transparent px-8 text-left font-sans text-[14px] uppercase tracking-[.02em] text-fg-2 transition-colors duration-base hover:text-text narrow:px-5">
        {label}
        <Icon name="chevron" size={18} className={`transition-transform duration-base ease-out ${open ? "rotate-180" : ""}`} />
      </button>
      <div id={body} hidden={!open} className="grid gap-6 px-8 pb-8 narrow:px-5 narrow:pb-6">
        {hint && <p className="m-0 -mt-1 text-[14px] leading-[1.45] text-fg-2">{hint}</p>}
        {children}
      </div>
    </section>
  );
}

// Advanced settings inside a group, closed until asked for.
export function More({ label = "More", children }: { label?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const body = useId();
  return (
    <div className="grid gap-6">
      <div id={body} hidden={!open} className="grid gap-6">{children}</div>
      <button type="button" aria-expanded={open} aria-controls={body} onClick={() => setOpen(!open)}
        className="mx-auto inline-flex h-8 cursor-pointer items-center gap-1 rounded-8 border-0 bg-transparent px-2 font-sans text-[14px] text-fg-2 transition-colors duration-base hover:text-text">
        {open ? "Less" : label}<Icon name="chevron" size={16} className={`transition-transform duration-base ${open ? "rotate-180" : ""}`} />
      </button>
    </div>
  );
}
