"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";
import { AuthDialog } from "@/components/Auth";
import { Footer, Nav } from "@/components/Chrome";
import { DropZone } from "@/components/DropZone";
import { PhoneDemo } from "@/components/PhoneDemo";
import { getToken, setPendingFile } from "@/lib/api";

const TOOLS = [
  { name: "Clip Maker", what: "Finds the moments worth posting.",
    how: "Scores every second on how loud the reaction is, how fast chat moves and what gets said, then cuts the top moments on sentence boundaries so nothing starts mid-word." },
  { name: "Reframe", what: "Turns widescreen into vertical without losing your face.",
    how: "Finds your camera on its own and stacks it over the gameplay. Works in 9:16, 4:5, 1:1 and 16:9." },
  { name: "Captions", what: "Burns in word-by-word captions.",
    how: "Five styles. Speech the model is unsure about, like song lyrics, is skipped. Download the text as SRT or VTT too." },
  { name: "Video Finder", what: "Search a six-hour VOD like a document.",
    how: "Type what was said or what was on screen (“police chase”, “no way”) and get a clip of each match. After the first search, more searches on that video are instant." },
];

const FAQ = [
  ["Can I paste a Twitch or YouTube link?", "Not yet. You upload the recording itself. That keeps your clips from depending on another site's download rules, and it works for any platform you stream on."],
  ["What does a credit buy?", "One credit is one minute of video. A video is charged in full once; after that, more clips, searches and reframes of the same upload only cost the minutes they render. If a job fails, the credits come back automatically."],
  ["How is the virality score worked out?", "An AI model rates each clip's hook, pacing, payoff and fit with what gaming audiences share. It is an estimate to help you pick which clip to post first, not a promise of views."],
  ["How long do you keep my files?", "Uploads and clips are deleted after 7 days. Download what you want to keep."],
  ["Is there an API?", "Yes. Everything on this site runs on the same public API, and there is a ready-made skill for AI coding agents."],
];

export default function Home() {
  const router = useRouter();
  const [auth, setAuth] = useState(false);

  function start(file: File) {
    setPendingFile(file);
    if (getToken()) router.push("/dashboard/");
    else setAuth(true);
  }

  return (
    <>
      <Nav />
      <main>
        <section className="hero">
          <div className="hero-copy">
            <h1>Drop the VOD.<br />Post the clips.</h1>
            <p className="lede">ClutchClips goes through your stream recording, cuts the moments worth posting, stacks your camera over the gameplay and adds captions.</p>
            <DropZone onFile={start} />
            <p className="hero-terms">Free to try: 30 credits when you sign up, no card. One credit is one minute of video.</p>
          </div>
          <PhoneDemo />
        </section>

        <section className="band" id="tools">
          <h2>Four tools, one upload</h2>
          <dl className="tools">
            {TOOLS.map((t) => (
              <div key={t.name}><dt>{t.name}</dt><dd><strong>{t.what}</strong> {t.how}</dd></div>
            ))}
          </dl>
        </section>

        <section className="band steps-band">
          <h2>From recording to posted in three steps</h2>
          <ol className="steps">
            <li><h3>Upload the recording</h3><p>Straight from OBS, or the VOD you downloaded from your own channel.</p></li>
            <li><h3>Pick from what comes back</h3><p>Each clip arrives with a title, hashtags and a score, so you can see which to post first.</p></li>
            <li><h3>Download and post</h3><p>MP4s sized for TikTok, Shorts and Reels, with captions already on them.</p></li>
          </ol>
        </section>

        <section className="band faq">
          <h2>Straight answers</h2>
          {FAQ.map(([q, a]) => (<details key={q}><summary>{q}</summary><p>{a}</p></details>))}
        </section>

        <section className="band closer">
          <h2>Your last stream already has clips in it.</h2>
          <Link href={"/login/?new=1"} className="btn primary">Sign up free</Link>
          <Link href="/pricing/" className="btn ghost">See pricing</Link>
        </section>
      </main>
      <Footer />
      <AuthDialog open={auth} onClose={() => setAuth(false)} onDone={() => router.push("/dashboard/")}
        note="Create an account and your video starts uploading straight away." />
    </>
  );
}
