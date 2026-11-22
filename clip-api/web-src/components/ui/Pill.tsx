"use client";
// Choices in a row. Pills: one of a few (ratio 9:16 / 16:9, sort). The selected pill is white.
// Tabs: sections of a page, plain words with the current one underlined.
export type Option<T extends string> = { value: T; label: React.ReactNode; disabled?: boolean };

// `tone="quiet"`: a filter above a list (All / Images / Videos): the chosen one is a grey block, the rest plain words.
export function Pills<T extends string>({ options, value, onChange, label, size = "md", tone = "solid", className = "" }: {
  options: Option<T>[]; value: T; onChange: (v: T) => void; label: string; size?: "sm" | "md"; tone?: "solid" | "quiet"; className?: string;
}) {
  const quiet = tone === "quiet";
  const dims = quiet ? "h-9 px-3 text-[14.5px] rounded-8" : `rounded-pill ${size === "sm" ? "h-7 min-w-[52px] px-3 text-[12px]" : "h-8 min-w-[75px] px-4 text-[13px]"}`;
  const look = (on: boolean) => quiet ? (on ? "bg-control text-text" : "bg-transparent text-fg-2 hover:text-text") : (on ? "bg-btn text-btn-ink" : "bg-control text-text hover:bg-control-hover");
  return (
    <div role="radiogroup" aria-label={label} className={`inline-flex flex-wrap items-center ${quiet ? "gap-1" : "gap-2"} ${className}`}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} disabled={o.disabled} onClick={() => onChange(o.value)}
          className={`${dims} inline-flex cursor-pointer items-center justify-center gap-1.5 border-0 font-sans font-medium tabular-nums transition-colors duration-base disabled:cursor-default disabled:opacity-45
            ${look(o.value === value)}`}>{o.label}</button>
      ))}
    </div>
  );
}

// 38 px tall, 16 px words, 16 px apart; the underline is as wide as the tab.
export function Tabs<T extends string>({ options, value, onChange, label, panel, className = "" }: {
  options: Option<T>[]; value: T; onChange: (v: T) => void; label: string; panel?: string; className?: string;
}) {
  function onKey(e: React.KeyboardEvent<HTMLDivElement>) {
    const move = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!move) return;
    const open = options.filter((o) => !o.disabled), at = open.findIndex((o) => o.value === value);
    const next = open[(at + move + open.length) % open.length];
    e.preventDefault();
    onChange(next.value);
    e.currentTarget.querySelector<HTMLElement>(`[data-tab="${next.value}"]`)?.focus();
  }
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKey} className={`flex flex-wrap items-center gap-x-4 gap-y-1 ${className}`}>
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" data-tab={o.value} aria-selected={o.value === value} aria-controls={panel} tabIndex={o.value === value ? 0 : -1}
          disabled={o.disabled} onClick={() => onChange(o.value)}
          className={`relative h-[38px] cursor-pointer border-0 bg-transparent px-2 font-sans text-[16px] font-normal transition-colors duration-base disabled:cursor-default disabled:opacity-45
            after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-text after:content-[''] after:transition-opacity after:duration-base
            ${o.value === value ? "text-text after:opacity-100" : "text-fg-2 after:opacity-0 hover:text-text"}`}>{o.label}</button>
      ))}
    </div>
  );
}
