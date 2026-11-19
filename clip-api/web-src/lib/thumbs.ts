"use client";
import { API, api, ApiError, getToken } from "./api";

// A clip's thumbnails (GET /v1/clips/{id}/thumbnails): the free original first, then premium AI ones.
export type Thumb = { id: string; kind: "original" | "premium"; style: string | null; instruction?: string | null; url: string | null;
  text: string | null; show_text: boolean; editable: boolean; selected: boolean; created_at?: string };
// What the server says about premium thumbnails; null while the feature is off (then the panel is hidden).
export type Premium = { credits: number; styles: { id: string; name: string }[]; instruction_max: number; consent: string; note: string } | null;
export type Gallery = { clip_id: string; selected: string; thumb_url: string | null; thumbnails: Thumb[]; pending: string[]; premium: Premium };

const base = (clipId: string) => `/v1/clips/${clipId}/thumbnails`;
export const loadGallery = (clipId: string) => api<Gallery>(base(clipId));
export const chooseThumb = (clipId: string, thumbId: string) => api<Gallery>(`${base(clipId)}/${thumbId}/select`, { method: "POST", body: {} });
export const editThumb = (clipId: string, thumbId: string, body: { text?: string | null; show_text?: boolean }) =>
  api<Gallery>(`${base(clipId)}/${thumbId}`, { method: "PATCH", body });
export const premiumQuotePath = (clipId: string) => `${base(clipId)}/premium/quote`;

// One Idempotency-Key per confirm step: a double click or a retried request is charged once.
export const newOrderKey = (clipId: string) => `thm-${clipId}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// The paid request: `credits` is the price the user saw (the API refuses it if the price changed).
export async function orderPremium(clipId: string, key: string, body: { style: string; instruction?: string; credits: number; likeness_consent: boolean }) {
  let res: Response;
  try {
    res = await fetch(`${API}${base(clipId)}/premium`, { method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}`, "Idempotency-Key": key },
      body: JSON.stringify({ ...body, confirm: true }) });
  } catch {
    throw new ApiError(0, "network", "Can't reach ClutchClips right now. Try again: the same request is never charged twice.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.error?.code || "error", data?.error?.message || `Request failed (${res.status}).`);
  return data;
}

export const styleName = (premium: Premium, id: string | null) => premium?.styles.find((s) => s.id === id)?.name || (id ? id.replace(/_/g, " ") : "Original");
