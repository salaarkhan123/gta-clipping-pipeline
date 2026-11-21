"use client";
import { RefObject, useEffect } from "react";

// While `open`: a pointer press outside `box`, or Escape, calls `close`. Escape also puts focus back on `back`.
export function useDismiss(open: boolean, close: () => void, box: RefObject<HTMLElement | null>, back?: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!box.current?.contains(e.target as Node)) close(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { close(); back?.current?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", key); };
  }, [open, close, box, back]);
}
