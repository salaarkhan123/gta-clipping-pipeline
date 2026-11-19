"use client";
import { useRef } from "react";
import { AiRating } from "../demos/Bits";
import { aiRated, Credits, Footage, Item, useItem, useItems } from "../demos/Footage";
import { useInView } from "../demos/motion";
import { BeforeFrame } from "../demos/Reframe";
import s from "../demos/demos.module.css";
import { Section } from "../../site/Section";
import { EyebrowIcon } from "./EyebrowIcon";

const clock = (sec: number) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`;
};
type Sourced = Item & { aspect?: string; source?: { id?: string; start_sec?: number; end_sec?: number } };

// The long stream's timeline with the moments the engine picked from it, all real: the stream is the media
// pipeline's VOD, the marks are the clips it cut from that same stream (their source times), and the result is
// the best-rated of them. With no media yet the card stays empty.
function FinderVisual({ play }: { play: boolean }) {
  const vod = useItem("hero-long-video", "vod") as Sourced | null;
  const all = [...useItems("hero-vertical-clips"), ...useItems("editor"), ...useItems("clip-finding")] as Sourced[];
  const len = vod?.duration_sec ?? 0, from = vod?.source?.id;
  const picked = len && from ? all.filter((i) => i.source?.id === from && typeof i.source?.start_sec === "number" && i.source.start_sec < len) : [];
  const marks = [...new Map(picked.map((i) => [Math.round(i.source!.start_sec! / 30), i])).values()];   // one mark per moment
  // The result: the best-rated finished vertical clip from that stream.
  const best = (useItems("hero-vertical-clips") as Sourced[]).filter((i) => /^clip-\d+$/.test(i.id) && i.source?.id === from)
    .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))[0] ?? null;
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex min-h-0 flex-1 items-center gap-6 narrow:gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-5 narrow:gap-3">
          <div className="grid gap-2">
            <span className="text-[14px] font-semibold text-white/85">Describe the moments you want</span>
            <span className="h-[42px] rounded-[10px] bg-black/35 ring-1 ring-white/15" />
          </div>
          <div className="relative h-14 rounded-[10px] bg-black/35 ring-1 ring-white/10">
            {marks.map((m) => {
              const on = m === best || (best && m.source?.start_sec === best.source?.start_sec);
              return <span key={m.id} className={`absolute inset-y-2 w-[3px] rounded-full ${on ? `${s.glow} bg-lime` : "bg-white/50"}`}
                style={{ left: `${(m.source!.start_sec! / len) * 100}%` }} title={clock(m.source!.start_sec!)} />;
            })}
            {len > 0 && <>
              <span className="absolute -bottom-5 left-0 text-[11px] text-white/45">0:00</span>
              <span className="absolute -bottom-5 right-0 text-[11px] text-white/45">{clock(len)}</span>
              {best && <span className="absolute -top-5 -translate-x-1/2 whitespace-nowrap text-[11px] text-lime"
                style={{ left: `${(best.source!.start_sec! / len) * 100}%` }}>{clock(best.source!.start_sec!)}</span>}
            </>}
          </div>
        </div>
        <div className="relative aspect-[9/16] h-[240px] shrink-0 overflow-hidden rounded-[14px] bg-white/[.04] ring-1 ring-white/10 narrow:h-[180px]">
          {best && <><Footage section="hero-vertical-clips" item={best} play={play} />
            {aiRated(best) && <AiRating value={Math.round(best.rating!)} className="absolute bottom-2 left-2 z-10" />}</>}
        </div>
      </div>
      <Credits items={[vod, best]} />
    </div>
  );
}

// The real before and after: the 16:9 original with the engine's facecam box and the crop it took, and the
// vertical clip it made from them.
function ReframeVisual({ play }: { play: boolean }) {
  const original = useItem("reframe", "original"), split = useItem("reframe", "split2");
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex min-h-0 flex-1 items-center justify-center gap-5 narrow:gap-3">
        <div className="w-[58%]"><BeforeFrame item={original} layout="split2" play={play} /></div>
        <div className="flex flex-col gap-1.5" aria-hidden="true">{[0, 1, 2].map((i) => <span key={i} className={`${s.dot} h-1.5 w-1.5 rounded-full bg-white`} style={{ ["--d" as string]: `${i * 0.2}s` }} />)}</div>
        <div className="relative aspect-[9/16] h-[240px] overflow-hidden rounded-[12px] bg-white/[.04] ring-1 ring-white/10 narrow:h-[170px]">
          {split && <Footage section="reframe" item={split} play={play} />}
        </div>
      </div>
      <Credits items={[original, split]} />
    </div>
  );
}

const CARDS = [
  { title: "Moment finder", Visual: FinderVisual, tone: "#2a2620",
    text: "Listens for your reactions, watches chat speed up and reads what was said, then ranks every moment of the stream. Want something specific? Describe it in your own words, or search for what was said or shown, and get a clip of every match." },
  { title: "Facecam reframe", Visual: ReframeVisual, tone: "#22242c",
    text: "Finds your facecam on its own, keeps it out of the gameplay crop and stacks the two for vertical. Captions and the hook never sit on your face. Prefer it another way? Pick the layout, which panel the camera goes in and how big it is." },
];

// "AI that understands gameplay": the two models behind every clip.
export function ModelsSection() {
  const box = useRef<HTMLDivElement>(null), seen = useInView(box, "0px");
  return (
    <Section id="features" eyebrow="Built for gaming streams" icon={<EyebrowIcon name="spark" />} title={<>AI that knows what a<br className="narrow:hidden" /> good play looks like</>}
      sub="Made for streams with a facecam over gameplay, not for podcasts. It hears the hype, follows the game and frames your face.">
      <div ref={box} className={`${s.demo} grid grid-cols-2 gap-8 narrow:grid-cols-1`} data-play={seen}>
        {CARDS.map((c) => (
          <article key={c.title}>
            <div className="h-[340px] overflow-hidden rounded-card p-7 shadow-card narrow:h-auto narrow:min-h-[260px] narrow:p-5"
              style={{ background: `radial-gradient(120% 100% at 30% 0%, ${c.tone}, #0e0f12 85%)` }}><c.Visual play={seen} /></div>
            <h3 className="mt-6 text-h3 text-fg">{c.title}</h3>
            <p className="mt-2 text-body-lg text-fg-2">{c.text}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}
