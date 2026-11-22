"use client";
// The homepage's Creators League section: the current competition and the top of its real leaderboard, linking
// to /league/. With no competition or no approved entry it says so; it never shows a made-up creator or number.
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { dollars, PHASE_LABEL, useCurrent, views } from "@/lib/league";
import { CreatorAvatar, PrizeLine } from "./Bits";

export function HomeLeagueSection() {
  const { data } = useCurrent();
  const c = data?.competition, top = data?.top || [];
  return (
    <section aria-labelledby="league-home-title" className="px-gutter pb-[clamp(56px,7vw,112px)] pt-0">
      <Card className="mx-auto grid max-w-site grid-cols-[1.1fr_1fr] items-center gap-[clamp(28px,4vw,64px)] !p-[clamp(24px,4vw,56px)] mid:grid-cols-1">
        <div className="grid justify-items-start gap-4">
          <p className="m-0 text-eyebrow uppercase text-fg-2">Creators League{c ? ` · ${PHASE_LABEL[c.phase]}` : ""}</p>
          <h2 id="league-home-title" className="m-0 text-h2 text-fg">Create. Compete. Climb.</h2>
          <p className="m-0 max-w-[480px] text-lead text-fg-2">
            {c ? `${c.name}: post a clip made with ClutchClips and climb the board by public views. Free to enter.`
              : "A monthly competition for clips made with ClutchClips, ranked by public views. Free to enter."}</p>
          {c && <p className="m-0 text-[14px] text-fg-2">
            {c.cash_prizes && c.prize_pool_cents !== null ? <><span className="font-semibold text-fg">{dollars(c.prize_pool_cents)} prize pool</span> · <PrizeLine competition={c} /></> : <PrizeLine competition={c} />}</p>}
          <Button href="/league/" size="lg" className="mt-1">{c?.accepting_entries ? "Join the competition" : "See Creators League"}</Button>
        </div>
        <div className="grid gap-2" aria-label="Leaderboard preview">
          <p className="m-0 mb-1 text-[13px] uppercase tracking-[.08em] text-fg-2">Current leaderboard</p>
          {top.length === 0
            ? <p className="m-0 rounded-16 border border-dashed border-line-strong px-5 py-8 text-center text-[14.5px] leading-[1.5] text-fg-2">
              {data === undefined ? "Loading the leaderboard…" : c ? "No entries on the board yet. The first approved clip takes first place." : "The first competition has not opened yet."}</p>
            : <ol className="m-0 grid list-none gap-2 p-0">
              {top.map((r) => (
                <li key={r.rank} className="flex items-center gap-3 rounded-16 bg-control px-4 py-3">
                  <span className={`w-7 flex-none font-sans text-[18px] font-semibold tabular-nums ${r.rank === 1 ? "text-lime" : "text-fg-2"}`}>#{r.rank}</span>
                  <CreatorAvatar name={r.username} color={r.avatar} size={30} />
                  <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-fg">{r.username || "Creator"}{r.game && <span className="ml-2 font-normal text-fg-2">{r.game}</span>}</span>
                  <span className="flex-none text-[14px] tabular-nums text-fg">{views(r.views)}{r.views !== null && <span className="ml-1 text-fg-2">views</span>}</span>
                </li>))}
            </ol>}
          {top.length > 0 && <p className="m-0 mt-1 text-[12.5px] text-fg-3">Views are read by hand from public pages and are unverified.</p>}
        </div>
      </Card>
    </section>
  );
}
