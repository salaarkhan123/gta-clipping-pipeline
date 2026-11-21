"use client";
// Brand kit: two-column editor — settings left, live preview right. A kit is a saved look
// (/v1/templates/custom); plan limits how many an account keeps. Saving is free.
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { KitPicker, NameDialog, UndoRedo } from "@/components/dash/brand/KitBar";
import { KitPreview, Shape, SHAPES } from "@/components/dash/brand/KitPreview";
import { KitForm } from "@/components/dash/brand/Sections";
import { useDash } from "@/components/dash/Shell";
import { BackTitle } from "@/components/dash/ui";
import { ApiError } from "@/lib/api";
import {
  blankKit, createKit, deleteKit, duplicateKit, FIRST_KIT_NAME, getDefaultKitId, Kit, kitFrom, Kits,
  KIT_NAME_MAX, loadKits, sameKit, setDefaultKitId, updateKit,
} from "@/lib/brandkit";
import { change, History, redo, startHistory, undo } from "@/lib/history";
import { useClipOptions } from "@/lib/options";

type Naming = { mode: "new" | "rename" | "duplicate"; problem: string } | null;

export default function BrandKit() {
  const { fail, say } = useDash();
  const listed = useClipOptions();
  const [store, setStore] = useState<Kits | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [saved, setSaved] = useState<Kit | null>(null);
  const [h, setH] = useState<History<Kit> | null>(null);
  const [shape, setShape] = useState<Shape>("9:16");
  const [busy, setBusy] = useState(false), [naming, setNaming] = useState<Naming>(null);
  const [draftName, setDraftName] = useState(FIRST_KIT_NAME);
  const [defaultId, setDefaultId] = useState<string | null>(null);

  const open = useCallback((kits: Kits, id: string | null) => {
    if (!listed) return;
    const found = kits.kits.find((k) => k.id === id) || null;
    const kit = found ? kitFrom(found, listed) : blankKit(listed);
    setCurrent(found?.id || null);
    setSaved(found ? kit : null);
    setH(startHistory(kit));
    setDraftName(found?.name || (kits.kits.length ? "New kit" : FIRST_KIT_NAME));
    if ((SHAPES as readonly string[]).includes(kit.aspect)) setShape(kit.aspect as Shape);
  }, [listed]);

  useEffect(() => {
    if (!listed) return;
    setDefaultId(getDefaultKitId());
    loadKits().then((k) => {
      setStore(k);
      const prefer = getDefaultKitId();
      const start = (prefer && k.kits.some((x) => x.id === prefer) ? prefer : null) || k.kits[0]?.id || null;
      open(k, start);
    }).catch((e) => { fail(e); setStore({ kits: [], limit: null }); open({ kits: [], limit: null }, null); });
  }, [listed]);   // eslint-disable-line react-hooks/exhaustive-deps

  const kit = h?.now || null;
  const dirty = !!(kit && listed && (saved ? !sameKit(kit, saved, listed) : true));
  const nameDirty = !!(current && store && draftName.trim() && draftName.trim() !== (store.kits.find((k) => k.id === current)?.name || ""));
  const unsavedEdits = !!(kit && listed && (saved ? (!sameKit(kit, saved, listed) || nameDirty) : !!h?.past.length));
  const set = useCallback((patch: Partial<Kit>) => setH((x) => (x ? change(x, patch) : x)), []);
  useEffect(() => { if (kit && (SHAPES as readonly string[]).includes(kit.aspect)) setShape(kit.aspect as Shape); }, [kit?.aspect]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      if ((e.target as HTMLElement).closest("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      setH((x) => (x ? (e.shiftKey ? redo(x) : undo(x)) : x));
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {
    if (!unsavedEdits) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsavedEdits]);

  const full = !!store && store.limit !== null && store.kits.length >= store.limit;
  const limitNote = store?.limit != null ? `${store.kits.length} of ${store.limit} kits on your plan.` : "";
  const leave = () => !unsavedEdits || window.confirm("Discard the changes you haven't saved?");
  const fallbackName = store?.kits.length ? "New kit" : FIRST_KIT_NAME;

  async function saveNew(name: string) {
    if (!kit || !listed || !store) return;
    setBusy(true);
    try {
      const made = await createKit(name, kit, listed);
      const next = { ...store, kits: [{ id: String(made.id), name: made.name, options: made.options }, ...store.kits] };
      setStore(next); setCurrent(String(made.id)); setSaved(kit); setDraftName(made.name); setNaming(null);
      say(`Saved "${made.name}". Pick it under Brand kit when you start a job.`);
    } catch (e) {
      if (e instanceof ApiError && e.status !== 401) setNaming({ mode: "new", problem: e.message }); else fail(e);
    } finally { setBusy(false); }
  }
  async function saveChanges() {
    if (!kit || !listed || !store) return;
    if (!current) { setNaming({ mode: "new", problem: "" }); return; }
    setBusy(true);
    try {
      const name = draftName.trim().slice(0, KIT_NAME_MAX);
      const done = await updateKit(current, { kit, ...(name && name !== store.kits.find((k) => k.id === current)?.name ? { name } : {}) }, listed);
      setStore({ ...store, kits: store.kits.map((k) => (k.id === current ? { ...k, name: done.name, options: done.options } : k)) });
      setSaved(kit);
      setDraftName(done.name);
      say("Changes saved.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function rename(name: string) {
    if (!current || !store || !listed) return;
    setBusy(true);
    try {
      const done = await updateKit(current, { name }, listed);
      setStore({ ...store, kits: store.kits.map((k) => (k.id === current ? { ...k, name: done.name } : k)) });
      setDraftName(done.name);
      setNaming(null);
    } catch (e) {
      if (e instanceof ApiError && e.status !== 401) setNaming({ mode: "rename", problem: e.message }); else fail(e);
    } finally { setBusy(false); }
  }
  async function duplicate(name: string) {
    if (!kit || !listed || !store) return;
    setBusy(true);
    try {
      const made = await duplicateKit(name, kit, listed);
      const next = { ...store, kits: [{ id: String(made.id), name: made.name, options: made.options }, ...store.kits] };
      setStore(next); open(next, String(made.id)); setNaming(null);
      say(`Duplicated as "${made.name}".`);
    } catch (e) {
      if (e instanceof ApiError && e.status !== 401) setNaming({ mode: "duplicate", problem: e.message }); else fail(e);
    } finally { setBusy(false); }
  }
  async function remove() {
    if (!current || !store) return;
    const k = store.kits.find((x) => x.id === current);
    if (!window.confirm(`Delete "${k?.name}"? Clips already made with it don't change.`)) return;
    setBusy(true);
    try {
      await deleteKit(current);
      if (defaultId === current) { setDefaultKitId(null); setDefaultId(null); }
      const next = { ...store, kits: store.kits.filter((x) => x.id !== current) };
      setStore(next); open(next, next.kits[0]?.id || null);
      say("Kit deleted.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  }
  function makeDefault() {
    if (!current) return;
    setDefaultKitId(current);
    setDefaultId(current);
    say("Default kit set for this browser.");
  }

  const currentName = useMemo(() => draftName || fallbackName, [draftName, fallbackName]);
  if (!listed || !store || !kit || !h) return <p className="muted">Loading…</p>;

  const dialogTitle = naming?.mode === "rename" ? "Rename kit" : naming?.mode === "duplicate" ? "Duplicate kit" : "Save as a new kit";
  const dialogStart = naming?.mode === "rename" ? currentName : naming?.mode === "duplicate" ? `${currentName} copy` : current ? `${currentName} copy` : currentName;
  const dialogSave = naming?.mode === "rename" ? rename : naming?.mode === "duplicate" ? duplicate : saveNew;

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="mr-auto grid min-w-0 gap-1">
          <BackTitle title="Brand kit" crumbs={[{ label: "Home", href: "/dashboard/" }, { label: "Brand kit" }]} />
          <p className="m-0 text-[14px] text-muted">Settings on the left, live preview on the right. Save a look once, pick it in any job.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 narrow:w-full">
          <div className="narrow:w-full"><KitPicker kits={store.kits} current={current} draftName={fallbackName} defaultId={defaultId}
            onPick={(id) => { if (id !== current && leave()) open(store, id); }} onNew={() => { if (leave()) open(store, null); }}
            onRename={() => setNaming({ mode: "rename", problem: "" })}
            onDuplicate={() => setNaming({ mode: "duplicate", problem: "" })}
            onSetDefault={makeDefault} onDelete={remove} /></div>
          <UndoRedo canUndo={h.past.length > 0} canRedo={h.future.length > 0} onUndo={() => setH(undo(h))} onRedo={() => setH(redo(h))} />
          <button type="button" className="btn small ghost" disabled={busy} onClick={() => setNaming({ mode: "new", problem: "" })}>Save as</button>
          <button type="button" className="btn small primary" disabled={busy || (!dirty && !nameDirty && !!current)} onClick={saveChanges}>
            {busy ? "Saving…" : current ? "Save" : "Save kit"}</button>
        </div>
      </div>
      {full && !current && <p className="notice m-0">Your plan keeps {store.limit} {store.limit === 1 ? "kit" : "kits"}, and you have {store.kits.length}. Delete one or <Link href="/dashboard/pricing/">upgrade</Link> to save another.</p>}

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(320px,420px)] items-start gap-6 mid:grid-cols-1">
        <div className="mid:order-2 min-w-0">
          <KitForm kit={kit} listed={listed} set={set} name={draftName} onName={setDraftName} />
        </div>
        <aside aria-label="Preview" className="sticky top-[calc(theme(spacing.topbar)+16px)] mid:static mid:order-1">
          <div className="rounded-[20px] border border-solid border-line-soft bg-card p-4">
            <KitPreview kit={kit} shape={shape} onShape={setShape} />
          </div>
        </aside>
      </div>

      {naming && <NameDialog key={naming.mode} title={dialogTitle} action="Save"
        start={dialogStart}
        note={naming.mode !== "rename" ? (full ? `Your plan keeps ${store.limit} ${store.limit === 1 ? "kit" : "kits"}. Delete one or upgrade to save another.` : limitNote) : undefined}
        full={naming.mode !== "rename" && full} busy={busy} problem={naming.problem}
        onSave={dialogSave} onClose={() => setNaming(null)} />}
    </div>
  );
}
