"use client";
// Creators League for a signed-in creator: the creator profile, the entry form and the entry's review status.
// The API decides everything (app/league.py): this page shows the rules before the creator submits and the
// API's answer after. Field names are the API's (tests/test_league_screens.py checks them).
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useDash } from "@/components/dash/Shell";
import { CreatorAvatar } from "@/components/league/Bits";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";
import { AVATAR_COLOR, day, ENTRY_STATUS, Me, MyEntry, ordinal, PHASE_LABEL, Platform, PLATFORM_HINT, PLATFORM_LABEL, safeVideoUrl, views } from "@/lib/league";

const INPUT = "h-11 w-full rounded-12 border border-solid border-transparent bg-control px-4 font-sans text-[14px] text-text placeholder:text-fg-3 focus:border-line-strong focus:outline-none";
const LABEL = "grid gap-2 text-[14px] font-medium text-text";
const CHECK = "flex items-start gap-3 text-[14px] font-normal leading-[1.45] text-text [&>input]:mt-[3px] [&>input]:h-4 [&>input]:w-4 [&>input]:flex-none";
const STEP = "m-0 text-[12px] font-semibold uppercase tracking-[.08em] text-fg-2";
const PLATFORMS = Object.keys(PLATFORM_LABEL) as Platform[];
const TONE: Record<MyEntry["status"], string> = { pending: "bg-control text-text", approved: "bg-lime/[.14] text-lime", rejected: "bg-danger/[.14] text-danger", disqualified: "bg-danger/[.14] text-danger" };

function EntryStatus({ entry }: { entry: MyEntry }) {
  const s = ENTRY_STATUS[entry.status], url = safeVideoUrl(entry.video_url);
  return (
    <Card className="grid gap-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 text-title text-fg">Your entry</h2>
        <span className={`inline-flex h-6 items-center rounded-[6px] px-2.5 text-[12.5px] font-medium ${TONE[entry.status]}`}>{s.label}</span>
        {entry.final_place !== null && <Badge tone="new">{ordinal(entry.final_place)} place, confirmed</Badge>}
      </div>
      <p className="m-0 text-[14.5px] leading-[1.5] text-fg-2">{s.text}{entry.status === "approved" && entry.rank !== null ? ` You are #${entry.rank}${entry.views !== null ? ` with ${views(entry.views)} views (unverified)` : "; no view count has been recorded yet"}.` : ""}</p>
      {entry.status_reason && (entry.status === "rejected" || entry.status === "disqualified") &&
        <p className="m-0 rounded-12 bg-control px-4 py-3 text-[14px] leading-[1.5] text-text"><span className="text-fg-2">Reason: </span>{entry.status_reason}</p>}
      <p className="m-0 flex flex-wrap gap-x-5 gap-y-1 text-[13.5px] text-fg-2">
        <span>{PLATFORM_LABEL[entry.platform]}</span><span>Submitted {day(entry.submitted_at)}</span>
        {url && <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="text-fg underline-offset-4 hover:underline">Open your video</a>}
        <Link href="/league/#leaderboard" className="text-fg underline-offset-4 hover:underline">See the leaderboard</Link>
      </p>
    </Card>
  );
}

function ProfileForm({ me, onSaved }: { me: Me; onSaved: () => void }) {
  const p = me.profile;
  const [username, setUsername] = useState(p?.username || ""), [avatar, setAvatar] = useState(p?.avatar || "lime");
  const [games, setGames] = useState((p?.games || []).join(", ")), [isPublic, setIsPublic] = useState(p?.is_public ?? false);
  const [busy, setBusy] = useState(false), [problem, setProblem] = useState(""), [saved, setSaved] = useState(false);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setProblem(""); setSaved(false);
    try {
      await api("/v1/league/me/profile", { method: "PUT", body: { username: username.trim(), avatar, is_public: isPublic,
        games: games.split(",").map((g) => g.trim()).filter(Boolean) } });
      setSaved(true); onSaved();
    } catch (err: any) { setProblem(err.message); } finally { setBusy(false); }
  };
  return (
    <Card>
      <form className="grid gap-5" onSubmit={save} aria-labelledby="profile-title">
        <div className="grid gap-1"><h2 id="profile-title" className="m-0 text-title text-fg">Creator profile</h2>
          <p className="m-0 text-[14px] leading-[1.5] text-fg-2">Your username, avatar and game are shown on the public leaderboard when you have an approved entry. Your email is never shown.</p></div>
        <div className="grid grid-cols-2 gap-5 narrow:grid-cols-1">
          <label className={LABEL}>Username
            <input name="username" className={INPUT} value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} maxLength={20}
              pattern="[A-Za-z0-9_]{3,20}" autoComplete="off" spellCheck={false} placeholder="clutch_kid" />
            <span className="text-[12.5px] font-normal text-fg-2">3 to 20 letters, numbers or underscores.</span></label>
          <label className={LABEL}>Games you play
            <input name="games" className={INPUT} value={games} onChange={(e) => setGames(e.target.value)} maxLength={160} placeholder="GTA 5, Valorant" />
            <span className="text-[12.5px] font-normal text-fg-2">Up to five, separated by commas.</span></label>
        </div>
        <fieldset className="m-0 grid gap-2 border-0 p-0">
          <legend className="mb-2 p-0 text-[14px] font-medium text-text">Avatar</legend>
          <div className="flex flex-wrap gap-3">
            {me.avatars.map((a) => (
              <label key={a} className={`cursor-pointer rounded-full p-[3px] ${avatar === a ? "shadow-[0_0_0_2px_var(--fg)]" : ""} has-[:focus-visible]:shadow-[0_0_0_2px_theme(colors.lime)]`}>
                <input type="radio" name="avatar" value={a} checked={avatar === a} onChange={() => setAvatar(a)} className="sr-only" />
                <CreatorAvatar name={username || "?"} color={a} size={40} /><span className="sr-only">{a}{AVATAR_COLOR[a] ? "" : " (default)"}</span>
              </label>))}
          </div>
        </fieldset>
        <label className={CHECK}><input type="checkbox" name="is_public" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          <span>Give me a public profile page that lists my approved entries, rankings and awards.</span></label>
        {problem && <p role="alert" className="error m-0">{problem}</p>}
        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" variant={p ? "secondary" : "primary"} disabled={busy}>{busy ? "Saving…" : p ? "Save profile" : "Create profile"}</Button>
          {saved && <span role="status" className="text-[14px] text-lime">Saved.</span>}
          {p?.is_public && <Link href={`/league/creator/?u=${encodeURIComponent(p.username)}`} className="text-[14px] text-fg-2 underline-offset-4 hover:text-fg hover:underline">View my public profile</Link>}
        </div>
      </form>
    </Card>
  );
}

// Copies with the Clipboard API, or through a selected textarea where a browser refuses it; says so if both fail.
async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const area = document.createElement("textarea");
  area.value = text; area.setAttribute("readonly", ""); area.style.position = "fixed"; area.style.opacity = "0";
  document.body.appendChild(area); area.select();
  try { return document.execCommand("copy"); } catch { return false; } finally { area.remove(); }
}

function CopyAttribution({ text }: { text: string }) {
  const [state, setState] = useState<"" | "copied" | "failed">("");
  return (
    <div className="grid gap-3 rounded-16 bg-control p-4">
      <p className="m-0 select-all whitespace-pre-line font-mono text-[14px] leading-[1.6] text-text">{text}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="secondary" onClick={async () => { setState((await copyText(text)) ? "copied" : "failed"); setTimeout(() => setState(""), 4000); }}>Copy attribution</Button>
        <span role="status" className={`text-[13px] ${state === "failed" ? "text-warn" : "text-lime"}`}>
          {state === "copied" ? "Copied. Paste it into your video's description." : state === "failed" ? "Could not copy. Select the text above and copy it." : ""}</span>
      </div>
    </div>
  );
}

function EntryForm({ me, onDone }: { me: Me; onDone: () => void }) {
  const c = me.competition!;
  const [clip, setClip] = useState(""), [platform, setPlatform] = useState<Platform>("tiktok"), [url, setUrl] = useState(""), [game, setGame] = useState(me.profile?.games[0] || "");
  const [attributed, setAttributed] = useState(false), [rules, setRules] = useState(false);
  const [busy, setBusy] = useState(false), [problem, setProblem] = useState("");
  const ready = clip && url.trim() && attributed && rules && !busy;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setProblem("");
    try {
      await api(`/v1/league/${c.slug}/entries`, { body: { clip_id: clip, platform, url: url.trim(), game: game.trim() || null,
        attribution_confirmed: attributed, rules_version: c.rules_version } });
      onDone();
    } catch (err: any) { setProblem(err.message); } finally { setBusy(false); }
  };
  return (
    <Card>
      <form className="grid gap-7" onSubmit={submit} aria-labelledby="enter-title">
        <div className="grid gap-1"><h2 id="enter-title" className="m-0 text-title text-fg">Enter {c.name}</h2>
          <p className="m-0 text-[14px] leading-[1.5] text-fg-2">Free to enter. One clip per creator. Entries close {day(c.ends_at)}.</p></div>

        <fieldset className="m-0 grid gap-3 border-0 p-0">
          <legend className={`${STEP} mb-3 p-0`}>1. Choose the clip you published</legend>
          {me.clips.length === 0
            ? <EmptyState icon="scissors" title="You have no clips yet" action={<Button href="/dashboard/" variant="secondary">Make a clip</Button>}>Your entry must be a clip made with ClutchClips. Make one first, then come back.</EmptyState>
            : <div className="grid max-h-[420px] grid-cols-6 gap-3 overflow-y-auto p-[3px] mid:grid-cols-4 narrow:grid-cols-3">
              {me.clips.map((k) => (
                <label key={k.id} className={`grid cursor-pointer gap-1.5 rounded-12 p-1.5 ${clip === k.id ? "bg-control shadow-[0_0_0_2px_var(--fg)]" : "hover:bg-control"} has-[:focus-visible]:shadow-[0_0_0_2px_theme(colors.lime)]`}>
                  <input type="radio" name="clip_id" value={k.id} checked={clip === k.id} onChange={() => setClip(k.id)} className="sr-only" />
                  <span className="relative block aspect-[9/16] overflow-hidden rounded-8 bg-control">
                    {k.thumb_url ? <img src={k.thumb_url} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" /> : <span className="absolute inset-0 grid place-items-center text-[11px] text-fg-3">No preview</span>}</span>
                  <span className="truncate text-[12.5px] text-text">{k.title || "Untitled clip"}</span>
                  <span className="text-[11.5px] text-fg-2">{Math.round(k.duration_sec)}s · {day(k.created_at)}</span>
                </label>))}
            </div>}
        </fieldset>

        <fieldset className="m-0 grid gap-3 border-0 p-0">
          <legend className={`${STEP} mb-3 p-0`}>2. Where did you publish it?</legend>
          <div className="flex flex-wrap gap-2">
            {PLATFORMS.map((id) => (
              <label key={id} className={`cursor-pointer rounded-12 px-4 py-2.5 text-[14px] font-medium ${platform === id ? "bg-btn text-btn-ink" : "bg-control text-text hover:bg-control-hover"} has-[:focus-visible]:shadow-[0_0_0_2px_theme(colors.lime)]`}>
                <input type="radio" name="platform" value={id} checked={platform === id} onChange={() => setPlatform(id)} className="sr-only" />{PLATFORM_LABEL[id]}</label>))}
          </div>
        </fieldset>

        <div className="grid gap-5">
          <p className={STEP}>3. Paste the public video link</p>
          <div className="grid grid-cols-[2fr_1fr] gap-5 narrow:grid-cols-1">
            <label className={LABEL}>Video link
              <input name="url" type="url" inputMode="url" className={INPUT} value={url} onChange={(e) => setUrl(e.target.value)} required maxLength={300} autoComplete="off" spellCheck={false} placeholder={PLATFORM_HINT[platform]} />
              <span className="text-[12.5px] font-normal text-fg-2">The full link to the video, not a short share link. The video must be public.</span></label>
            <label className={LABEL}>Game
              <input name="game" className={INPUT} value={game} onChange={(e) => setGame(e.target.value)} maxLength={30} placeholder="GTA 5" />
              <span className="text-[12.5px] font-normal text-fg-2">Shown on the leaderboard.</span></label>
          </div>
        </div>

        <div className="grid gap-4">
          <p className={STEP}>4. Add the ClutchClips link to your video&apos;s description</p>
          <CopyAttribution text={me.attribution.text} />
          <label className={CHECK}><input type="checkbox" name="attribution_confirmed" checked={attributed} onChange={(e) => setAttributed(e.target.checked)} required />
            <span>I confirm this text is in my video&apos;s description. Entries are checked by hand and can be rejected without it.</span></label>
        </div>

        <div className="grid gap-4">
          <p className={STEP}>5. Accept the rules</p>
          <label className={CHECK}><input type="checkbox" name="rules_version" value={c.rules_version} checked={rules} onChange={(e) => setRules(e.target.checked)} required />
            <span>I have read and accept the <Link href={`/league/?rules=${encodeURIComponent(c.rules_version)}#rules`} target="_blank" className="text-fg underline underline-offset-4">competition rules</Link> (version {c.rules_version}), and I agree that my username, avatar, game, this clip&apos;s thumbnail, the video link and its public view count are shown on the public leaderboard.</span></label>
        </div>

        {problem && <p role="alert" className="error m-0">{problem}</p>}
        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" size="lg" disabled={!ready}>{busy ? "Submitting…" : "Submit entry"}</Button>
          <span className="text-[13px] text-fg-2">A person reviews every entry before it appears on the leaderboard.</span>
        </div>
      </form>
    </Card>
  );
}

export default function LeagueEntryPage() {
  const [me, setMe] = useState<Me | null>(null), [problem, setProblem] = useState("");
  const load = useCallback(() => { api("/v1/league/me").then(setMe).catch((e) => setProblem(e.message)); }, []);
  useEffect(load, [load]);
  const c = me?.competition, admin = useDash().me.is_admin;
  return (
    <div className="stack mx-auto w-full max-w-dash">
      <PageHeader title="Creators League" hint="Create. Compete. Climb.">{admin && <Button href="/dashboard/admin/league/" variant="ghost" size="sm">Admin</Button>}<Button href="/league/" variant="secondary" size="sm">Leaderboard and rules</Button></PageHeader>
      {problem && <p role="alert" className="error m-0">{problem}</p>}
      {!me ? (!problem && <p className="muted">Loading…</p>) : <>
        {c && (
          <Card className="flex flex-wrap items-center justify-between gap-4 !py-5">
            <div className="grid gap-1"><span className="text-[12px] uppercase tracking-[.08em] text-fg-2">Current competition</span>
              <span className="text-[17px] font-semibold text-fg">{c.name}</span>
              <span className="text-[13.5px] text-fg-2">{day(c.starts_at)} to {day(c.ends_at)} · {c.participants.toLocaleString("en-US")} participant{c.participants === 1 ? "" : "s"}</span></div>
            <Badge tone={c.phase === "live" ? "new" : "neutral"} className="!h-7 !px-3 !text-[13px]">{PHASE_LABEL[c.phase]}</Badge>
          </Card>)}
        {me.entry && <EntryStatus entry={me.entry} />}
        {!me.email_verified && <p className="notice !m-0 !max-w-none">Confirm your email address before you enter. Check your inbox for the link we sent when you signed up.</p>}
        {!c ? <EmptyState icon="calendar" title="No competition is open yet">Create your profile now. When a competition opens, you can enter from this page.</EmptyState>
          : me.entry ? null
          : !c.accepting_entries ? <EmptyState icon="calendar" title={c.phase === "upcoming" ? `Entries open ${day(c.starts_at)}` : "Entries are closed"}>{c.phase === "upcoming" ? "Come back then to submit your clip." : "This competition no longer takes entries. Watch for the next one."}</EmptyState>
          : !me.profile ? <p className="notice !m-0 !max-w-none">Create your creator profile below, then the entry form appears here.</p>
          : me.email_verified ? <EntryForm me={me} onDone={load} /> : null}
        <ProfileForm key={me.profile?.username || "new"} me={me} onSaved={load} />
      </>}
    </div>
  );
}
