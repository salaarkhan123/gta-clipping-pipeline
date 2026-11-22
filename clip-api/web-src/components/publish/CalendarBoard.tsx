"use client";
import Link from "next/link";
import {
  addDays, CalendarView, formatDay, formatTime, formatWhen, localZone, monthGrid,
  PLATFORM_LABEL, Post, postsOnDay, sameLocalDay, startOfLocalDay, weekStart,
} from "@/lib/publish";
import { StatusChip } from "./StatusChip";

type Props = {
  view: CalendarView;
  anchor: Date;
  posts: Post[];
  zone?: string;
  busyId: string | null;
  onSelectDay?: (day: Date) => void;
  onEdit: (post: Post) => void;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
};

function PostActions({
  post, busyId, onEdit, onCancel, onRetry,
}: {
  post: Post; busyId: string | null;
  onEdit: (p: Post) => void; onCancel: (id: string) => void; onRetry: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Link href={`/dashboard/project/?clip=${post.clip_id}`} className="btn small ghost">Clip</Link>
      {post.can_edit && (
        <button type="button" className="btn small ghost" disabled={busyId === post.id}
          onClick={() => onEdit(post)}>Edit</button>
      )}
      {post.can_cancel && (
        <button type="button" className="btn small ghost" disabled={busyId === post.id}
          onClick={() => onCancel(post.id)}>Cancel</button>
      )}
      {post.can_retry && (
        <button type="button" className="btn small primary" disabled={busyId === post.id}
          onClick={() => onRetry(post.id)}>Retry</button>
      )}
    </div>
  );
}

function PostCard({
  post, zone, busyId, onEdit, onCancel, onRetry, compact,
}: {
  post: Post; zone: string; busyId: string | null; compact?: boolean;
  onEdit: (p: Post) => void; onCancel: (id: string) => void; onRetry: (id: string) => void;
}) {
  const when = post.publish_at || post.published_at || post.created_at;
  return (
    <article className={`grid gap-2 rounded-16 border border-solid border-line-soft bg-card ${compact ? "p-2.5" : "p-4"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`font-medium ${compact ? "text-[12.5px]" : "text-[14px]"}`}>
          {PLATFORM_LABEL[post.platform] || post.platform}
        </span>
        <StatusChip status={post.status} compact={compact} />
      </div>
      {(post.title || post.caption) && (
        <p className={`m-0 text-muted line-clamp-2 ${compact ? "text-[12px]" : "text-[13px]"}`}>
          {post.title || post.caption}
        </p>
      )}
      <p className={`m-0 tabular-nums text-fg-3 ${compact ? "text-[11px]" : "text-[12.5px]"}`}>
        {compact ? formatTime(when, zone) : formatWhen(when, zone)}
      </p>
      {post.error_message && (
        <p className="m-0 text-[12.5px] text-danger" role="alert">
          {post.error_code}: {post.error_message}
        </p>
      )}
      {post.external_url && (
        <a href={post.external_url} target="_blank" rel="noreferrer"
          className="text-[12.5px] text-cyan underline-offset-2 hover:underline">
          View on {PLATFORM_LABEL[post.platform] || post.platform}
        </a>
      )}
      {!compact && (
        <PostActions post={post} busyId={busyId} onEdit={onEdit} onCancel={onCancel} onRetry={onRetry} />
      )}
    </article>
  );
}

export function CalendarBoard({
  view, anchor, posts, zone = localZone(), busyId, onSelectDay, onEdit, onCancel, onRetry,
}: Props) {
  if (view === "list") {
    if (!posts.length) {
      return <p className="m-0 text-[14px] text-muted">No posts match this filter.</p>;
    }
    return (
      <ul className="m-0 grid list-none gap-2 p-0">
        {posts.map((p) => (
          <li key={p.id}>
            <PostCard post={p} zone={zone} busyId={busyId} onEdit={onEdit} onCancel={onCancel} onRetry={onRetry} />
          </li>
        ))}
      </ul>
    );
  }

  if (view === "week") {
    const start = weekStart(anchor);
    const days = Array.from({ length: 7 }, (_, i) => addDays(start, i));
    const today = startOfLocalDay(new Date());
    return (
      <div className="grid gap-3" role="grid" aria-label="Week calendar">
        <div className="grid grid-cols-7 gap-2 narrow:grid-cols-1">
          {days.map((day) => {
            const dayPosts = postsOnDay(posts, day);
            const isToday = sameLocalDay(day, today);
            return (
              <div
                key={day.toISOString()}
                role="gridcell"
                className={`grid content-start gap-2 rounded-16 border border-solid p-2.5 min-h-[140px] ${
                  isToday ? "border-lime/40 bg-lime-wash/40" : "border-line-soft bg-panel"
                }`}
              >
                <button
                  type="button"
                  className="flex w-full items-baseline justify-between gap-1 border-0 bg-transparent p-0 text-left"
                  onClick={() => onSelectDay?.(day)}
                >
                  <span className={`text-[12.5px] font-medium ${isToday ? "text-lime" : "text-muted"}`}>
                    {formatDay(day, zone)}
                  </span>
                  <span className="text-[11px] tabular-nums text-fg-3">{dayPosts.length || ""}</span>
                </button>
                {dayPosts.length === 0 && (
                  <p className="m-0 text-[11px] text-fg-3">—</p>
                )}
                <ul className="m-0 grid list-none gap-1.5 p-0">
                  {dayPosts.slice(0, 4).map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        className="grid w-full gap-0.5 rounded-12 border border-solid border-line-soft bg-card px-2 py-1.5 text-left hover:border-lime/50"
                        onClick={() => (p.can_edit ? onEdit(p) : undefined)}
                      >
                        <span className="truncate text-[11px] font-medium text-soft">
                          {PLATFORM_LABEL[p.platform] || p.platform}
                        </span>
                        <span className="flex items-center justify-between gap-1">
                          <span className="tabular-nums text-[10.5px] text-fg-3">
                            {formatTime(p.publish_at || p.published_at || p.created_at, zone)}
                          </span>
                          <StatusChip status={p.status} compact />
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                {dayPosts.length > 4 && (
                  <p className="m-0 text-[11px] text-muted">+{dayPosts.length - 4} more</p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // month
  const cells = monthGrid(anchor);
  const today = startOfLocalDay(new Date());
  const inMonth = (d: Date) => d.getMonth() === anchor.getMonth();
  const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return (
    <div className="grid gap-2" role="grid" aria-label="Month calendar">
      <div className="grid grid-cols-7 gap-1 narrow:hidden">
        {weekdays.map((w) => (
          <div key={w} className="px-1 text-[11px] font-medium uppercase tracking-[0.04em] text-fg-3">{w}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1 narrow:grid-cols-1">
        {cells.map((day) => {
          const dayPosts = postsOnDay(posts, day);
          const isToday = sameLocalDay(day, today);
          const muted = !inMonth(day);
          return (
            <div
              key={day.toISOString()}
              role="gridcell"
              className={`grid content-start gap-1 rounded-12 border border-solid p-1.5 min-h-[88px] narrow:min-h-0 ${
                isToday ? "border-lime/40 bg-lime-wash/30" : "border-line-soft bg-panel"
              } ${muted ? "opacity-45 narrow:hidden" : ""}`}
            >
              <button
                type="button"
                className="flex w-full items-center justify-between border-0 bg-transparent p-0 text-left"
                onClick={() => onSelectDay?.(day)}
              >
                <span className={`text-[12px] tabular-nums ${isToday ? "font-semibold text-lime" : "text-muted"}`}>
                  {day.getDate()}
                </span>
                {dayPosts.length > 0 && (
                  <span className="text-[10px] tabular-nums text-fg-3">{dayPosts.length}</span>
                )}
              </button>
              <ul className="m-0 hidden list-none gap-1 p-0 narrow:grid">
                {dayPosts.map((p) => (
                  <li key={p.id}>
                    <PostCard post={p} zone={zone} busyId={busyId} compact
                      onEdit={onEdit} onCancel={onCancel} onRetry={onRetry} />
                  </li>
                ))}
              </ul>
              <ul className="m-0 grid list-none gap-0.5 p-0 narrow:hidden">
                {dayPosts.slice(0, 3).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      title={`${PLATFORM_LABEL[p.platform] || p.platform} · ${p.status}`}
                      className="flex w-full items-center gap-1 truncate rounded-8 border-0 bg-chip px-1 py-0.5 text-left hover:bg-chip-hover"
                      onClick={() => (p.can_edit ? onEdit(p) : undefined)}
                    >
                      <span className={`h-1.5 w-1.5 flex-none rounded-full ${
                        p.status === "PUBLISHED" ? "bg-lime"
                          : p.status === "FAILED" ? "bg-danger"
                          : p.status === "SCHEDULED" ? "bg-cyan"
                          : "bg-warn"
                      }`} aria-hidden="true" />
                      <span className="truncate text-[10px] text-soft">
                        {formatTime(p.publish_at || p.published_at || p.created_at, zone)}
                      </span>
                    </button>
                  </li>
                ))}
                {dayPosts.length > 3 && (
                  <li className="px-1 text-[10px] text-fg-3">+{dayPosts.length - 3}</li>
                )}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
