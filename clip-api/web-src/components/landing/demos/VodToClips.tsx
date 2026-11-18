"use client";
import { AiRating, LinkIcon } from "./Bits";
import { aiRated, Footage, useItem, useItems } from "./Footage";
import { Cam, Gameplay, SplitClip } from "./Frames";
import s from "./demos.module.css";

// One long stream in, ranked vertical clips out, each with its AI rating. The ratings are scaled across one
// video's clips, so the best lands in the 90s (app/scoring.py display_scores); the order is the AI's own.
// The placeholder numbers below only illustrate that; real clips show their own rating, or none.
const SAMPLE = [96, 93, 91, 88, 86, 83];

const clock = (sec: number) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`;
};

export function VodToClips({ play }: { play: boolean }) {
  const vod = useItem("hero-long-video", "vod");
  const real = useItems("hero-vertical-clips").filter((i) => /^clip-\d+$/.test(i.id))
    .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99)).slice(0, 6);
  // A clip's rank is its place in its own stream; clips from several streams can share one, so the chips show
  // only when the ranks shown are all different.
  const ranks = real.map((c) => c.rank), ranked = ranks.every((r) => typeof r === "number") && new Set(ranks).size === ranks.length;
  const clipCls = (i: number) => `${s.rise} relative aspect-[9/16] w-[108px] overflow-hidden rounded-[12px] ring-1 ring-white/10 narrow:w-[30vw] narrow:max-w-[104px] ${i > 2 ? "narrow:hidden" : ""}`;
  const delay = (i: number) => ({ ["--d" as string]: `${i * 0.22}s` });
  const rank = (n: number) => <span className="absolute left-1.5 top-1.5 z-10 rounded-[6px] bg-black/60 px-1.5 text-[11px] font-semibold text-white/85">#{n}</span>;

  return (
    <div className={`${s.demo} flex h-full flex-col items-center justify-center gap-5 narrow:gap-4`} data-play={play}>
      <div className="relative aspect-video w-[min(380px,100%)] overflow-hidden rounded-[14px] ring-1 ring-white/10">
        {vod ? <Footage section="hero-long-video" item={vod} play={play} /> : <>
          <Gameplay game="gta" label="Stream VOD" />
          <span className="absolute bottom-[6%] left-[4%] aspect-[4/3] w-[22%] overflow-hidden rounded-[6px] ring-1 ring-white/20"><Cam /></span>
        </>}
        <span className={`${s.scan} absolute inset-y-0 w-[12%] bg-gradient-to-r from-transparent via-lime/25 to-transparent`} aria-hidden="true" />
        <span className="absolute bottom-2 right-2 rounded-[6px] bg-black/70 px-1.5 py-0.5 text-[12px] font-semibold tabular-nums text-white">
          {vod?.duration_sec ? clock(vod.duration_sec) : "2:04:37"}</span>
      </div>

      <div className="flex w-[min(500px,100%)] items-center gap-2.5 rounded-full bg-black/45 py-1.5 pl-4 pr-1.5 ring-1 ring-white/10" aria-hidden="true">
        <LinkIcon className="h-4 w-4 shrink-0 text-white/60" />
        <span className="min-w-0 flex-1 truncate text-[14px] text-white/75">Paste a Twitch or Kick link, or drop the file</span>
        <span className="shrink-0 rounded-full bg-white px-4 py-2 text-[14px] font-semibold text-black">Get clips</span>
      </div>

      <ol className="flex list-none items-end gap-3 narrow:gap-2" aria-label="Clips found, best first">
        {real.length ? real.map((c, i) => (
          <li key={c.id} className={clipCls(i)} style={delay(i)}>
            <Footage section="hero-vertical-clips" item={c} play={play} />
            {ranked && rank(c.rank!)}
            {aiRated(c) && <AiRating value={Math.round(c.rating!)} className="absolute bottom-1.5 left-1.5 z-10" />}
          </li>
        )) : SAMPLE.map((r, i) => (
          <li key={i} className={clipCls(i)} style={delay(i)}>
            <SplitClip game="gta" />
            {rank(i + 1)}
            <AiRating value={r} className="absolute bottom-1.5 left-1.5" />
          </li>
        ))}
      </ol>
    </div>
  );
}
