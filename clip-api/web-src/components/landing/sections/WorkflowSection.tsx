"use client";
import { useRef } from "react";
import { PlatformBadge, PlatformId } from "@/components/ui/PlatformGlyph";
import { ComingSoonBadge } from "../../ComingSoonBadge";
import { LinkIcon } from "../demos/Bits";
import { Credits, Footage, Item, useItems } from "../demos/Footage";
import { useInView, useReducedMotion } from "../demos/motion";
import { Eyebrow } from "../../site/Section";
import { EyebrowIcon } from "./EyebrowIcon";

// Import, auto editing, scheduling: three columns in one warm card, each a picture of the step on approved footage
// over its title and a line about it, joined by dashed arrows with a slowly turning sync mark in the logo's green.
// Step 1 is what the product does today (a pasted link or an upload; nothing is pulled from a channel by itself).
// Step 2 names only what one run does today. Step 3, scheduling, is not live: it carries the Coming soon badge, is
// written in the future tense and its picture shows no time or repeat, only the platforms the publishing code
// targets (app/publish/platforms.py: YouTube, TikTok, Instagram, Facebook). Downloading each clip is what works today.
const PLATFORMS: PlatformId[] = ["youtube", "tiktok", "instagram", "facebook"];
const clock = (sec: number) => {
  const t = Math.round(sec), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), x = t % 60;
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(x).padStart(2, "0")}`;
};

function Sync({ still }: { still: boolean }) {
  return (
    <span className="grid h-11 w-11 flex-none place-items-center rounded-full bg-[#141612] text-lime shadow-[inset_0_0_0_1.5px_#b8ff3c,0_0_18px_rgba(184,255,60,.18)]">
      <svg viewBox="0 0 24 24" className={`h-5 w-5 ${still ? "" : "animate-[spin_6s_linear_infinite]"}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 12a8 8 0 0 1 14-5.3L20 9" /><path d="M20 4v5h-5" /><path d="M20 12a8 8 0 0 1-14 5.3L4 15" /><path d="M4 20v-5h5" /></svg>
    </span>
  );
}

function Arrow({ still }: { still: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-white/40 narrow:rotate-90" aria-hidden="true">
      <span className="h-0 w-7 border-0 border-t-2 border-dashed border-current mid:w-4" />
      <Sync still={still} />
      <span className="h-0 w-5 border-0 border-t-2 border-dashed border-current mid:w-3" />
      <svg viewBox="0 0 24 24" className="-ml-2 h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
    </span>
  );
}

// A layer of a stack: out of place and faded until the card is on screen, then settling in after `delay` ms.
const settle = (on: boolean, from: string, delay: number) => ({
  transform: on ? undefined : from, opacity: on ? undefined : 0,
  transition: `transform 700ms cubic-bezier(.2,.8,.2,1) ${delay}ms, opacity 500ms ease-out ${delay}ms`,
});

export function WorkflowSection() {
  const box = useRef<HTMLDivElement>(null), seen = useInView(box, "-80px"), reduced = useReducedMotion();
  const on = seen || reduced, still = reduced;
  const hero = useItems("hero-clean"), captions = useItems("captions");
  const find = (id: string) => hero.find((i) => i.id === id) ?? null;
  const stream = find("gta-vi-source") as (Item & { source_duration_sec?: number }) | null;
  const front = captions.find((i) => i.id === "impact") ?? null;
  const behind = [find("cdl-2"), find("cdl-5")];
  const posted = find("cdl-3");
  const clips = [stream, front, ...behind, posted];
  const play = seen && !reduced;

  const steps = [
    { title: "Import", icon: <path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14" />,
      text: "Paste a link to a recorded stream or upload the file, up to six hours long. Last night's VOD is enough.",
      visual: <div className="relative h-[118px] w-[210px]">
        {[2, 1].map((k) => <span key={k} className="absolute inset-x-0 top-0 aspect-video rounded-[12px] bg-white/[.06] ring-1 ring-white/10"
          style={{ ...settle(on, "translateY(0) scale(1)", 0), transform: on ? `translateY(${k * 9}px) scale(${1 - k * .06})` : "translateY(0) scale(1)" }} />)}
        <span className="absolute inset-x-0 top-0 aspect-video overflow-hidden rounded-[12px] bg-black shadow-[0_12px_30px_rgba(0,0,0,.45)] ring-1 ring-white/10"
          style={settle(on, "translateY(10px)", 120)}>
          {stream && <Footage section="hero-clean" item={stream} play={play} />}
          {stream?.source_duration_sec ? <span className="absolute bottom-1.5 right-1.5 rounded-[5px] bg-black/70 px-1.5 py-px text-[10px] font-medium tabular-nums text-white">{clock(stream.source_duration_sec)}</span> : null}
        </span>
        <span className="absolute -right-6 top-3 flex items-center gap-1.5 rounded-[9px] bg-white px-2.5 py-1.5 text-[11px] font-medium text-[#111] shadow-[0_8px_20px_rgba(0,0,0,.35)]"
          style={settle(on, "translate(8px, -6px)", 380)}>
          <LinkIcon className="h-3 w-3 text-[#555]" />Recorded stream
          <span className="rounded-[5px] bg-lime px-1.5 py-px text-[10px] font-semibold text-ink">New</span>
        </span>
      </div> },
    { title: "Auto editing", icon: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M14 6l4 4" /></>,
      text: "The AI finds the best moments, cuts them into clips, frames them for vertical, captions every word and cuts the dead air.",
      visual: <div className="relative h-[170px] w-[150px]">
        {behind.map((c, k) => <span key={k} className="absolute left-1/2 top-0 aspect-[9/16] h-[160px] overflow-hidden rounded-[12px] bg-white/[.06] ring-1 ring-white/10"
          style={{ ...settle(on, "translateX(-50%) rotate(0deg)", 80 * k), transform: on ? `translateX(calc(-50% + ${(k + 1) * 16}px)) rotate(${(k + 1) * 5}deg)` : "translateX(-50%)",
            transformOrigin: "50% 100%", zIndex: 1 - k }}>
          {c && <Footage section="hero-clean" item={c} play={false} className="opacity-80" />}</span>)}
        <span className="absolute left-1/2 top-0 z-10 aspect-[9/16] h-[160px] -translate-x-1/2 overflow-hidden rounded-[12px] bg-black shadow-[0_12px_30px_rgba(0,0,0,.45)] ring-1 ring-white/15"
          style={settle(on, "translate(-50%, 10px)", 220)}>
          {front && <Footage section="captions" item={front} play={play} />}
        </span>
      </div> },
    { title: "Scheduling", soon: true, icon: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>,
      text: "ClutchClips will post your clips to the platforms you post to, at the times you pick. Until then, download each clip and post it yourself.",
      visual: <div className="flex h-[170px] items-center gap-4">
        <span className="relative aspect-[9/16] h-[160px] flex-none overflow-hidden rounded-[12px] bg-black shadow-[0_12px_30px_rgba(0,0,0,.45)] ring-1 ring-white/15"
          style={settle(on, "translateY(10px)", 0)}>
          {posted && <Footage section="hero-clean" item={posted} play={false} className="opacity-70" />}
        </span>
        <span className="grid gap-3" style={settle(on, "translateX(-8px)", 200)}>
          <span className="text-[15px] font-medium text-fg">New clip</span>
          <span className="flex opacity-60">{PLATFORMS.map((p, i) => <span key={p} className="-ml-2 h-9 w-9 rounded-full ring-2 ring-[#2a231d] first:ml-0" style={{ zIndex: PLATFORMS.length - i }}>
            <PlatformBadge id={p} className="h-full w-full" /></span>)}</span>
          <ComingSoonBadge className="justify-self-start" />
        </span>
      </div> },
  ];

  return (
    // The header is set larger than the other sections' (a 48 px headline, a 20 px line under it), as the reference.
    <section id="workflow" className="px-gutter py-[clamp(64px,8vw,120px)]">
      <div className="mx-auto max-w-site">
      <header className="mx-auto mb-[clamp(32px,4vw,56px)] grid max-w-prose justify-items-center gap-4 text-center">
        <Eyebrow icon={<EyebrowIcon name="loop" />}>Stream to post</Eyebrow>
        <h2 className="m-0 text-[clamp(28px,3.4vw,48px)] font-semibold leading-[1.1] tracking-[-0.03em] text-fg">Stream once,<br /> post all week</h2>
        <p className="m-0 max-w-[700px] text-[clamp(15px,1.4vw,20px)] leading-[1.5] tracking-[-0.01em] text-fg-2">
          Drop in last night&apos;s stream. ClutchClips cuts the clips, captions every word and frames each one for the shape of every platform you post to, ready to download.</p>
      </header>
      <div ref={box} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)] items-start gap-x-4 rounded-stage px-12 pb-14 pt-16 shadow-card mid:gap-x-2 mid:px-8 narrow:grid-cols-1 narrow:justify-items-center narrow:gap-y-6 narrow:px-5 narrow:py-10"
        style={{ background: "radial-gradient(70% 90% at 22% 18%, rgba(160,120,86,.38), transparent 70%), radial-gradient(60% 80% at 85% 90%, rgba(120,92,70,.32), transparent 70%), linear-gradient(160deg, #3a3029, #241f1b 60%, #1c1917)" }}>
        {steps.map((st, i) => (
          <div key={st.title} className="contents">
            {i > 0 && <span className="flex h-[170px] items-center narrow:h-auto">{<Arrow still={still} />}</span>}
            <article className="grid max-w-[330px] content-start gap-3 narrow:max-w-[360px]">
              <div className="mb-6 flex h-[170px] items-center justify-center mid:scale-[.82] narrow:scale-100" aria-hidden="true">{st.visual}</div>
              <h3 className="m-0 flex flex-wrap items-center gap-2.5 text-[20px] font-semibold leading-tight tracking-[-0.01em] text-fg">
                <svg viewBox="0 0 24 24" className="h-[22px] w-[22px] flex-none" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{st.icon}</svg>
                {st.title}{st.soon && <ComingSoonBadge />}
              </h3>
              <p className="m-0 text-[15px] leading-[1.55] text-fg-2">{st.text}</p>
            </article>
          </div>
        ))}
      </div>
      <div className="mt-3"><Credits items={clips} /></div>
      </div>
    </section>
  );
}
