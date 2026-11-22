"use client";
// Publishing calendar: list / week / month, status chips, schedule + edit, honest when PUBLISHING=false.
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useDash } from "@/components/dash/Shell";
import { Tabs } from "@/components/dash/Tabs";
import { PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import { CalendarBoard } from "@/components/publish/CalendarBoard";
import { CalendarEmpty } from "@/components/publish/CalendarEmpty";
import { ScheduleComposer } from "@/components/publish/ScheduleComposer";
import { StatusChip } from "@/components/publish/StatusChip";
import {
  addDays, CalendarView, countByStatus, formatDay, loadPlatforms, loadPosts,
  localZone, Post, PostStatus, toLocalInputValue, weekStart,
} from "@/lib/publish";

const FILTERS: Array<PostStatus | "ALL"> = [
  "ALL", "SCHEDULED", "QUEUED", "UPLOADING", "PROCESSING", "PUBLISHED", "FAILED", "CANCELED",
];

export default function CalendarPage() {
  const { fail } = useDash();
  const zone = useMemo(() => localZone(), []);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [posts, setPosts] = useState<Post[]>([]);
  const [filter, setFilter] = useState<PostStatus | "ALL">("ALL");
  const [view, setView] = useState<CalendarView>("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [composer, setComposer] = useState<"create" | Post | null>(null);
  const [prefillAt, setPrefillAt] = useState<string>("");

  const reload = useCallback(async () => {
    try {
      const plat = await loadPlatforms();
      setEnabled(plat.enabled);
      setReason(plat.reason || "");
      if (!plat.enabled) { setPosts([]); return; }
      setPosts(await loadPosts());
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  useEffect(() => { reload(); }, [reload]);

  const counts = useMemo(() => countByStatus(posts), [posts]);
  const shown = filter === "ALL" ? posts : posts.filter((p) => p.status === filter);

  const rangeLabel = useMemo(() => {
    if (view === "week") {
      const start = weekStart(anchor);
      const end = addDays(start, 6);
      return `${formatDay(start, zone)} – ${formatDay(end, zone)}`;
    }
    if (view === "month") {
      return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: zone }).format(anchor);
    }
    return "All scheduled posts";
  }, [view, anchor, zone]);

  function shift(dir: -1 | 1) {
    if (view === "month") {
      setAnchor(new Date(anchor.getFullYear(), anchor.getMonth() + dir, 1));
      return;
    }
    if (view === "week") {
      setAnchor(addDays(weekStart(anchor), dir * 7));
      return;
    }
  }

  function openCreate(day?: Date) {
    if (day) {
      const local = new Date(day);
      local.setHours(19, 30, 0, 0);
      setPrefillAt(toLocalInputValue(local.toISOString()));
    } else {
      setPrefillAt("");
    }
    setComposer("create");
  }

  async function cancel(id: string) {
    setBusy(id); setNote("");
    try {
      await api(`/v1/posts/${id}/cancel`, { method: "POST", body: {} });
      setNote("Canceled.");
      await reload();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Could not cancel.");
    } finally { setBusy(null); }
  }

  async function retry(id: string) {
    setBusy(id); setNote("");
    try {
      await api(`/v1/posts/${id}/retry`, { method: "POST", body: {} });
      setNote("Re-queued.");
      await reload();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Could not retry.");
    } finally { setBusy(null); }
  }

  return (
    <div className="grid gap-6">
      <div className={PAGE_HEAD}>
        <div className="grid gap-1">
          <h1 className={PAGE_TITLE}>Social schedule</h1>
          <p className="m-0 max-w-[58ch] text-[14px] text-muted">
            Publishing calendar in {zone}. Status is live from the job queue — scheduled, draft-queue, published, or failed — never a fake success.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/dashboard/social-accounts/" className="btn small ghost">Social accounts</Link>
          {enabled && (
            <button type="button" className="btn small primary" onClick={() => openCreate()}>
              Schedule clip
            </button>
          )}
        </div>
      </div>

      {enabled === null && (
        <p className="m-0 text-[14px] text-muted">Loading calendar…</p>
      )}

      {enabled === false && (
        <CalendarEmpty mode="disabled" reason={reason} />
      )}

      {enabled && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Tabs
              seg
              label="Calendar view"
              panel="calendar-board"
              value={view}
              onChange={setView}
              tabs={[["week", "Week"], ["month", "Month"], ["list", "List"]]}
            />
            {view !== "list" && (
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className="btn small ghost" onClick={() => shift(-1)} aria-label="Previous">
                  ←
                </button>
                <button type="button" className="btn small ghost" onClick={() => setAnchor(new Date())}>
                  Today
                </button>
                <button type="button" className="btn small ghost" onClick={() => shift(1)} aria-label="Next">
                  →
                </button>
                <span className="text-[13px] tabular-nums text-muted">{rangeLabel}</span>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Post status">
            {FILTERS.map((f) => {
              const n = counts[f];
              const active = filter === f;
              return (
                <button
                  key={f}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`inline-flex items-center gap-2 rounded-pill border border-solid px-3 py-[5px] text-[12.5px] font-medium transition-colors ${
                    active
                      ? "border-lime/50 bg-lime-wash text-text"
                      : "border-line-soft bg-transparent text-muted hover:border-line-strong hover:text-text"
                  }`}
                  onClick={() => setFilter(f)}
                >
                  {f === "ALL" ? "All" : <StatusChip status={f} compact />}
                  <span className="tabular-nums text-fg-3">{n}</span>
                </button>
              );
            })}
          </div>

          {note && <p className="m-0 text-[13px] text-cyan" role="status">{note}</p>}

          {composer && (
            <ScheduleComposer
              editing={composer === "create" ? null : composer}
              initialAtLocal={composer === "create" ? prefillAt : undefined}
              onClose={() => setComposer(null)}
              onSaved={async () => { setNote(composer === "create" ? "Scheduled." : "Updated."); await reload(); }}
            />
          )}

          {!posts.length && !composer ? (
            <CalendarEmpty mode="empty" canSchedule onSchedule={() => openCreate()} />
          ) : (
            <div id="calendar-board" role="tabpanel" aria-label={view}>
              <CalendarBoard
                view={view}
                anchor={anchor}
                posts={shown}
                zone={zone}
                busyId={busy}
                onSelectDay={(day) => openCreate(day)}
                onEdit={(p) => setComposer(p)}
                onCancel={cancel}
                onRetry={retry}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
