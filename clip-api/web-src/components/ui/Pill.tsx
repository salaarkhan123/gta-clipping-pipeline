"use client";
// Choices in a row. Pills: one of a few (ratio 9:16 / 16:9, sort). The selected pill is white.
// Tabs: sections of a page, plain words with the current one underlined.
export type Option<T extends string> = { value: T; label: React.ReactNode; disabled?: boolean };

export function Pills<T extends string>({ options, value, onChange, label, size = "md", className = "" }: {
  options: Option<T>[]; value: T; onChange: (v: T) => void; label: string; size?: "sm" | "md"; className?: string;
}) {
  const dims = size === "sm" ? "h-7 min-w-[52px] px-3 text-[12px]" : "h-8 min-w-[75px] px-4 text-[13px]";
  return (
    <div role="radiogroup" aria-label={label} className={`inline-flex flex-wrap items-center gap-2 ${className}`}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} disabled={o.disabled} onClick={() => onChange(o.value)}
          className={`${dims} inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-pill border-0 font-sans font-medium tabular-nums transition-colors duration-base disabled:cursor-default disabled:opacity-45
            ${o.value === value ? "bg-btn text-btn-ink" : "bg-control text-text hover:bg-control-hover"}`}>{o.label}</button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ options, value, onChange, label, className = "" }: {
  options: Option<T>[]; value: T; onChange: (v: T) => void; label: string; className?: string;
}) {
  return (
    <div role="tablist" aria-label={label} className={`flex flex-wrap items-center gap-x-5 gap-y-1 ${className}`}>
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={o.value === value} disabled={o.disabled} onClick={() => onChange(o.value)}
          className={`relative h-9 cursor-pointer border-0 bg-transparent p-0 font-sans text-[14px] transition-colors duration-base disabled:cursor-default disabled:opacity-45
            after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:rounded-full after:bg-text after:transition-opacity after:duration-base
            ${o.value === value ? "text-text after:opacity-100" : "text-fg-2 after:opacity-0 hover:text-text"}`}>{o.label}</button>
      ))}
    </div>
  );
}
