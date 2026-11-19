"use client";
import { useRef } from "react";
import { Cam, Gameplay, SplitClip } from "../demos/Frames";
import { Credits, Footage, useItems } from "../demos/Footage";
import { useInView } from "../demos/motion";
import s from "../demos/demos.module.css";
import { Section } from "../../site/Section";
import { EyebrowIcon } from "./EyebrowIcon";

// Where the strong moments sit along a 2-hour stream (fractions of its length) and how strong each is.
const PEAKS = [[0.08, 0.5], [0.21, 0.8], [0.34, 0.45], [0.47, 1], [0.63, 0.65], [0.78, 0.9], [0.9, 0.55]];

// A moment the finder found, from the media pipeline (clip-finding). Ranked on signals, so it shows its rank, never an
// AI rating. Until the section has footage, the drawn clip stands in.
function FoundClip() {
  const item = useItems("clip-finding")[0] ?? null, box = useRef<HTMLDivElement>(null), seen = useInView(box);
  return (
    <div className="flex shrink-0 flex-col items-center">
      <div ref={box} className="relative aspect-[9/16] h-[260px] overflow-hidden rounded-[14px] ring-1 ring-white/10 narrow:h-[190px]">
        {item ? <Footage section="clip-finding" item={item} play={seen} /> : <SplitClip game="gta" />}
        {item?.rank && <span className="absolute bottom-2 left-2 z-10 rounded-full bg-black/65 px-2 py-[3px] text-[11px] font-semibold text-white">Match #{item.rank}</span>}
      </div>
      <Credits items={[item]} className="mt-2" />
    </div>
  );
}

function FinderVisual() {
  return (
    <div className="flex h-full items-center gap-6 narrow:gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-5 narrow:gap-3">
        <div className="grid gap-2">
          <span className="text-[14px] font-semibold text-white/85">Describe the moments you want</span>
          <span className="rounded-[10px] bg-black/35 px-3.5 py-2.5 text-[14px] text-white/90 ring-1 ring-white/15 narrow:text-[13px]">
            Police chases that end in a crash<span className={s.caret} /></span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {["“no way”", "heist", "clutch"].map((t) => <span key={t} className="rounded-[8px] bg-white/10 px-2.5 py-1 text-[12px] text-white/75">{t}</span>)}
        </div>
        <div className="relative h-14 rounded-[10px] bg-black/35 ring-1 ring-white/10">
          {PEAKS.map(([x, h], i) => <span key={i} className={`absolute bottom-2 w-[6%] rounded-[3px] ${h === 1 ? "bg-lime" : "bg-white/25"}`}
            style={{ left: `${x * 94}%`, height: `${h * 70}%` }} />)}
          <span className={`${s.glow} absolute inset-y-1 rounded-[8px]`} style={{ left: "calc(47% * .94 - 1.5%)", width: "9%" }} />
          <span className="absolute -bottom-5 left-0 text-[11px] text-white/45">0:00</span>
          <span className="absolute -bottom-5 right-0 text-[11px] text-white/45">2:00:00</span>
        </div>
      </div>
      <FoundClip />
    </div>
  );
}

function ReframeVisual() {
  return (
    <div className="flex h-full items-center justify-center gap-5 narrow:gap-3">
      <div className="relative aspect-video w-[55%] overflow-hidden rounded-[10px] ring-1 ring-white/10">
        <Gameplay game="valorant" label={false} />
        <span className="absolute right-[3%] top-[5%] aspect-[4/3] w-[24%] overflow-hidden rounded-[5px]"><Cam /></span>
        <span className={`${s.find} absolute right-[1.5%] top-[2%] aspect-[4/3] w-[27%] rounded-[7px] border-2 border-dashed border-lime`} />
        <span className="absolute bottom-[8%] left-[14%] h-[64%] w-[46%] rounded-[7px] border-2 border-dashed border-cyan/70" />
      </div>
      <div className="flex flex-col gap-1.5" aria-hidden="true">{[0, 1, 2].map((i) => <span key={i} className={`${s.dot} h-1.5 w-1.5 rounded-full bg-white`} style={{ ["--d" as string]: `${i * 0.2}s` }} />)}</div>
      <div className="flex flex-col items-center gap-2">
        <div className="relative aspect-[9/16] h-[250px] overflow-hidden rounded-[12px] ring-1 ring-white/10 narrow:h-[170px]"><SplitClip game="valorant" /></div>
        <span className="text-[13px] font-medium text-white/80">9:16</span>
      </div>
    </div>
  );
}

const CARDS = [
  { title: "Moment finder", visual: <FinderVisual />, tone: "#2a2620",
    text: "Listens for your reactions, watches chat speed up and reads what was said, then ranks every moment of the stream. Want something specific? Describe it in your own words, or search for what was said or shown, and get a clip of every match." },
  { title: "Facecam reframe", visual: <ReframeVisual />, tone: "#22242c",
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
              style={{ background: `radial-gradient(120% 100% at 30% 0%, ${c.tone}, #0e0f12 85%)` }} aria-hidden="true">{c.visual}</div>
            <h3 className="mt-6 text-h3 text-fg">{c.title}</h3>
            <p className="mt-2 text-body-lg text-fg-2">{c.text}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}
