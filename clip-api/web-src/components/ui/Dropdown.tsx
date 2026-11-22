"use client";
// The one dropdown: a trigger and the panel it opens (a menu of rows, or any content such as a style picker).
// Every panel in the app shares this surface (grey, radius, shadow, padding) and this behaviour: Escape or a press
// outside closes it; closing from inside the panel returns focus to the trigger, and tabbing out closes it; arrow
// keys, Home and End move between its `data-item`s.
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, IconName } from "@/components/dash/Icon";

// The surface every panel shares. Its corner and padding are the `panelClass` default, so a larger picker can set its own.
export const PANEL = "z-[95] bg-control shadow-pop";
const GAP = 8, EDGE = 12;

export type TriggerProps = {
  ref: React.RefObject<HTMLButtonElement | null>; onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu" | "dialog";
};

// The panel is drawn over the page (a portal into the app's theme root, fixed to the window), so no card can clip
// it. It opens under its anchor, or over it when there is more room there, never leaves the window, and scrolls
// inside when it is taller than the room it has.
// `anchor`: the element the panel lines up with (default: the trigger). `dx`: a nudge sideways from that edge.
export function Dropdown({ trigger, children, label, kind = "menu", align = "start", side = "bottom", anchor, dx = 0, panelClass = "rounded-[16px] p-2", className = "" }: {
  trigger: (props: TriggerProps, open: boolean) => React.ReactNode;
  children: React.ReactNode | ((close: () => void) => React.ReactNode);
  label: string; kind?: "menu" | "dialog"; align?: "start" | "end" | "center"; side?: "bottom" | "top";
  anchor?: React.RefObject<HTMLElement | null>; dx?: number; panelClass?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState<{ left: number; top: number; max: number } | null>(null);
  const wrap = useRef<HTMLSpanElement>(null), panel = useRef<HTMLDivElement>(null), button = useRef<HTMLButtonElement>(null);
  // Closing from inside the panel (an item chosen, Escape) gives focus back to the trigger instead of the page.
  const close = useCallback(() => {
    const now = document.activeElement;
    if (!now || now === document.body || panel.current?.contains(now)) button.current?.focus({ preventScroll: true });
    setOpen(false);
  }, []);
  // The panel sits at the end of the page (a portal), so Tab past its last control (Shift+Tab before its first)
  // closes it and goes on from the trigger, to the trigger's own neighbour, as if the panel were inline.
  const tabOut = (e: React.KeyboardEvent) => {
    const all = Array.from(panel.current?.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input:not(:disabled), select, textarea, [tabindex]:not([tabindex='-1'])") || []);
    if (e.target !== (e.shiftKey ? all[0] : all[all.length - 1])) return;
    button.current?.focus({ preventScroll: true });
    setOpen(false);
  };
  // Focus moving to another element outside the panel closes it too. A blur with no new target (a press on plain
  // content, the window losing focus) leaves it open.
  const leave = (e: React.FocusEvent) => {
    const to = e.relatedTarget as Node | null;
    if (to && !panel.current?.contains(to) && !wrap.current?.contains(to)) setOpen(false);
  };
  const items = () => Array.from(panel.current?.querySelectorAll<HTMLElement>("[data-item]:not(:disabled):not([aria-disabled=true])") || []);

  const place = useCallback(() => {
    const el = panel.current, to = (anchor?.current || button.current)?.getBoundingClientRect();
    if (!el || !to) return;
    const width = el.offsetWidth, height = el.scrollHeight, vw = window.innerWidth, vh = window.innerHeight;
    const want = align === "start" ? to.left + dx : align === "end" ? to.right - width + dx : to.left + to.width / 2 - width / 2;
    const below = vh - to.bottom - GAP - EDGE, above = to.top - GAP - EDGE;
    const up = side === "top" ? above >= Math.min(height, below) : below < Math.min(height, 260) && above > below;
    const max = Math.max(160, up ? above : below);
    setAt({ left: Math.max(EDGE, Math.min(want, vw - width - EDGE)), top: up ? Math.max(EDGE, to.top - GAP - Math.min(height, max)) : to.bottom + GAP, max });
  }, [align, side, anchor, dx]);

  useLayoutEffect(() => {
    if (!open) { setAt(null); return; }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { const t = e.target as Node; if (!wrap.current?.contains(t) && !panel.current?.contains(t)) close(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); button.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open, close]);
  // Focus moves into the panel once it is placed (it is hidden until then): the chosen item, else the first.
  const placed = at !== null;
  useEffect(() => {
    if (!placed) return;
    const list = items();
    (list.find((el) => el.getAttribute("aria-checked") === "true" || el.getAttribute("aria-selected") === "true") || list[0])?.focus({ preventScroll: true });
  }, [placed]);

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Tab") return tabOut(e);
    const move = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    if (move === undefined && e.key !== "Home" && e.key !== "End") return;
    if ((e.target as HTMLElement).matches("input, textarea, select")) return;
    const list = items();
    if (!list.length) return;
    e.preventDefault();
    const now = list.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : (now + move! + list.length) % list.length;
    list[next].focus();
  }

  return (
    <span ref={wrap} className={`inline-flex ${className}`}>
      {trigger({ ref: button, onClick: () => setOpen((o) => !o), "aria-expanded": open, "aria-haspopup": kind }, open)}
      {open && createPortal(
        <div ref={panel} role={kind} aria-label={label} onKeyDown={onKey} onBlur={leave}
          style={at ? { left: at.left, top: at.top, maxHeight: at.max } : { left: 0, top: 0, visibility: "hidden" }}
          className={`fixed max-w-[calc(100vw-24px)] overflow-y-auto overscroll-contain ${PANEL} ${panelClass}`}>
          {typeof children === "function" ? children(close) : children}
        </div>, document.querySelector<HTMLElement>("[data-theme]") || document.body)}
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
