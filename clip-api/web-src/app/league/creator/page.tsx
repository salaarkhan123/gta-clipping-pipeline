"use client";
// A creator's public profile: /league/creator/?u=<username>. Shows only what GET /v1/league/creators/{username}
// returns, which is only what the creator made public. A private or unknown profile is the same "not found".
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Footer, Nav } from "@/components/Chrome";
import { ClipThumb, CreatorAvatar, WatchLink } from "@/components/league/Bits";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { api } from "@/lib/api";
import { ordinal, PHASE_LABEL, Phase, Platform, views } from "@/lib/league";

type Entry = { competition: { slug: string; name: string; phase: Phase }; platform: Platform; video_url: string; game: string | null;
  thumb_url: string | null; rank: number; views: number | null; observed_at: string | null; final_place: number | null };
type Creator = { username: string; avatar: string; games: string[]; entries: Entry[]; awards: { competition: { name: string }; place: number }[] };

// useSearchParams needs a Suspense boundary in a static export.
export default function CreatorPage() { return <Suspense><Profile /></Suspense>; }

function Profile() {
  const username = (useSearchParams().get("u") || "").trim();
  const [creator, setCreator] = useState<Creator | null | undefined>(undefined);
  useEffect(() => {
    if (!/^[A-Za-z0-9_]{3,20}$/.test(username)) { setCreator(null); return; }
    api(`/v1/league/creators/${encodeURIComponent(username)}`, { auth: false }).then(setCreator).catch(() => setCreator(null));
  }, [username]);
  return (
    <>
      <Nav />
      <main className="px-gutter pb-[clamp(56px,7vw,112px)] pt-14 narrow:pt-8">
        <div className="mx-auto grid max-w-[880px] gap-10">
          <Link href="/league/" className="text-[14px] text-fg-2 underline-offset-4 hover:text-fg hover:underline">← Creators League</Link>
          {creator === undefined ? <div className="h-[160px] rounded-card bg-card" aria-hidden="true" />
            : creator === null ? <EmptyState icon="search" title="No public profile here" action={<Button href="/league/" variant="secondary">Back to Creators League</Button>}>
              This creator does not exist or keeps their profile private.</EmptyState>
            : <>
              <header className="flex flex-wrap items-center gap-5">
                <CreatorAvatar name={creator.username} color={creator.avatar} size={72} />
                <div className="grid gap-2">
                  <h1 className="m-0 text-h2 text-fg">{creator.username}</h1>
                  {creator.games.length > 0 && <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label="Games">
                    {creator.games.map((g) => <li key={g}><Badge className="!h-6 !px-2.5 !text-[12.5px]">{g}</Badge></li>)}</ul>}
                </div>
              </header>
              {creator.awards.length > 0 && (
                <section aria-labelledby="awards-title" className="grid gap-3 !p-0">
                  <h2 id="awards-title" className="m-0 text-h3 text-fg">Awards</h2>
                  <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
                    {creator.awards.map((a, i) => <li key={i} className="rounded-16 bg-card px-5 py-3 shadow-card"><span className="font-semibold text-lime">{ordinal(a.place)} place</span><span className="ml-2 text-fg-2">{a.competition.name}</span></li>)}
                  </ul>
                </section>)}
              <section aria-labelledby="entries-title" className="grid gap-3 !p-0">
                <h2 id="entries-title" className="m-0 text-h3 text-fg">Competition entries</h2>
                {creator.entries.length === 0 ? <EmptyState icon="film" title="No approved entries yet">Entries appear here once they are approved.</EmptyState>
                  : <ul className="m-0 grid list-none gap-3 p-0">
                    {creator.entries.map((e) => (
                      <li key={e.competition.slug} className="grid grid-cols-[64px_1fr_auto] items-center gap-4 rounded-card bg-card p-4 shadow-card narrow:grid-cols-[56px_1fr]">
                        <ClipThumb row={{ thumb_url: e.thumb_url, username: creator.username, platform: e.platform }} className="aspect-[9/16] w-full" />
                        <div className="grid min-w-0 gap-1">
                          <span className="truncate text-[16px] font-semibold text-fg">{e.competition.name}</span>
                          <span className="text-[13px] text-fg-2">{PHASE_LABEL[e.competition.phase]}{e.game ? ` · ${e.game}` : ""}</span>
                          <WatchLink row={e} className="text-[13px]" />
                        </div>
                        <div className="grid justify-items-end gap-1 narrow:col-span-2 narrow:justify-items-start">
                          <span className="font-sans text-[22px] font-semibold leading-none tabular-nums text-fg">#{e.rank}</span>
                          <span className="text-[13px] tabular-nums text-fg-2">{views(e.views)}{e.views !== null ? " views (unverified)" : ""}</span>
                          {e.final_place !== null && <Badge tone="new">{ordinal(e.final_place)} place, confirmed</Badge>}
                        </div>
                      </li>))}
                  </ul>}
              </section>
            </>}
        </div>
      </main>
      <Footer />
    </>
  );
}
