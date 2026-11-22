"use client";
import { Score } from "@/components/ui/Score";
import { LinkIcon } from "./Bits";
import { aiRated, Credits, Footage, Item, useItem, useItems } from "./Footage";
import { Cam, Gameplay, SplitClip } from "./Frames";
import { useReducedMotion, useTicker } from "./motion";
import s from "./demos.module.css";
import { pastePrompt } from "@/lib/platforms";

// Decorative hero walkthrough: cursor → Get clips → export destinations → aspect ratios → scores.
// aria-hidden throughout — the real Get clips CTA lives in the hero StartInput and stays clickable.
// Destinations are download shapes (not live auto-post). Sample scores are labeled as such.

const ASPECTS = ["9:16", "16:9", "1:1", "4:5"] as const;
const ASPECT_CLASS: Record<(typeof ASPECTS)[number], string> = {
  "9:16": "aspect-[9/16]",
  "16:9": "aspect-video",
  "1:1": "aspect-square",
  "4:5": "aspect-[4/5]",
};
// Export targets the editor already frames for — not a claim that auto-post is live.
const DESTINATIONS = [
  { id: "tiktok", name: "TikTok", aspect: "9:16" as const },
  { id: "shorts", name: "YouTube Shorts", aspect: "9:16" as const },
  { id: "reels", name: "Reels", aspect: "9:16" as const },
  { id: "feed", name: "Feed", aspect: "1:1" as const },
];
const SAMPLE_SCORES = [94, 91, 88, 86, 83];

type Phase = "aim" | "click" | "destinations" | "aspects" | "scores";

const clock = (sec: number) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`;
};

function phaseOf(tick: number, reduced: boolean): { phase: Phase; aspect: (typeof ASPECTS)[number]; dest: number } {
  if (reduced) return { phase: "scores", aspect: "9:16", dest: 0 };
  const cycle = tick % 18;
  if (cycle < 3) return { phase: "aim", aspect: "9:16", dest: 0 };
  if (cycle < 5) return { phase: "click", aspect: "9:16", dest: 0 };
  if (cycle < 9) return { phase: "destinations", aspect: DESTINATIONS[cycle % DESTINATIONS.length].aspect, dest: cycle % DESTINATIONS.length };
  if (cycle < 13) return { phase: "aspects", aspect: ASPECTS[(cycle - 9) % ASPECTS.length], dest: 0 };
  return { phase: "scores", aspect: "9:16", dest: 0 };
}

export function VodToClips({ play }: { play: boolean }) {
  const reduced = useReducedMotion();
  const tick = useTicker(play && !reduced, 700);
  const { phase, aspect, dest } = phaseOf(tick, reduced);

  const vod = useItem("hero-long-video", "vod");
  const wideClip = useItem("hero-vertical-clips", "clip-wide"), found = useItem("clip-finding", "find-1");
  const wide: { section: "hero-vertical-clips" | "clip-finding"; item: Item } | null =
    wideClip ? { section: "hero-vertical-clips", item: wideClip } : found ? { section: "clip-finding", item: found } : null;
  const tall = useItems("hero-vertical-clips").filter((i) => /^clip-\d+$/.test(i.id)).slice(wideClip ? 1 : 0).slice(0, 5);

  const tile = "relative h-[160px] shrink-0 overflow-hidden rounded-[12px] ring-1 ring-white/10 narrow:h-[96px]";
  const delay = (i: number) => ({ ["--d" as string]: `${i * 0.18}s` });
  const showScores = phase === "scores" || reduced;
  const badge = (item: Item | null, i: number) => {
    if (!showScores) return null;
    if (item && aiRated(item)) return <Score value={Math.round(item.rating!)} kind="ai" size="sm" className="absolute bottom-1.5 left-1.5 z-10" />;
    return <Score value={SAMPLE_SCORES[i % SAMPLE_SCORES.length]} kind="sample" size="sm" className="absolute bottom-1.5 left-1.5 z-10" />;
  };

  return (
    <div className={`${s.demo} relative flex h-full flex-col items-center justify-center gap-5 narrow:gap-4`} data-play={play} aria-hidden="true">
      <div className="relative aspect-video w-[min(380px,100%)] overflow-hidden rounded-[14px] ring-1 ring-white/10">
        {vod ? <Footage section="hero-long-video" item={vod} play={play} /> : <>
          <Gameplay game="gta" label="Stream VOD" />
          <span className="absolute bottom-[6%] left-[4%] aspect-[4/3] w-[22%] overflow-hidden rounded-[6px] ring-1 ring-white/20"><Cam /></span>
        </>}
        <span className={`${s.scan} absolute inset-y-0 w-[12%] bg-gradient-to-r from-transparent via-lime/25 to-transparent`} />
        <span className="absolute bottom-2 right-2 rounded-[6px] bg-black/70 px-1.5 py-0.5 text-[12px] font-semibold tabular-nums text-white">
          {vod?.duration_sec ? clock(vod.duration_sec) : "2:04:37"}</span>
      </div>

      <div className="relative flex w-[min(500px,100%)] items-center gap-2.5 rounded-full bg-black/45 py-1.5 pl-4 pr-1.5 ring-1 ring-white/10">
        <LinkIcon className="h-4 w-4 shrink-0 text-white/60" />
        <span className="min-w-0 flex-1 truncate text-[14px] text-white/75">{pastePrompt()}</span>
        <span className={`shrink-0 rounded-full px-4 py-2 text-[14px] font-semibold transition-colors duration-300
          ${phase === "click" ? "bg-lime text-ink ring-2 ring-lime/40" : "bg-white text-black"}`}>Get clips</span>
        {!reduced && (phase === "aim" || phase === "click") && (
          <span className={`${s.cursor} pointer-events-none absolute z-20`} data-phase={phase}>
            <svg viewBox="0 0 24 24" className="h-7 w-7 drop-shadow-[0_2px_4px_rgba(0,0,0,.55)]" aria-hidden="true">
              <path fill="#fff" stroke="#111" strokeWidth="1.2" d="M5.5 3.5 18 12.2l-5.2 1.2 2.6 6.4-2.4 1-2.7-6.5L5.5 18.5z" />
            </svg>
          </span>
        )}
      </div>

      {(phase === "destinations" || phase === "aspects") && (
        <div className="flex w-[min(500px,100%)] flex-col items-center gap-2">
          {phase === "destinations" && (
            <ul className="flex flex-wrap items-center justify-center gap-2">
              {DESTINATIONS.map((d, i) => (
                <li key={d.id} className={`rounded-full px-3 py-1 text-[12px] font-medium ring-1 transition-colors
                  ${i === dest ? "bg-white text-black ring-white" : "bg-white/5 text-white/70 ring-white/15"}`}>{d.name}</li>
              ))}
            </ul>
          )}
          <p className="text-[11px] text-white/45">Download shapes · auto-post coming soon</p>
          <div className="flex items-end justify-center gap-2">
            {ASPECTS.map((a) => (
              <span key={a} className={`relative overflow-hidden rounded-[10px] bg-white/[.06] ring-1 transition-all duration-500
                ${a === aspect ? "h-[88px] ring-lime" : "h-[64px] opacity-45 ring-white/10"} ${ASPECT_CLASS[a]}`}>
                <Gameplay game="gta" label={false} hud={a === "9:16" || a === "4:5"} />
                {a === "9:16" && <span className="absolute inset-x-0 top-0 h-[32%] overflow-hidden border-b border-black/50"><Cam /></span>}
                <span className="absolute bottom-1 left-1 rounded-[4px] bg-black/65 px-1 text-[9px] font-semibold text-white/80">{a}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {(phase === "aim" || phase === "click" || phase === "scores" || reduced) && (
        <ol className="flex list-none items-end justify-center gap-3 narrow:gap-2">
          <li className={`${s.rise} ${tile} aspect-video`} style={delay(0)}>
            {wide ? <><Footage section={wide.section} item={wide.item} play={play} />{badge(wide.item, 0)}</>
              : <><Gameplay game="gta" label={false} />{badge(null, 0)}</>}
          </li>
          {(tall.length ? tall : [null, null, null, null, null]).map((c, i) => (
            <li key={c?.id ?? i} className={`${s.rise} ${tile} aspect-[9/16] ${i > 1 ? "narrow:hidden" : ""}`} style={delay(i + 1)}>
              {c ? <><Footage section="hero-vertical-clips" item={c} play={play} />{badge(c, i + 1)}</>
                : <><SplitClip game="gta" />{badge(null, i + 1)}</>}
            </li>
          ))}
        </ol>
      )}
      <Credits items={[vod, wide?.item, ...tall]} className="-mt-2" />
    </div>
  );
}
