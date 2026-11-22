// Creators League: the shapes the API returns (app/routes_league.py) and the words the screens use for them.
// The API enforces every rule; the screens only show and explain.
import { useEffect, useState } from "react";
import { api } from "./api";

export type Platform = "tiktok" | "youtube" | "instagram";
export type Phase = "upcoming" | "live" | "ended" | "final";
export type Prize = { place: 1 | 2 | 3; amount_cents: number; currency: string; label: string | null };
export type Competition = { slug: string; name: string; starts_at: string; ends_at: string; phase: Phase; accepting_entries: boolean;
  participants: number; rules_version: string; cash_prizes: boolean; prizes: Prize[] | null; prize_pool_cents: number | null; prize_note: string | null };
export type Row = { rank: number; username: string | null; avatar: string; has_profile: boolean; game: string | null; platform: Platform;
  video_url: string; thumb_url: string | null; views: number | null; views_verified: boolean; views_source: string | null;
  observed_at: string | null; status: "provisional" | "winner"; final_place: number | null };
export type Board = { competition: Competition; updated_at: string | null; entries: Row[] };
export type RulesSection = { id: string; title: string; needs_legal_review: boolean; body: string[] };
export type Attribution = { url: string; text: string };
export type Rules = { version: string; status: string; legally_reviewed: boolean; sections: RulesSection[]; attribution: Attribution };
export type Profile = { username: string; avatar: string; games: string[]; is_public: boolean; hidden: boolean };
export type Current = { competition: Competition | null; top: Row[] };
export type EntryStatus = "pending" | "approved" | "rejected" | "disqualified";
export type MyEntry = { id: string; status: EntryStatus; status_reason: string | null; platform: Platform; video_url: string; game: string | null;
  clip_id: string; submitted_at: string; rank: number | null; views: number | null; observed_at: string | null; final_place: number | null;
  prize_status: string | null };
export type MyClip = { id: string; title: string | null; thumb_url: string | null; duration_sec: number; created_at: string };
export type Me = { email_verified: boolean; profile: Profile | null; avatars: string[]; clips: MyClip[]; competition: Competition | null;
  entry: MyEntry | null; attribution: Attribution; rules_version: string };

export const PLATFORM_LABEL: Record<Platform, string> = { tiktok: "TikTok", youtube: "YouTube Shorts", instagram: "Instagram Reels" };
export const PLATFORM_HINT: Record<Platform, string> = {
  tiktok: "https://www.tiktok.com/@you/video/1234567890123456789",
  youtube: "https://www.youtube.com/shorts/AbCdEfGhIjK",
  instagram: "https://www.instagram.com/reel/AbCdEfGhIjK/",
};
export const PHASE_LABEL: Record<Phase, string> = { upcoming: "Opens soon", live: "Live now", ended: "Entries closed", final: "Final results" };
// What a creator is told about their entry. Rejected and disqualified also show the reviewer's reason.
export const ENTRY_STATUS: Record<EntryStatus, { label: string; text: string }> = {
  pending: { label: "Pending review", text: "A person on our team checks every entry. Yours appears on the leaderboard once it is approved." },
  approved: { label: "Approved", text: "Your entry is on the leaderboard." },
  rejected: { label: "Rejected", text: "Your entry was not accepted. If you fix the problem below, contact us and a reviewer can approve it." },
  disqualified: { label: "Disqualified", text: "Your entry was removed from this competition." },
};
// The statuses each review may be taken from: ENTRY_RULES in app/league.py, one line per action
// (tests/test_league_screens.py checks the two match). The API answers 409 to anything else.
export type EntryAction = "approve" | "reject" | "disqualify";
export const ENTRY_RULES: Record<EntryAction, string[]> = {
  approve: ["pending", "rejected"],
  reject: ["pending", "approved"],
  disqualify: ["pending", "approved"],
};
export type CompetitionAction = "open" | "close" | "reopen" | "finalize";
export const COMPETITION_RULES: Record<CompetitionAction, string[]> = {
  open: ["draft"],
  close: ["open"],
  reopen: ["closed"],
  finalize: ["closed"],
};

// The avatars a creator can pick: a colour behind their initial. No image is uploaded or linked.
export const AVATAR_COLOR: Record<string, string> = {
  lime: "#b8ff3c", violet: "#b49cff", sky: "#7cc8ff", amber: "#ffc266", rose: "#ff8fa8", slate: "#aab2bd",
};

const HOSTS = ["https://www.tiktok.com/", "https://www.youtube.com/shorts/", "https://www.instagram.com/reel/"];
// The API stores only links it rebuilt itself; this is a second check before one becomes an href.
export const safeVideoUrl = (url: string | null | undefined) => (url && HOSTS.some((h) => url.startsWith(h)) ? url : null);

export const views = (n: number | null) => (n === null ? "No count yet" : n.toLocaleString("en-US"));
export const dollars = (cents: number) => `$${(cents / 100).toLocaleString("en-US", { maximumFractionDigits: cents % 100 ? 2 : 0 })}`;
export const ordinal = (n: number) => `${n}${["th", "st", "nd", "rd"][n % 100 > 10 && n % 100 < 14 ? 0 : Math.min(n % 10, 4) % 4]}`;
export const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
export const moment = (iso: string) => new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

// The time left until `iso`, split for a countdown; null once it has passed. Ticks every second.
export function useCountdown(iso: string | null): { d: number; h: number; m: number; s: number } | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!iso || now === null) return null;
  const left = Math.floor((new Date(iso).getTime() - now) / 1000);
  if (left <= 0) return null;
  return { d: Math.floor(left / 86400), h: Math.floor((left % 86400) / 3600), m: Math.floor((left % 3600) / 60), s: left % 60 };
}

// One public league read. `data` is undefined until it arrives; a failed or rate-limited read sets `failed`, never
// leaves the caller loading, and `retry` asks again. A null `path` waits (nothing to ask for yet).
export function usePublic<T>(path: string | null) {
  const [state, setState] = useState<{ data?: T; failed: boolean }>({ failed: false });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setState({ failed: false });
    api<T>(path, { auth: false }).then((data) => { if (live) setState({ data, failed: false }); })
      .catch(() => { if (live) setState({ failed: true }); });
    return () => { live = false; };
  }, [path, attempt]);
  return { ...state, retry: () => setAttempt((n) => n + 1) };
}

// The current competition with the top of its board; `competition: null` when none is open.
export const useCurrent = () => usePublic<Current>("/v1/league/current");

// The rules text a competition's entrants accept: its own version, which stays after a newer one is published.
export const rulesPath = (version?: string | null) => "/v1/league/rules" + (version ? `?version=${encodeURIComponent(version)}` : "");
