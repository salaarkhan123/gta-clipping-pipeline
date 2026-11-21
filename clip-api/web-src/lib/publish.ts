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

export const READINESS_LABEL: Record<Readiness, string> = {
  awaiting_approval: "Pending platform approval",
  not_configured: "Not configured on this server",
  held: "Not offered yet",
  production_verified: "Live",
};

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

export function idemKey(clipId: string, accountIds: string[]): string {
  return `pub_${clipId}_${accountIds.slice().sort().join("_")}_${Date.now()}`;
}
