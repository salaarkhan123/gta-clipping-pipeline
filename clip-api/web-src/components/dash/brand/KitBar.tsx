"use client";
// Brand kit header actions: kit picker (switch, new, rename, duplicate, set default, delete), undo/redo,
// Save as and Save. Naming opens a small dialog.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { useDismiss } from "../shell/useDismiss";
import { KIT_NAME_MAX, SavedKit } from "@/lib/brandkit";

const ICON_BTN = "grid h-[38px] w-[38px] cursor-pointer place-items-center rounded-control border-0 bg-transparent text-text transition-colors duration-base hover:bg-control disabled:cursor-default disabled:text-fg-3 disabled:hover:bg-transparent";
const MENU_ITEM = "flex min-h-[38px] w-full cursor-pointer items-center gap-[10px] rounded-8 border-0 bg-transparent px-[10px] py-[6px] text-left font-sans text-[14px] font-normal leading-[normal] text-text hover:bg-control-hover";

export function KitPicker({ kits, current, draftName, defaultId, onPick, onNew, onRename, onDuplicate, onSetDefault, onDelete }: {
  kits: SavedKit[]; current: string | null; draftName: string; defaultId: string | null;
  onPick: (id: string) => void; onNew: () => void; onRename: () => void; onDuplicate: () => void;
  onSetDefault: () => void; onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, box, btn);
  const name = kits.find((k) => k.id === current)?.name || draftName;
  const isDefault = !!current && current === defaultId;
  const pick = (f: () => void) => () => { setOpen(false); f(); };
  return (
    <div ref={box} className="relative min-w-0">
      <button ref={btn} type="button" aria-expanded={open} aria-label={`Brand kit: ${name}`} onClick={() => setOpen(!open)}
        className="flex h-[38px] w-[200px] max-w-full cursor-pointer items-center justify-between gap-2 rounded-pill border-0 bg-control pl-5 pr-4 font-sans text-[15px] font-medium text-text transition-colors duration-base hover:bg-control-hover">
        <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
          {name}
          {!current && <span className="font-normal text-muted"> (not saved)</span>}
          {isDefault && <span className="font-normal text-lime"> · default</span>}
        </span>
        <Icon name="chevron" size={18} className="text-muted" /></button>
      {open && <div aria-label="Brand kits" className="absolute left-0 top-[calc(100%+8px)] z-[60] grid w-[300px] max-w-[calc(100vw-32px)] gap-[2px] rounded-[14px] border-0 bg-control p-2 shadow-pop">
        {kits.length > 0 && <p className="m-0 px-[10px] pb-1 pt-1 text-[12px] font-medium text-muted">Your kits</p>}
        {kits.map((k) => <button key={k.id} type="button" className={MENU_ITEM} aria-current={k.id === current ? "true" : undefined} onClick={pick(() => onPick(k.id))}>
          <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{k.name}{k.id === defaultId ? <span className="text-muted"> · default</span> : ""}</span>
          {k.id === current && <Icon name="check" size={16} className="text-lime" />}</button>)}
        {kits.length > 0 && <div className="my-1 h-px bg-line" role="separator" />}
        <button type="button" className={MENU_ITEM} onClick={pick(onNew)}><Icon name="plus" size={17} className="text-muted" />New kit</button>
        {current && <button type="button" className={MENU_ITEM} onClick={pick(onRename)}><Icon name="pencil" size={17} className="text-muted" />Rename</button>}
        {current && <button type="button" className={MENU_ITEM} onClick={pick(onDuplicate)}><Icon name="stack" size={17} className="text-muted" />Duplicate</button>}
        {current && <button type="button" className={MENU_ITEM} onClick={pick(onSetDefault)} disabled={isDefault}
          aria-disabled={isDefault || undefined}>
          <Icon name="bookmark" size={17} className="text-muted" />{isDefault ? "Default kit" : "Set as default"}</button>}
        {current && <button type="button" className={`${MENU_ITEM} text-danger`} onClick={pick(onDelete)}><Icon name="trash" size={17} />Delete kit</button>}
      </div>}
    </div>
  );
}

export function UndoRedo({ canUndo, canRedo, onUndo, onRedo }: { canUndo: boolean; canRedo: boolean; onUndo: () => void; onRedo: () => void }) {
  return (
    <div className="flex items-center gap-[10px]">
      <button type="button" className={ICON_BTN} aria-label="Undo" title="Undo (Ctrl/Cmd+Z)" disabled={!canUndo} onClick={onUndo}><Icon name="undo" size={19} /></button>
      <button type="button" className={ICON_BTN} aria-label="Redo" title="Redo (Ctrl/Cmd+Shift+Z)" disabled={!canRedo} onClick={onRedo}><Icon name="redo" size={19} /></button>
    </div>
  );
}

// Asks for a kit's name. `full`: the plan's kit limit is reached, so a new kit cannot be saved.
export function NameDialog({ title, start, action, note, full, busy, problem, onSave, onClose }: { title: string; start: string; action: string; note?: string;
  full?: boolean; busy: boolean; problem: string; onSave: (name: string) => void; onClose: () => void }) {
  const [name, setName] = useState(start);
  const input = useRef<HTMLInputElement>(null), closer = useRef(onClose);
  closer.current = onClose;
  useEffect(() => {
    input.current?.select();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") closer.current(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  const ok = name.trim().length > 0 && name.trim().length <= KIT_NAME_MAX;
  return (
    <div className="fixed inset-0 z-[90] grid place-items-center bg-[rgba(0,0,0,.6)] p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form role="dialog" aria-modal="true" aria-labelledby="kit-dialog-title" onSubmit={(e) => { e.preventDefault(); if (ok && !full) onSave(name.trim()); }}
        className="grid w-[min(420px,100%)] gap-4 rounded-card border-0 bg-card p-6 shadow-pop">
        <h2 id="kit-dialog-title" className="m-0 text-[18px] font-semibold">{title}</h2>
        {full ? <p className="m-0 text-[14px] leading-[1.5] text-muted">{note} <Link href="/dashboard/pricing/">See plans</Link></p> : <>
          <label className="m-0 grid gap-2 text-[13px] font-medium text-muted">Name
            <input ref={input} value={name} maxLength={KIT_NAME_MAX} onChange={(e) => setName(e.target.value)} className="w-full" /></label>
          {note && <p className="m-0 text-[13px] text-fg-3">{note}</p>}
        </>}
        {problem && <p className="m-0 text-[14px] text-danger" role="alert">{problem}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn small ghost" onClick={onClose}>{full ? "Close" : "Cancel"}</button>
          {!full && <button type="submit" className="btn small primary" disabled={!ok || busy}>{busy ? "Saving…" : action}</button>}
        </div>
      </form>
    </div>
  );
}
