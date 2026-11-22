"use client";
// Creators League: the public page. The current competition, its leaderboard, the entered clips, how it works and
// the rules, all from the public API. Nothing here is invented: with no competition or no entries the page says so.
// A read that fails or is rate-limited shows one short line with a retry in its own section; nothing spins forever.
import { useEffect, useState } from "react";
import { Footer, Nav } from "@/components/Chrome";
import { ClipThumb, Countdown, CreatorAvatar, CreatorName, PrizeLine, WatchLink } from "@/components/league/Bits";
import { Leaderboard } from "@/components/league/Leaderboard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Board, Competition, day, dollars, PHASE_LABEL, Row, Rules, rulesPath, useCurrent, usePublic } from "@/lib/league";

const ENTER = "/dashboard/league/";
const SECTION = "px-gutter py-[clamp(48px,6vw,96px)]";
const WRAP = "mx-auto grid w-full max-w-site gap-[clamp(24px,3vw,40px)] [&>*]:min-w-0";
const STEPS: [string, string][] = [
  ["Create", "Make a clip from your own stream with ClutchClips."],
  ["Publish", "Post it publicly on TikTok, YouTube Shorts or Instagram Reels with the ClutchClips link in the description."],
  ["Submit", "Paste the link to your published video here. One clip per competition."],
  ["Compete", "Approved entries are ranked by their public view count."],
  ["Win", "The top three are reviewed by a person before any winner is confirmed."],
];

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid gap-1"><dt className="text-[13px] uppercase tracking-[.08em] text-fg-2">{label}</dt>
    <dd className="m-0 font-sans text-[22px] font-semibold leading-[1.2] tracking-[-0.02em] text-fg narrow:text-[19px]">{children}</dd></div>;
}

function LoadFailed({ what, retry }: { what: string; retry: () => void }) {
  return (
    <div role="status" className="flex flex-wrap items-center justify-center gap-3 rounded-card border border-dashed border-line-strong px-6 py-8 text-center text-[14.5px] text-fg-2">
      <span>Couldn&apos;t load {what}.</span>
      <Button size="sm" variant="secondary" onClick={retry}>Try again</Button>
    </div>
  );
}

function Hero({ competition, failed, retry }: { competition: Competition | null | undefined; failed: boolean; retry: () => void }) {
  return (
    <header className="grid justify-items-center px-gutter pb-[clamp(32px,4vw,56px)] pt-20 text-center narrow:pt-10">
      <p className="m-0 text-eyebrow uppercase text-fg-2">Monthly competition</p>
      <h1 className="m-0 mt-5 font-sans text-[clamp(40px,7.2vw,88px)] font-semibold uppercase leading-[1] tracking-[-0.045em] text-fg">Creators League</h1>
      <p className="m-0 mt-5 text-[clamp(18px,2.2vw,26px)] font-medium tracking-[-0.02em] text-lime">Create. Compete. Climb.</p>
      <p className="m-0 mt-4 max-w-[600px] text-lead text-fg-2">Post a clip you made with ClutchClips. The most-viewed clips of the month take the top of the board. Entry is free.</p>
      {competition === undefined && failed ? <div className="mt-10 w-full max-w-[880px]"><LoadFailed what="the current competition" retry={retry} /></div>
        : competition === undefined ? <div className="mt-10 h-[196px] w-full max-w-[880px] rounded-card bg-card" aria-hidden="true" />
        : competition === null ? (
          <Card className="mt-10 grid w-full max-w-[880px] justify-items-center gap-4 text-center">
            <h2 className="m-0 text-h3 text-fg">The first competition has not opened yet</h2>
            <p className="m-0 max-w-[520px] text-[15px] leading-[1.5] text-fg-2">Set up your creator profile now so you are ready to enter when it does.</p>
            <Button href={ENTER} size="lg">Set up your profile</Button>
          </Card>
        ) : (
          <Card className="mt-10 grid w-full max-w-[880px] gap-7 text-left">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-1">
                <p className="m-0 text-[13px] uppercase tracking-[.08em] text-fg-2">Current competition</p>
                <h2 className="m-0 text-h3 text-fg">{competition.name}</h2>
                <p className="m-0 text-[14px] text-fg-2">{day(competition.starts_at)} to {day(competition.ends_at)}</p>
              </div>
              <Badge tone={competition.phase === "live" ? "new" : "neutral"} className="!h-7 !px-3 !text-[13px]">{PHASE_LABEL[competition.phase]}</Badge>
            </div>
            <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-6">
              <Countdown competition={competition} />
              <dl className="m-0 flex flex-wrap gap-x-10 gap-y-4">
                <Stat label="Participants">{competition.participants.toLocaleString("en-US")}</Stat>
                {competition.cash_prizes && competition.prize_pool_cents !== null && <Stat label="Prize pool">{dollars(competition.prize_pool_cents)}</Stat>}
              </dl>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4 border-0 border-t border-solid border-line-soft pt-6">
              <p className="m-0 max-w-[520px] text-[14px] leading-[1.5] text-fg-2"><PrizeLine competition={competition} /></p>
              {competition.phase === "upcoming" || competition.accepting_entries
                ? <Button href={ENTER} size="lg">{competition.accepting_entries ? "Enter competition" : "Get ready to enter"}</Button>
                : <Button href="#leaderboard" size="lg" variant="secondary">See the leaderboard</Button>}
            </div>
          </Card>
        )}
    </header>
  );
}

function Featured({ clips, failed, retry }: { clips: Row[]; failed: boolean; retry: () => void }) {
  return (
    <section aria-labelledby="featured-title" className={SECTION}>
      <div className={WRAP}>
        <div className="grid gap-2"><h2 id="featured-title" className="m-0 text-h2 text-fg">Featured clips</h2>
          <p className="m-0 text-lead text-fg-2">Entries in this competition, made with ClutchClips.</p></div>
        {failed ? <LoadFailed what="the featured clips" retry={retry} />
          : clips.length === 0
          ? <EmptyState icon="film" title="No clips to feature yet">Approved entries appear here with the creator&apos;s own thumbnail.</EmptyState>
          : <ul className="m-0 grid list-none grid-cols-6 gap-4 p-0 mid:grid-cols-4 narrow:grid-cols-2 narrow:gap-3">
            {clips.map((c) => (
              <li key={c.rank} className="grid gap-2.5">
                <ClipThumb row={c} className="aspect-[9/16] w-full !rounded-16" />
                <span className="flex min-w-0 items-center gap-2 text-[14px]"><CreatorAvatar name={c.username} color={c.avatar} size={24} /><CreatorName row={c} className="min-w-0 truncate font-medium" /></span>
                <WatchLink row={c} className="text-[13px]" />
              </li>))}
          </ul>}
      </div>
    </section>
  );
}

function RulesBlock({ rules, failed, retry }: { rules: Rules | undefined; failed: boolean; retry: () => void }) {
  return (
    <section id="rules" aria-labelledby="rules-title" className={SECTION}>
      <div className="mx-auto grid max-w-prose gap-6">
        <div className="grid gap-2"><h2 id="rules-title" className="m-0 text-h2 text-fg">Competition rules</h2>
          {rules && <p className="m-0 text-[14px] text-fg-2">Version {rules.version}. {rules.legally_reviewed ? "" : "These rules are a draft. Sections marked To be confirmed are completed when the official rules are published."}</p>}</div>
        {failed ? <LoadFailed what="the rules" retry={retry} /> : !rules ? <p className="m-0 text-fg-2">Loading the rules…</p> : (
          <>
            <Card className="grid gap-3 !p-6">
              <h3 className="m-0 text-title text-fg">Required in your video&apos;s description</h3>
              <p className="m-0 whitespace-pre-line rounded-12 bg-control px-4 py-3 font-mono text-[14px] leading-[1.6] text-fg">{rules.attribution.text}</p>
              <p className="m-0 text-[13px] text-fg-2">Entries are checked by hand. An entry without this link can be rejected.</p>
            </Card>
            <div className="grid gap-2">
              {rules.sections.map((s) => (
                <details key={s.id} className="group rounded-16 bg-card px-6 py-4 shadow-card">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-title text-fg [&::-webkit-details-marker]:hidden">
                    <span className="flex flex-wrap items-center gap-2.5">{s.title}{s.needs_legal_review && <Badge tone="soon">To be confirmed</Badge>}</span>
                    <span aria-hidden="true" className="text-fg-3 transition-transform duration-base group-open:rotate-45 motion-reduce:transition-none">+</span>
                  </summary>
                  <ul className="m-0 mt-3 grid list-none gap-2.5 p-0 text-[15px] leading-[1.55] text-fg-2">
                    {s.body.map((line, i) => <li key={i} className={line.startsWith("[PLACEHOLDER") ? "rounded-12 border border-dashed border-line-strong px-3 py-2 text-[13.5px] text-fg-3" : ""}>{line}</li>)}
                  </ul>
                </details>))}
            </div>
          </>)}
      </div>
    </section>
  );
}

export default function LeaguePage() {
  const current = useCurrent();
  const competition = current.data?.competition, slug = competition?.slug;
  const board = usePublic<Board>(slug ? `/v1/league/${slug}/leaderboard` : null);
  const featured = usePublic<{ clips: Row[] }>(slug ? `/v1/league/${slug}/featured` : null);
  // The rules of this competition's own version; the entry form links here with ?rules=<the version it accepts>.
  const [asked, setAsked] = useState<string | null | undefined>(undefined);
  useEffect(() => { setAsked(new URLSearchParams(window.location.search).get("rules")); }, []);
  const settled = asked !== undefined && (current.data !== undefined || current.failed);
  const rules = usePublic<Rules>(settled ? rulesPath(asked || competition?.rules_version) : null);
  return (
    <>
      <Nav />
      <main>
        <Hero competition={competition} failed={current.failed} retry={current.retry} />

        <section id="leaderboard" aria-labelledby="board-title" className={SECTION}>
          <div className={WRAP}>
            <div className="grid gap-2"><h2 id="board-title" className="m-0 text-h2 text-fg">Leaderboard</h2>
              <p className="m-0 text-lead text-fg-2">{competition ? `${competition.name}: approved entries by public views.` : "Approved entries by public views."}</p></div>
            {current.failed ? <LoadFailed what="the leaderboard" retry={current.retry} />
              : board.failed ? <LoadFailed what="the leaderboard" retry={board.retry} />
              : competition === undefined || (competition && !board.data) ? <div className="h-[220px] rounded-card bg-card" aria-hidden="true" />
              : <Leaderboard rows={board.data?.entries || []} updatedAt={board.data?.updated_at || null}
                empty={competition?.accepting_entries ? "Be the first on the board: enter your clip and it appears here once it is approved." : "Entries appear here once they are approved."} />}
          </div>
        </section>

        <Featured clips={featured.data?.clips || []} failed={current.failed || featured.failed} retry={current.failed ? current.retry : featured.retry} />

        <section aria-labelledby="how-title" className={SECTION}>
          <div className={WRAP}>
            <h2 id="how-title" className="m-0 text-h2 text-fg">How it works</h2>
            <ol className="m-0 grid list-none grid-cols-5 gap-4 p-0 mid:grid-cols-2 narrow:grid-cols-1">
              {STEPS.map(([title, text], i) => (
                <li key={title} className="grid content-start gap-3 rounded-card bg-card p-6 shadow-card">
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-control font-sans text-[15px] font-semibold tabular-nums text-lime">{i + 1}</span>
                  <h3 className="m-0 text-title text-fg">{title}</h3>
                  <p className="m-0 text-[14.5px] leading-[1.5] text-fg-2">{text}</p>
                </li>))}
            </ol>
          </div>
        </section>

        <RulesBlock rules={rules.data} failed={rules.failed} retry={rules.retry} />
      </main>
      <Footer />
    </>
  );
}
