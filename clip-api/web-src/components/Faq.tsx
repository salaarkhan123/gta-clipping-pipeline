"use client";
// Accordion of questions: bordered rows, one chevron each, answers slide open. Any number can be open at once.
import { useId, useState } from "react";
import { Icon } from "@/components/dash/Icon";

export type FaqItem = { q: string; a: React.ReactNode };

export function Faq({ items }: { items: FaqItem[] }) {
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const base = useId();
  return (
    <div className="mx-auto grid max-w-prose gap-4 narrow:gap-3">
      {items.map(({ q, a }, i) => {
        const on = !!open[i], panel = `${base}-${i}`;
        return (
          <div key={q} className="rounded-card border border-solid border-line transition-colors duration-200 hover:border-line-strong">
            <h3 className="m-0">
              <button type="button" aria-expanded={on} aria-controls={panel} onClick={() => setOpen((o) => ({ ...o, [i]: !o[i] }))}
                className="flex w-full cursor-pointer items-center justify-between gap-4 border-0 bg-transparent px-7 py-[25px] text-left font-sans text-h3 text-fg narrow:px-4 narrow:py-[18px] narrow:text-[16px] narrow:font-medium">
                {q}
                <Icon name="chevron" size={22} className={`flex-none transition-transform duration-300 ease-out ${on ? "rotate-180" : ""}`} />
              </button>
            </h3>
            <div id={panel} role="region" aria-label={q} className={`grid transition-[grid-template-rows] duration-300 ease-out ${on ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
              <div className="overflow-hidden" inert={!on}>
                <div className="grid gap-3 px-7 pb-[25px] text-body-lg text-fg-2 narrow:px-4 narrow:pb-[18px] narrow:text-[15px] [&_a]:text-fg [&_a]:underline">{a}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
