"use client";
import { useRef } from "react";

// A tab list with the usual keyboard: Tab reaches the selected tab, arrows / Home / End move between tabs.
// Give `panel` the id of the element the tabs switch, and put role="tabpanel" on it.
// `seg`: the compact segmented look instead of pills.
const SEG = "inline-flex gap-[2px] rounded-12 border border-solid border-line-soft bg-panel p-[3px]";
const SEG_BUTTON = "cursor-pointer rounded-8 border-0 px-4 py-[7px] font-body text-[14px] font-medium leading-[normal] narrow:min-h-[40px]";
export function Tabs<T extends string>({ label, tabs, value, onChange, panel, seg }: {
  label: string; tabs: [T, string][]; value: T; onChange: (v: T) => void; panel?: string; seg?: boolean }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: React.KeyboardEvent, i: number) {
    const n = tabs.length;
    const j = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (j < 0) return;
    e.preventDefault();
    onChange(tabs[j][0]);
    refs.current[j]?.focus();
  }
  return (
    <div className={seg ? SEG : "tabs"} role="tablist" aria-label={label}>
      {tabs.map(([id, name], i) => (
        <button key={id} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" aria-selected={value === id} aria-controls={panel}
          tabIndex={value === id ? 0 : -1} className={seg ? `${SEG_BUTTON} ${value === id ? "bg-chip-hover text-text" : "bg-transparent text-muted hover:text-text"}` : value === id ? "on" : ""} onClick={() => onChange(id)} onKeyDown={(e) => onKey(e, i)}>{name}</button>))}
    </div>
  );
}
