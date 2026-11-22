"use client";
// The landing page: the headline and the import field, the stage showing the product working, the workflow (import, auto editing, scheduling), the
// finished clips, FAQ and a closing call to action; the import field again as a bar pinned to the bottom once the
// hero's has scrolled away.
// Numbers that can change (sign-up credits, languages) come from the public API; nothing about a plan is written here.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Footer, Nav } from "@/components/Chrome";
import { Faq, FaqItem } from "@/components/Faq";
import { StartBar, StartInput, useStart } from "@/components/StartInput";
import { Languages, useLanguages } from "@/lib/languages";
import { freeCredits, useSignupCredits } from "@/lib/plans";
import { isBuilt, TOOLS } from "@/lib/tools";
import { DemoCarousel } from "@/components/landing/sections/DemoCarousel";
import { WorkflowSection } from "@/components/landing/sections/WorkflowSection";
import { aiRated, useItems } from "@/components/landing/demos/Footage";
import { useReducedMotion } from "@/components/landing/demos/motion";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ClipCard } from "@/components/ui/ClipCard";
import { Score } from "@/components/ui/Score";
import { mediaUrl } from "@/lib/media";
import { linkPhrase, platformNames, VERIFIED_PLATFORMS } from "@/lib/platforms";

const list = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

function faq(signup: number | null, langs: Languages | null): FaqItem[] {
  const on = langs ? { translation: langs.translation, summaries: langs.summaries } : null;
  const soon = [...TOOLS.filter((t) => !isBuilt(t, on)).map((t) => t.name), "Auto-post and scheduling"];
  const spoken = langs?.languages.filter((l) => l.transcribe) || [];
  return [
    { q: "How does ClutchClips work?", a: <>
      <p>Paste {linkPhrase()}, or upload the recording. ClutchClips reads the transcript, listens for the hype, finds the strongest moments and cuts them into vertical clips with your facecam stacked over the gameplay and captions on.</p>
      <p>Every clip gets an AI rating, so you know which one to post first.</p></> },
    { q: "What videos can I use?", a: <>
      <p>Streams and VODs you own, or have permission to clip. Upload MP4, MOV, MKV or WebM files up to 8 GB and 6 hours long.</p>
      <p>{VERIFIED_PLATFORMS.length ? `Links work for public ${platformNames()} videos. ` : ""}If a link can't be imported, upload the file instead. Every link import asks you to confirm you own the video or have permission to clip it.</p></> },
    { q: "Which languages are supported?", a: spoken.length
      ? <p>Speech in {spoken.length} languages can be transcribed and captioned, including {list(spoken.slice(0, 6).map((l) => l.name))}. Pick the spoken language when you start, or let it be detected.{langs && !langs.translation ? " Translated captions are coming soon." : ""}</p>
      : <p>Pick the spoken language when you start a job. The list in the app shows every language that can be transcribed.</p> },
    { q: "Can I add captions?", a: <p>Yes. Clips come with word-by-word animated captions, and you can pick the style. The AI Captions tool burns captions into any part of a video, and you can download them as SRT or VTT.</p> },
    { q: "Is ClutchClips free to use?", a: <>
      <p>You can start free: new accounts get {signup === null ? "free credits" : `${signup.toLocaleString()} free credits`} once the email is confirmed. No card needed.</p>
      <p>Clipping uses one credit per minute of source video; every other tool shows its price before you start. Credits don&apos;t expire, and if a job fails its credits come back automatically. <Link href="/pricing/">See pricing</Link>.</p></> },
    { q: "What's coming soon?", a: <p>{list(soon)} are coming soon. They aren&apos;t in the app yet; everything else on this page works today.</p> },
    { q: "How long do you keep my files?", a: <p>Uploads and clips are deleted after 7 days. Download the clips you want to keep.</p> },
    { q: "I have more questions!", a: <p>Email <a href="mailto:support@clutchclips.io">support@clutchclips.io</a> or use the <Link href="/contact/">contact page</Link>. A person replies.</p> },
  ];
}

// What the highlighted phrase of the headline turns through: the kinds of moment the clip finder labels.
const PHRASES = ["clutch plays", "funny fails", "big reactions", "wild moments"];

// One phrase of the headline in a soft pill with a lime-tinted glow, changing every few seconds. The phrases are
// stacked in one cell and slide entirely inside the pill, which clips them and eases its width to the phrase
// shown. Still under reduced motion.
function Rotating({ phrases }: { phrases: string[] }) {
  const [at, setAt] = useState(0), [width, setWidth] = useState<number | null>(null);
  const reduced = useReducedMotion();
  const spans = useRef<(HTMLSpanElement | null)[]>([]);
  useEffect(() => {
    if (reduced) return;
    const t = setInterval(() => setAt((i) => (i + 1) % phrases.length), 2600);
    return () => clearInterval(t);
  }, [reduced, phrases.length]);
  // The pill is exactly as wide as the phrase shown: measured again when the phrase, the font or the window changes.
  useEffect(() => {
    const el = spans.current[at];
    if (!el) return;
    const fit = () => setWidth(Math.ceil(el.getBoundingClientRect().width));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    document.fonts?.ready.then(fit).catch(() => {});
    return () => ro.disconnect();
  }, [at]);
  const before = (at + phrases.length - 1) % phrases.length;
  return (
    <span className="relative inline-block overflow-hidden rounded-pill bg-[#10160f] px-[.5em] py-[.14em] align-middle shadow-[inset_0_0_0_1px_rgba(184,255,60,.16)]">
      <span aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_120%_at_18%_100%,rgba(184,255,60,.28),transparent_70%),radial-gradient(50%_120%_at_85%_0%,rgba(60,240,255,.16),transparent_70%)]" />
      <span className="relative grid justify-items-start overflow-hidden transition-[width] duration-slow ease-out" style={{ width: width ?? undefined }}>
        {phrases.map((p, i) => (
          <span key={p} ref={(el) => { spans.current[i] = el; }} aria-hidden={i !== at}
            className={`col-start-1 row-start-1 whitespace-nowrap transition-[opacity,transform] duration-slow ease-out
              ${i === at ? "translate-y-0 opacity-100" : i === before ? "-translate-y-[130%] opacity-0" : "translate-y-[130%] opacity-0"}`}>{p}</span>
        ))}
      </span>
    </span>
  );
}

// The finished clips, large: the approved footage of the hero section with the AI's rating of each.
function ClipWall() {
  // clip-6 (Fortnite) is left out: it is soft, with the character half out of frame, and the other approved Fortnite
  // candidates are menu screens. The slot comes back when a sharper approved Fortnite clip exists.
  const clips = useItems("hero-vertical-clips").filter((i) => /^clip-[1-5]$/.test(i.id));
  return (
    <section aria-labelledby="wall-title" className="px-gutter py-[clamp(56px,7vw,112px)]">
      <div className="mx-auto grid max-w-site gap-[clamp(28px,3.4vw,48px)]">
        <div className="grid justify-items-center gap-3 text-center">
          <h2 id="wall-title" className="m-0 text-h2 text-fg">Clips that look ready to post</h2>
          <p className="m-0 max-w-[560px] text-lead text-fg-2">Framed for vertical, captioned word by word, and rated so you know which one to post first.</p>
        </div>
        <ul className="m-0 grid list-none grid-cols-5 gap-4 p-0 mid:grid-cols-3 narrow:grid-cols-2 narrow:gap-3">
          {clips.map((c) => (
            <li key={c.id}>
              <ClipCard shape="tall" poster={c.poster ? mediaUrl("hero-vertical-clips", c.poster) : null} video={mediaUrl("hero-vertical-clips", c.src)}
                webm={c.webm ? mediaUrl("hero-vertical-clips", c.webm) : null} title={c.game || c.label} meta={c.credit}
                score={aiRated(c) ? <Score value={c.rating!} kind="ai" /> : undefined} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function Home() {
  const start = useStart();
  const signup = useSignupCredits(), langs = useLanguages();
  return (
    <>
      <Nav />
      <main>
        {/* Sizes and gaps follow the measured reference: eyebrow 80 px under the header, a 60 px two-line headline,
            a 20 px subhead, a 64 px field 48 px below it. On a phone: 24 px headline, 14 px subhead. */}
        <header className="grid justify-items-center px-gutter pb-7 pt-20 text-center narrow:pb-5 narrow:pt-6">
          <p className="m-0 text-[16px] font-semibold uppercase leading-[20px] tracking-[.0125em] text-fg-2 narrow:text-[12px] narrow:font-medium">Engineered for gamers</p>
          <h1 className="m-0 mt-6 font-sans text-[60px] font-semibold leading-[1.18] tracking-[-0.04em] text-fg mid:text-[52px] narrow:mt-3 narrow:text-[24px] narrow:leading-[1.35] narrow:tracking-[-0.025em]">
            <span className="block">Turn your gaming streams into</span>
            <span className="mt-[2px] flex flex-wrap items-center justify-center gap-x-[.28em]"><Rotating phrases={PHRASES} /><span>ready to post</span></span>
          </h1>
          <p className="m-0 mt-6 max-w-[660px] text-[20px] leading-[30px] tracking-[-0.02em] text-fg-2 narrow:mt-3 narrow:text-[14px] narrow:leading-[22px] narrow:tracking-normal">
            ClutchClips finds the best moments in a stream, frames them for every platform and captions every word.</p>
          <div className="mt-12 flex w-full items-center justify-center gap-3 narrow:mt-6 narrow:flex-col">
            <StartInput start={start} id="start-hero" />
            <span className="text-[16px] font-medium text-fg-2 narrow:hidden">or</span>
            <Button href="/pricing/" variant="secondary" className="!h-16 !px-6 !text-[17px] narrow:!h-12 narrow:w-full narrow:!text-[15px]">See pricing</Button>
          </div>
          <p className="m-0 mt-4 text-[15px] text-fg-2 narrow:text-[13px]">{freeCredits(signup)} · No card needed</p>
        </header>

        <DemoCarousel />

        <WorkflowSection />

        <ClipWall />

        <section id="faq" className="px-gutter pb-[clamp(56px,7vw,112px)] pt-0">
          <h2 className="mb-[clamp(28px,3.4vw,48px)] text-center text-h2 text-fg">Got questions?</h2>
          <Faq items={faq(signup, langs)} />
        </section>

        <section className="px-gutter pb-[clamp(56px,7vw,112px)] pt-0">
          <Card className="mx-auto grid max-w-site justify-items-center gap-5 !px-6 !py-[clamp(44px,5vw,72px)] text-center">
            <h2 className="m-0 text-h2 text-fg">Your last stream already has clips in it</h2>
            {/* Back to the hero's input: one way in, the same for signed-in and new visitors. */}
            <Button size="lg" onClick={() => {
              const el = document.getElementById("start-hero-link");
              el?.scrollIntoView({ behavior: "smooth", block: "center" }); el?.focus({ preventScroll: true });
            }}>Start clipping free</Button>
            <p className="m-0 text-[13px] text-fg-2">{freeCredits(signup)} · No card needed</p>
          </Card>
        </section>
      </main>
      <Footer />
      <StartBar start={start} after="start-hero" before="site-footer" />
      {start.dialog}
    </>
  );
}
