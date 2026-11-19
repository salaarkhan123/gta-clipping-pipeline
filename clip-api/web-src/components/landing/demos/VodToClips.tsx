"use client";
import { AiRating, LinkIcon } from "./Bits";
import { aiRated, Footage, Item, useItem, useItems } from "./Footage";
import { Cam, Gameplay, SplitClip } from "./Frames";
import s from "./demos.module.css";

// One long stream in; the clips found in it out, in one row: the first as a wide 16:9 clip, the rest vertical.
// Each clip carries its AI rating bottom-left, but only when the AI judge rated it (rating_source "ai").

const clock = (sec: number) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`;
};

export function VodToClips({ play }: { play: boolean }) {
  const vod = useItem("hero-long-video", "vod");
  // The wide tile: the engine's 16:9 render of the first clip when the media pipeline has one, else a 16:9 moment
  // the clip finder picked.
  const wideClip = useItem("hero-vertical-clips", "clip-wide"), found = useItem("clip-finding", "find-1");
  const wide: { section: "hero-vertical-clips" | "clip-finding"; item: Item } | null =
    wideClip ? { section: "hero-vertical-clips", item: wideClip } : found ? { section: "clip-finding", item: found } : null;
  const tall = useItems("hero-vertical-clips").filter((i) => /^clip-\d+$/.test(i.id)).slice(wideClip ? 1 : 0).slice(0, 5);

  const tile = "relative h-[160px] shrink-0 overflow-hidden rounded-[12px] ring-1 ring-white/10 narrow:h-[96px]";
  const delay = (i: number) => ({ ["--d" as string]: `${i * 0.18}s` });
  const badge = (item: Item) => aiRated(item) && <AiRating value={Math.round(item.rating!)} className="absolute bottom-1.5 left-1.5 z-10" />;

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

      <ol className="flex list-none items-end justify-center gap-3 narrow:gap-2" aria-label="Clips found">
        <li className={`${s.rise} ${tile} aspect-video`} style={delay(0)}>
          {wide ? <><Footage section={wide.section} item={wide.item} play={play} />{badge(wide.item)}</> : <Gameplay game="gta" label={false} />}
        </li>
        {(tall.length ? tall : [null, null, null, null, null]).map((c, i) => (
          <li key={c?.id ?? i} className={`${s.rise} ${tile} aspect-[9/16] ${i > 1 ? "narrow:hidden" : ""}`} style={delay(i + 1)}>
            {c ? <><Footage section="hero-vertical-clips" item={c} play={play} />{badge(c)}</> : <SplitClip game="gta" />}
          </li>
        ))}
      </ol>
      {/* The full credit for every clip in the row: on small tiles the corner credit is cut short. */}
      {(wide || tall.length > 0) && <p className="-mt-2 text-center text-[11px] text-white/50">
        Footage: {[...new Set([wide?.item, ...tall].map((c) => c?.credit?.replace(/^Footage:\s*/, "")).filter(Boolean))].join(", ")}</p>}
    </div>
  );
}
