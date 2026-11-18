"use client";
// Small pieces of the job-setup screen: cards, setting rows with a switch, inline selects and a popover.
import { useEffect, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon, IconName } from "../Icon";

export const CARD = "rounded-[24px] border border-solid border-line-soft bg-card p-6 narrow:p-4";
export const LABEL = "text-[13px] font-medium uppercase tracking-[.06em] text-muted";

// An on/off switch. `disabled` keeps it where it is.
export function Switch({ on, onChange, label, disabled }: { on: boolean; onChange?: (on: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={() => onChange?.(!on)}
      className={`relative h-7 w-12 flex-none cursor-pointer rounded-full border-0 p-0 transition-colors duration-150 disabled:cursor-default
        ${on ? "bg-text" : "bg-raised"} ${disabled && !on ? "opacity-50" : ""}`}>
      <span className={`absolute top-[3px] h-[22px] w-[22px] rounded-full transition-[left] duration-150 ${on ? "left-[23px] bg-bg" : "left-[3px] bg-muted"}`} />
    </button>
  );
}

// One setting: an icon, its name and a short line, then whatever sets it (a switch, a select). `soon` greys it out,
// adds the Coming soon mark and a switch that stays off: nothing planned can be turned on.
export function SettingRow({ icon, name, hint, soon, children, under }: { icon: IconName; name: string; hint?: string; soon?: boolean;
  children?: React.ReactNode; under?: React.ReactNode }) {
  return (
    <div className="grid gap-3 py-[14px]">
      <div className="flex items-center gap-3">
        <span className={`grid h-9 w-9 flex-none place-items-center rounded-12 ${soon ? "bg-surface text-fg-3" : "bg-text text-bg"}`} aria-hidden="true"><Icon name={icon} size={19} /></span>
        <div className="grid min-w-0 flex-1 gap-[2px]">
          <span className={`flex flex-wrap items-center gap-2 text-[15px] font-medium ${soon ? "text-fg-2" : "text-text"}`}>{name}{soon && <ComingSoonBadge />}</span>
          {hint && <span className="text-[12.5px] leading-[1.4] text-muted">{hint}</span>}
        </div>
        {soon ? <Switch on={false} label={`${name}: coming soon`} disabled /> : children}
      </div>
      {!soon && under}
    </div>
  );
}

// A select that reads as text ("AI picks: Auto ▾"): the native select sits on top, invisible, so the keyboard,
// screen readers and phones get the real control.
export function InlineSelect({ label, value, shown, onChange, children, disabled }: { label: string; value: string; shown: string;
  onChange: (v: string) => void; children: React.ReactNode; disabled?: boolean }) {
  return (
    <label className={`relative m-0 inline-flex min-h-[36px] max-w-full cursor-pointer items-center gap-1 rounded-full px-3 text-[14px] font-normal hover:bg-chip ${disabled ? "pointer-events-none opacity-50" : ""}`}>
      <span className="text-muted">{label}:</span><span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-text">{shown}</span>
      <Icon name="chevron" size={16} className="text-muted" />
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={label}
        className="absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-full p-0 opacity-0">{children}</select>
    </label>
  );
}

// A button that opens a panel under it. Escape or a click elsewhere closes it; focus goes back to the button.
export function Popover({ button, label, children, wide }: { button: React.ReactNode; label: string; children: React.ReactNode; wide?: boolean }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button ref={btn} type="button" aria-expanded={open} aria-label={label} onClick={() => setOpen(!open)}
        className="inline-flex min-h-[36px] cursor-pointer items-center gap-2 rounded-full border-0 bg-transparent px-3 font-sans text-[14px] text-text hover:bg-chip aria-expanded:bg-chip">{button}</button>
      {open && <div role="dialog" aria-label={label}
        className={`absolute left-0 top-[calc(100%+8px)] z-[60] grid max-h-[min(70vh,640px)] gap-5 overflow-y-auto rounded-[20px] border border-solid border-line bg-surface p-5 shadow-pop
          ${wide ? "w-[min(640px,calc(100vw-32px))]" : "w-[min(380px,calc(100vw-32px))]"} narrow:fixed narrow:inset-x-4 narrow:bottom-4 narrow:top-auto narrow:w-auto`}>{children}</div>}
    </div>
  );
}

// A picture tile in a row or grid (layouts, caption styles, hook tones). `on` draws the white ring and a tick.
export function Tile({ on, onClick, name, children, soon, className = "" }: { on?: boolean; onClick?: () => void; name: string; children: React.ReactNode;
  soon?: boolean; className?: string }) {
  const body = <>
    <span className={`relative grid place-items-center overflow-hidden rounded-12 bg-raised ring-inset transition-shadow duration-150 ${className}
      ${on ? "ring-2 ring-text" : "ring-1 ring-[rgba(255,255,255,.08)] group-hover/tile:ring-[rgba(255,255,255,.3)]"} ${soon ? "opacity-50" : ""}`}>
      {children}
      {on && <span className="absolute right-[6px] top-[6px] grid h-5 w-5 place-items-center rounded-full bg-text text-bg" aria-hidden="true"><Icon name="check" size={14} /></span>}
    </span>
    <span className={`flex flex-col items-center gap-1 text-center text-[12.5px] leading-[1.25] ${on ? "text-text" : "text-muted"}`}>{name}{soon && <ComingSoonBadge short />}</span>
  </>;
  return soon ? <span className="group/tile grid w-full content-start gap-[6px]" aria-disabled="true">{body}</span>
    : <button type="button" aria-pressed={!!on} onClick={onClick} className="group/tile grid w-full cursor-pointer content-start gap-[6px] border-0 bg-transparent p-0 font-sans">{body}</button>;
}
