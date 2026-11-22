// Publishing client helpers. Tokens never live here — only public status and account metadata.
import { api, ApiError } from "./api";

export type Readiness = "awaiting_approval" | "not_configured" | "held" | "production_verified";

export type Platform = {
  id: string;
  name: string;
  readiness: Readiness;
  operational: boolean;
  configured: boolean;
  limits: { min_sec: number; max_sec: number; max_bytes: number; title_max: number | null; caption_max: number };
  privacy_options: string[];
  fields: string[];
  notes: string[];
};

export type SocialAccount = {
  id: string;
  platform: string;
  external_id: string;
  display_name: string | null;
  avatar_url: string | null;
  status: "active" | "needs_reconnect" | "revoked";
  created_at: string | null;
};

export type PostStatus =
  | "SCHEDULED" | "QUEUED" | "UPLOADING" | "PROCESSING" | "PUBLISHED" | "FAILED" | "CANCELED";

export type Post = {
  id: string;
  clip_id: string;
  social_account_id: string;
  platform: string;
  title: string | null;
  caption: string | null;
  hashtags: string[];
  privacy: string | null;
  publish_at: string | null;
  status: PostStatus;
  attempts: number;
  external_url: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string | null;
  published_at: string | null;
  can_cancel: boolean;
  can_edit: boolean;
  can_retry: boolean;
};

export const STATUS_LABEL: Record<PostStatus, string> = {
  SCHEDULED: "Scheduled",
  QUEUED: "Queued",
  UPLOADING: "Uploading",
  PROCESSING: "Processing",
  PUBLISHED: "Published",
  FAILED: "Failed",
  CANCELED: "Canceled",
};

/** Chip surface: border + wash + text. Status colour only — never a success claim. */
export const STATUS_TONE: Record<PostStatus, string> = {
  SCHEDULED: "border-[rgba(60,240,255,.35)] bg-cyan-wash text-cyan",
  QUEUED: "border-line-strong bg-chip text-soft",
  UPLOADING: "border-[rgba(255,182,72,.4)] bg-[rgba(255,182,72,.12)] text-warn",
  PROCESSING: "border-[rgba(255,182,72,.4)] bg-[rgba(255,182,72,.12)] text-warn",
  PUBLISHED: "border-[rgba(184,255,60,.4)] bg-lime-wash text-lime",
  FAILED: "border-[rgba(255,92,122,.4)] bg-[rgba(255,92,122,.12)] text-danger",
  CANCELED: "border-line-soft bg-surface text-muted",
};

export const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube Shorts",
  tiktok: "TikTok",
  instagram: "Instagram Reels",
  facebook: "Facebook Reels",
};

export const READINESS_LABEL: Record<Readiness, string> = {
  awaiting_approval: "Pending platform approval",
  not_configured: "Not configured on this server",
  held: "Not offered yet",
  production_verified: "Live",
};

export type CalendarView = "list" | "week" | "month";

/** Gaming-creator tips shown in empty / disabled calendar states. */
export const SCHEDULE_TIPS = [
  "Space GTA and ranked clips 3–4 hours apart so Shorts and Reels do not cannibalize each other.",
  "Weeknights 7–9pm in your viewers' zone usually beat midday drops for reaction clips.",
  "Keep one draft slot for the best kill or clutch — schedule filler only after the hero clip is locked.",
  "Failed posts stay Failed until you retry. Reconnect the account first if the error is permission or token.",
] as const;

export type SampleSlot = {
  id: string;
  platform: string;
  status: PostStatus;
  title: string;
  whenLabel: string;
  tip: string;
};

/** Illustrative slots only — never mixed into live API rows. */
export const SAMPLE_SCHEDULE: SampleSlot[] = [
  {
    id: "sample-1", platform: "youtube", status: "SCHEDULED",
    title: "GTA: alley chase → jump scare", whenLabel: "Tue · 7:30pm",
    tip: "Hero clip first in the week.",
  },
  {
    id: "sample-2", platform: "tiktok", status: "SCHEDULED",
    title: "Streamer reaction to the clutch", whenLabel: "Wed · 8:15pm",
    tip: "Reaction cut performs after the play itself.",
  },
  {
    id: "sample-3", platform: "instagram", status: "PUBLISHED",
    title: "Ranked win montage (9:16)", whenLabel: "Mon · 6:00pm",
    tip: "Already live — calendar shows the real status.",
  },
  {
    id: "sample-4", platform: "youtube", status: "FAILED",
    title: "Failstack highlight (retry after reconnect)", whenLabel: "Thu · 9:00pm",
    tip: "Failed stays Failed until you hit Retry.",
  },
];

export async function loadPlatforms(): Promise<{ platforms: Platform[]; enabled: boolean; reason?: string }> {
  try {
    const data = await api<{ platforms: Platform[] }>("/v1/publish/platforms");
    return { platforms: data.platforms || [], enabled: true };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.code === "publishing_disabled")) {
      return { platforms: [], enabled: false, reason: "Publishing is not enabled on this server yet." };
    }
    throw e;
  }
}

export async function loadAccounts(): Promise<SocialAccount[]> {
  const data = await api<{ accounts: SocialAccount[] }>("/v1/social-accounts");
  return data.accounts || [];
}

export async function loadPosts(params: { from?: string; to?: string; status?: string; clip_id?: string } = {}): Promise<Post[]> {
  const q = new URLSearchParams();
  if (params.from) q.set("from", params.from);
  if (params.to) q.set("to", params.to);
  if (params.status) q.set("status", params.status);
  if (params.clip_id) q.set("clip_id", params.clip_id);
  const qs = q.toString();
  // Concatenate query so the contract path scanner only sees the /v1/posts prefix.
  const data = await api<{ posts: Post[] }>(qs ? ("/v1/posts?" + qs) : "/v1/posts");
  return data.posts || [];
}

export function localZone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; }
  catch { return "UTC"; }
}

export function formatWhen(iso: string | null, zone = localZone()): string {
  if (!iso) return "Now";
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: zone, dateStyle: "medium", timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatTime(iso: string | null, zone = localZone()): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: zone, hour: "numeric", minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatDay(d: Date, zone = localZone()): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: zone, weekday: "short", month: "short", day: "numeric",
    }).format(d);
  } catch {
    return d.toISOString().slice(0, 10);
  }
}

/** Instant used for calendar placement: schedule time, else published, else created. */
export function postInstant(p: Post): Date | null {
  const raw = p.publish_at || p.published_at || p.created_at;
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

/** Monday-first week containing `anchor`. */
export function weekStart(anchor: Date): Date {
  const day = startOfLocalDay(anchor);
  const dow = (day.getDay() + 6) % 7; // Mon=0 … Sun=6
  return addDays(day, -dow);
}

export function monthGrid(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const start = weekStart(first);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

export function sameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

export function postsOnDay(posts: Post[], day: Date): Post[] {
  return posts.filter((p) => {
    const t = postInstant(p);
    return t ? sameLocalDay(t, day) : false;
  }).sort((a, b) => {
    const ta = postInstant(a)?.getTime() ?? 0;
    const tb = postInstant(b)?.getTime() ?? 0;
    return ta - tb;
  });
}

export function countByStatus(posts: Post[]): Record<PostStatus | "ALL", number> {
  const out: Record<PostStatus | "ALL", number> = {
    ALL: posts.length,
    SCHEDULED: 0, QUEUED: 0, UPLOADING: 0, PROCESSING: 0,
    PUBLISHED: 0, FAILED: 0, CANCELED: 0,
  };
  for (const p of posts) out[p.status] += 1;
  return out;
}

export function toLocalInputValue(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function idemKey(clipId: string, accountIds: string[]): string {
  return `pub_${clipId}_${accountIds.slice().sort().join("_")}_${Date.now()}`;
}
