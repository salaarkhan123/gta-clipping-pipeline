"use client";
import { RefObject, useEffect, useState } from "react";

// The landing demos animate only while they can be seen: in view, on the carousel's active card, and never for a
// visitor who asked for less motion. These three hooks decide that.

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(q.matches);
    on();
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);
  return reduced;
}

// True once the element is within `margin` of the viewport, false again when it leaves.
export function useInView(ref: RefObject<Element | null>, margin = "160px"): boolean {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, margin]);
  return seen;
}

// A counter that goes up by one every `ms` while `on`, and holds where it is otherwise.
export function useTicker(on: boolean, ms: number): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setN((v) => v + 1), ms);
    return () => clearInterval(t);
  }, [on, ms]);
  return n;
}
