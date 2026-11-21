"use client";
// Timezone-aware post calendar: scheduled / draft-ish queued / published / failed / retry / cancel.
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useDash } from "@/components/dash/Shell";
import { PAGE_HEAD, PAGE_TITLE } from "@/components/dash/ui";
import {
  formatWhen, loadPlatforms, loadPosts, localZone, Post, STATUS_LABEL, PostStatus,
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
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState("");

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

  const shown = filter === "ALL" ? posts : posts.filter((p) => p.status === filter);

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
          <h1 className={PAGE_TITLE}>Calendar</h1>
          <p className="m-0 max-w-[56ch] text-[14px] text-muted">
            Scheduled and published posts in {zone}. Status is live from the job queue — never a fake success.
          </p>
        </div>
        <Link href="/dashboard/social-accounts/" className="btn small ghost">Social accounts</Link>
      </div>

      {enabled === false && (
        <p className="m-0 rounded-20 border border-solid border-line-soft bg-card p-5 text-[14px] text-muted">
          {reason || "Publishing is not enabled yet."} When it is on, scheduled and published clips appear here.
        </p>
      )}

      {enabled && (
        <>
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Post status">
            {FILTERS.map((f) => (
              <button key={f} type="button" role="tab" aria-selected={filter === f}
                className={`btn small ${filter === f ? "primary" : "ghost"}`}
                onClick={() => setFilter(f)}>
                {f === "ALL" ? "All" : STATUS_LABEL[f]}
              </button>
            ))}
          </div>
          {note && <p className="m-0 text-[13px] text-cyan" role="status">{note}</p>}
          {!shown.length && <p className="m-0 text-[14px] text-muted">No posts in this view.</p>}
          <ul className="m-0 grid list-none gap-2 p-0">
            {shown.map((p) => (
              <li key={p.id} className="grid gap-2 rounded-20 border border-solid border-line-soft bg-card p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-[15px] font-medium">{p.platform} · {STATUS_LABEL[p.status]}</span>
                  <span className="text-[12.5px] tabular-nums text-muted">
                    {formatWhen(p.publish_at || p.published_at || p.created_at, zone)}
                  </span>
                </div>
                {(p.title || p.caption) && (
                  <p className="m-0 text-[13px] text-muted line-clamp-2">{p.title || p.caption}</p>
                )}
                {p.error_message && (
                  <p className="m-0 text-[13px] text-rose" role="alert">{p.error_code}: {p.error_message}</p>
                )}
                {p.external_url && (
                  <a href={p.external_url} target="_blank" rel="noreferrer" className="text-[13px] text-cyan underline-offset-2 hover:underline">
                    View on {p.platform}
                  </a>
                )}
                <div className="flex flex-wrap gap-2">
                  <Link href={`/dashboard/project/?clip=${p.clip_id}`} className="btn small ghost">Clip</Link>
                  {p.can_cancel && (
                    <button type="button" className="btn small ghost" disabled={busy === p.id}
                      onClick={() => cancel(p.id)}>Cancel</button>
                  )}
                  {p.can_retry && (
                    <button type="button" className="btn small primary" disabled={busy === p.id}
                      onClick={() => retry(p.id)}>Retry</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
