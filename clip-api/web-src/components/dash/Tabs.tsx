"use client";
import { useRef } from "react";

// A tab list with the usual keyboard: Tab reaches the selected tab, arrows / Home / End move between tabs.
// Give `panel` the id of the element the tabs switch, and put role="tabpanel" on it.
export function Tabs<T extends string>({ label, tabs, value, onChange, panel }: {
  label: string; tabs: [T, string][]; value: T; onChange: (v: T) => void; panel?: string }) {
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
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map(([id, name], i) => (
        <button key={id} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" aria-selected={value === id} aria-controls={panel}
          tabIndex={value === id ? 0 : -1} className={value === id ? "on" : ""} onClick={() => onChange(id)} onKeyDown={(e) => onKey(e, i)}>{name}</button>))}
    </div>
  );
}
