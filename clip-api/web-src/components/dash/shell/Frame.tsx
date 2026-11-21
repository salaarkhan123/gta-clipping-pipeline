"use client";
// The frame around every signed-in page: the sidebar (a drawer on a phone), the top bar, and the page's own column.
import { useEffect, useRef, useState } from "react";
import { isFindShortcut } from "@/lib/globalFind";
import { GlobalFind } from "./GlobalFind";
import { SIDE_OPEN, SIDE_SHUT, Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

const KEY = "cc_sidebar";
const read = () => { try { return window.localStorage.getItem(KEY) === "collapsed"; } catch { return false; } };
const write = (shut: boolean) => { try { window.localStorage.setItem(KEY, shut ? "collapsed" : "open"); } catch { /* private mode: not remembered */ } };

export function Frame({ me, path, onLogout, children }: { me: any; path: string; onLogout: () => void; children: React.ReactNode }) {
  const [shut, setShut] = useState(false), [drawer, setDrawer] = useState(false);
  const [findOpen, setFindOpen] = useState(false);
  const drawerBox = useRef<HTMLDivElement>(null);
  useEffect(() => { setShut(read()); }, []);
  useEffect(() => { setDrawer(false); }, [path]);
  useEffect(() => {
    if (!drawer) return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setDrawer(false); };
    document.addEventListener("keydown", key);
    drawerBox.current?.querySelector<HTMLElement>("button, a")?.focus();
    const was = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = was; };
  }, [drawer]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (!isFindShortcut(e)) return;
      e.preventDefault();
      setFindOpen((open) => !open);
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  const toggle = () => { setShut(!shut); write(!shut); };
  const side = shut ? SIDE_SHUT : SIDE_OPEN;

  // --app-bottom-bar: there is no bottom tab bar any more, so sticky bars on pages sit on the screen's edge.
  return (
    <div className="min-h-screen pl-[var(--side)] narrow:pl-0" style={{ "--side": `${side}px`, "--app-bottom-bar": "0px" } as React.CSSProperties}>
      <aside aria-label="Sidebar" className="fixed bottom-0 left-0 top-0 z-50 w-[var(--side)] border-0 border-r border-solid border-line-soft bg-bg-2 transition-[width] duration-200 narrow:hidden">
        <Sidebar me={me} path={path} compact={shut} onToggle={toggle} onLogout={onLogout} />
      </aside>
      {drawer && <div className="fixed inset-0 z-[80] hidden narrow:block">
        <div className="absolute inset-0 bg-[rgba(0,0,0,.6)]" onClick={() => setDrawer(false)} aria-hidden="true" />
        <div ref={drawerBox} role="dialog" aria-modal="true" aria-label="Menu"
          className="absolute bottom-0 left-0 top-0 w-[min(300px,86vw)] border-0 border-r border-solid border-line bg-bg-2 shadow-pop">
          <Sidebar me={me} path={path} compact={false} onClose={() => setDrawer(false)} onLogout={onLogout} />
        </div>
      </div>}
      <TopBar me={me} onMenu={() => setDrawer(true)} onFind={() => setFindOpen(true)} />
      {children}
      <GlobalFind open={findOpen} onClose={() => setFindOpen(false)} />
    </div>
  );
}
