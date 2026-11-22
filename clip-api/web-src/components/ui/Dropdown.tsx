"use client";
// The one dropdown: a trigger and the panel it opens (a menu of rows, or any content such as a style picker).
// Every panel in the app shares this surface (grey, radius, shadow, padding) and this behaviour: Escape or a press
// outside closes it and focus returns to the trigger; arrow keys, Home and End move between its `data-item`s.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Icon, IconName } from "@/components/dash/Icon";

export const PANEL = "z-[70] rounded-[16px] bg-control p-2 shadow-pop";
const ALIGN = { start: "left-0", end: "right-0", center: "left-1/2 -translate-x-1/2" };
const SIDE = { bottom: "top-[calc(100%+8px)]", top: "bottom-[calc(100%+8px)]" };

export type TriggerProps = {
  ref: React.RefObject<HTMLButtonElement | null>; onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu" | "dialog";
};

// `anchor="parent"`: the panel is placed against the nearest positioned ancestor instead of the trigger (a wide
// picker that lines up with its card). `panelClass` then carries the position.
export function Dropdown({ trigger, children, label, kind = "menu", align = "start", side = "bottom", anchor = "trigger", panelClass = "", className = "" }: {
  trigger: (props: TriggerProps, open: boolean) => React.ReactNode;
  children: React.ReactNode | ((close: () => void) => React.ReactNode);
  label: string; kind?: "menu" | "dialog"; align?: keyof typeof ALIGN; side?: keyof typeof SIDE; anchor?: "trigger" | "parent";
  panelClass?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null), panel = useRef<HTMLDivElement>(null), button = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const items = () => Array.from(panel.current?.querySelectorAll<HTMLElement>("[data-item]:not(:disabled):not([aria-disabled=true])") || []);

  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!wrap.current?.contains(e.target as Node)) close(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); button.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    const list = items();
    (list.find((el) => el.getAttribute("aria-checked") === "true" || el.getAttribute("aria-selected") === "true") || list[0])?.focus({ preventScroll: true });
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open, close]);

  function onKey(e: React.KeyboardEvent) {
    const move = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    if (move === undefined && e.key !== "Home" && e.key !== "End") return;
    if ((e.target as HTMLElement).matches("input, textarea, select")) return;
    const list = items();
    if (!list.length) return;
    e.preventDefault();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : (at + move! + list.length) % list.length;
    list[next].focus();
  }

  return (
    <span ref={wrap} className={`${anchor === "trigger" ? "relative" : ""} inline-flex ${className}`}>
      {trigger({ ref: button, onClick: () => setOpen((o) => !o), "aria-expanded": open, "aria-haspopup": kind }, open)}
      {open && <div ref={panel} role={kind} aria-label={label} onKeyDown={onKey}
        className={`absolute ${PANEL} ${anchor === "trigger" ? `${ALIGN[align]} ${SIDE[side]}` : ""} ${panelClass}`}>
        {typeof children === "function" ? children(close) : children}
      </div>}
    </span>
  );
}

const ROW = "flex min-h-[40px] w-full items-center gap-[10px] rounded-[10px] border-0 bg-transparent px-[10px] py-[6px] text-left font-sans text-[14px] font-normal leading-[1.3] no-underline";
const ROW_ON = "cursor-pointer text-text hover:bg-control-hover focus-visible:bg-control-hover";

// A row of a menu: a link (`href`), an action (`onSelect`), or neither (planned: shown dimmed with its mark).
// `checked` puts the tick on the right, for a menu that picks one of several.
export function MenuItem({ icon, children, href, onSelect, checked, danger, disabled, after }: {
  icon?: IconName; children: React.ReactNode; href?: string; onSelect?: () => void; checked?: boolean; danger?: boolean; disabled?: boolean; after?: React.ReactNode;
}) {
  const body = <>
    {icon && <Icon name={icon} size={18} className={danger ? "" : "text-fg-2"} />}
    <span className="min-w-0 flex-1">{children}</span>
    {after}
    {checked && <Icon name="check" size={16} />}
  </>;
  const role = checked === undefined ? "menuitem" : "menuitemradio";
  if (href) return <Link data-item role={role} href={href} onClick={onSelect} className={`${ROW} ${ROW_ON}`}>{body}</Link>;
  if (!onSelect || disabled) return <span role={role} aria-disabled="true" className={`${ROW} cursor-default text-fg-3`}>{body}</span>;
  return <button data-item type="button" role={role} aria-checked={checked} onClick={onSelect} className={`${ROW} ${ROW_ON} ${danger ? "!text-danger" : ""}`}>{body}</button>;
}

export const MenuLabel = ({ children }: { children: React.ReactNode }) => (
  <p className="m-0 px-[10px] pb-1 pt-[6px] font-sans text-[12px] font-medium text-fg-2">{children}</p>
);
export const MenuRule = () => <div className="my-1 h-px bg-line" role="separator" />;
