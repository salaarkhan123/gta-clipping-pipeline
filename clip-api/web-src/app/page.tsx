"use client";
// The landing page: hero with the start input, the feature sections (components/landing/sections/), FAQ, closing call to
// action, footer, and the start input again as a bar pinned to the bottom once the hero's has scrolled away.
// Numbers that can change (sign-up credits, languages) come from the public API; nothing about a plan is written here.
import Link from "next/link";
import { Footer, Nav } from "@/components/Chrome";
import { Faq, FaqItem } from "@/components/Faq";
import { Eyebrow } from "@/components/site/Section";
import { StartBar, StartInput, useStart } from "@/components/StartInput";
import { Languages, useLanguages } from "@/lib/languages";
import { freeCredits, useSignupCredits } from "@/lib/plans";
import { isBuilt, TOOLS } from "@/lib/tools";
// Landing sections (agent B).
import { DemoCarousel } from "@/components/landing/sections/DemoCarousel";
import { EditorSection } from "@/components/landing/sections/EditorSection";
import { ModelsSection } from "@/components/landing/sections/ModelsSection";
import { TeamsSection } from "@/components/landing/sections/TeamsSection";
import { WorkflowSection } from "@/components/landing/sections/WorkflowSection";
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

export default function Home() {
  const start = useStart();
  const signup = useSignupCredits(), langs = useLanguages();
  return (
    <>
      <Nav />
      <main>
        <header className="grid justify-items-center px-gutter pb-[clamp(32px,4vw,48px)] pt-[clamp(48px,7vw,96px)] text-center">
          <Eyebrow bright>AI clipping for gaming streams</Eyebrow>
          <h1 className="mt-[clamp(12px,1.6vw,24px)] max-w-site text-display text-fg">Stream for hours. Post clips in minutes.</h1>
          <p className="mt-[clamp(12px,1.4vw,20px)] max-w-prose text-lead text-fg-2">
            ClutchClips finds the clutch moments in your VOD, stacks your facecam over the gameplay, captions every word and gives each clip an AI rating.</p>
          <div className="mt-[clamp(28px,3.5vw,48px)] flex w-full items-center justify-center gap-4 narrow:flex-col narrow:gap-3">
            <StartInput start={start} id="start-hero" />
            <span className="text-[16px] font-medium text-fg-2 narrow:hidden">or</span>
            <Link href="/pricing/" className="btn btn-ghost h-16 px-6 narrow:hidden">See pricing</Link>
          </div>
          <p className="mt-4 text-[14px] text-fg-2">{freeCredits(signup)} · No card needed</p>
        </header>

        {/* Landing sections (agent B): begin. Carousel under the hero, then the feature sections, in the reference's order. */}
        <DemoCarousel />
        <ModelsSection />
        <WorkflowSection />
        <EditorSection />
        <TeamsSection />
        {/* Landing sections (agent B): end */}

        <section id="faq" className="px-gutter py-[clamp(64px,8vw,120px)]">
          <h2 className="mb-[clamp(28px,4vw,56px)] text-center text-h2 text-fg">Got questions?</h2>
          <Faq items={faq(signup, langs)} />
        </section>

        <section className="px-gutter pb-[clamp(64px,8vw,120px)] pt-0">
          <div className="mx-auto grid max-w-site justify-items-center gap-6 rounded-stage bg-surface px-6 py-[clamp(48px,6vw,80px)] text-center">
            <h2 className="text-[clamp(24px,2vw+8px,36px)] leading-[1.1] tracking-[-0.03em] text-fg">Your last stream already has clips in it</h2>
            {/* Back to the hero's input: one way in, the same for signed-in and new visitors. */}
            <button type="button" className="btn btn-primary h-[52px]" onClick={() => {
              const el = document.getElementById("start-hero-link");
              el?.scrollIntoView({ behavior: "smooth", block: "center" }); el?.focus({ preventScroll: true });
            }}>Start clipping free</button>
            <p className="text-[14px] text-fg-2">{freeCredits(signup)} · No card needed</p>
          </div>
        </section>
      </main>
      <Footer />
      <StartBar start={start} after="start-hero" before="site-footer" />
      {start.dialog}
    </>
  );
}
