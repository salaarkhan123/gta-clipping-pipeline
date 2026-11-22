// Small pieces the Creators League screens share. Every creator-supplied value (username, game) is rendered as
// text by React; nothing here sets HTML.
import Link from "next/link";
import { PlatformBadge } from "@/components/ui/PlatformGlyph";
import { AVATAR_COLOR, Competition, dollars, ordinal, PLATFORM_LABEL, Row, safeVideoUrl, useCountdown } from "@/lib/league";

export function CreatorAvatar({ name, color, size = 36 }: { name: string | null; color: string; size?: number }) {
  return (
    <span aria-hidden="true" style={{ width: size, height: size, fontSize: size * 0.42, background: AVATAR_COLOR[color] || AVATAR_COLOR.slate }}
      className="grid flex-none place-items-center rounded-full font-sans font-semibold leading-none text-ink">
      {(name?.[0] || "?").toUpperCase()}</span>
  );
}

// A creator's name: a link to their profile page when they made it public.
export function CreatorName({ row, className = "" }: { row: Pick<Row, "username" | "has_profile">; className?: string }) {
  const name = row.username || "Creator";
  return row.has_profile && row.username
    ? <Link href={`/league/creator/?u=${encodeURIComponent(row.username)}`} className={`text-fg underline-offset-4 hover:underline ${className}`}>{name}</Link>
    : <span className={`text-fg ${className}`}>{name}</span>;
}

// The creator's own ClutchClips thumbnail, or a quiet tile when the clip has none. Never an embed of the platform.
export function ClipThumb({ row, className = "" }: { row: Pick<Row, "thumb_url" | "username" | "platform">; className?: string }) {
  return (
    <span className={`relative block overflow-hidden rounded-12 bg-control ${className}`}>
      {row.thumb_url
        ? <img src={row.thumb_url} alt={`Clip by ${row.username || "a creator"}`} loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover" />
        : <span className="absolute inset-0 grid place-items-center text-[11px] text-fg-3">No preview</span>}
      <PlatformBadge id={row.platform} className="absolute bottom-1.5 right-1.5 h-6 w-6" />
    </span>
  );
}

export function WatchLink({ row, className = "" }: { row: Pick<Row, "video_url" | "platform">; className?: string }) {
  const url = safeVideoUrl(row.video_url);
  if (!url) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer nofollow" className={`text-fg-2 underline-offset-4 hover:text-fg hover:underline ${className}`}>
    Watch on {PLATFORM_LABEL[row.platform]}<span className="sr-only"> (opens in a new tab)</span></a>;
}

const UNIT = "grid min-w-[64px] justify-items-center gap-1 rounded-12 bg-control px-3 py-2.5 narrow:min-w-[56px]";
// Days, hours, minutes and seconds until the entries close (or open). Plain numbers: nothing moves but the digits.
export function Countdown({ competition }: { competition: Competition }) {
  const to = competition.phase === "upcoming" ? competition.starts_at : competition.phase === "live" ? competition.ends_at : null;
  const left = useCountdown(to);
  if (!to) return <p className="m-0 text-[15px] text-fg-2">{competition.phase === "final" ? "This competition is over. The results are final." : "Entries are closed. Winners are being reviewed."}</p>;
  const parts: [string, number | null][] = [["days", left?.d ?? null], ["hours", left?.h ?? null], ["min", left?.m ?? null], ["sec", left?.s ?? null]];
  return (
    <div className="grid gap-2">
      <p className="m-0 text-[13px] uppercase tracking-[.08em] text-fg-2">{competition.phase === "upcoming" ? "Entries open in" : "Entries close in"}</p>
      <div className="flex gap-2" role="timer" aria-label={left ? `${left.d} days ${left.h} hours ${left.m} minutes` : undefined}>
        {parts.map(([label, n]) => (
          <span key={label} className={UNIT}>
            <span className="font-sans text-[26px] font-semibold leading-none tabular-nums text-fg narrow:text-[22px]">{n === null ? "--" : String(n).padStart(2, "0")}</span>
            <span className="text-[11px] uppercase tracking-[.08em] text-fg-3">{label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// The prize pool, only when the API says cash prizes are on; otherwise its note that prizes come with the official rules.
export function PrizeLine({ competition }: { competition: Competition }) {
  return <span>{competition.cash_prizes && competition.prizes ? competition.prizes.map((p) => `${ordinal(p.place)} ${dollars(p.amount_cents)}`).join(" · ") : competition.prize_note}</span>;
}
