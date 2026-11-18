"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { AuthDialog } from "@/components/Auth";
import { Footer, Nav } from "@/components/Chrome";
import { DropZone } from "@/components/DropZone";
import { getToken, setPendingFile } from "@/lib/api";
import { freeCredits, useSignupCredits } from "@/lib/plans";

const TYPED = ["Find the clutch moments in a 5-hour VOD", "Stack your facecam over the gameplay", "Word-by-word captions, ready to post"];

const SOURCES = ["Twitch VODs", "YouTube Gaming", "Kick", "OBS recordings", "Streamlabs", "Medal", "NVIDIA ShadowPlay", "Xbox captures", "PlayStation captures", "MP4", "MOV", "MKV"];

const TOOLS: { ico: string; name: string; text: string; soon?: boolean }[] = [
  { ico: "🎯", name: "AI Clip Finder", text: "Scores every second on reaction volume, chat speed and what gets said, then cuts the top moments on sentence boundaries." },
  { ico: "🔥", name: "Virality Score", text: "Every clip gets a 0–100 score for hook, pacing and payoff, so you post the strongest one first." },
  { ico: "💬", name: "Animated Captions", text: "Word-by-word captions in five styles. Download them as SRT or VTT too." },
  { ico: "📐", name: "Auto Reframe", text: "Finds your facecam on its own and stacks it over the gameplay. 9:16, 4:5, 1:1 and 16:9." },
  { ico: "🔎", name: "Find Any Moment", text: "Type what was said or shown (“police chase”, “no way”) and get a clip of every match." },
  { ico: "🪝", name: "AI Titles & Hashtags", text: "Each clip comes with a title and hashtags written for TikTok, Shorts and Reels." },
  { ico: "🔴", name: "Live Stream Clipper", text: "Clip a Twitch or Kick stream while it's still live.", soon: true },
  { ico: "⚡", name: "Bulk Import", text: "Queue a whole week of VODs at once.", soon: true },
  { ico: "📅", name: "Auto-Post & Schedule", text: "Post straight to TikTok, YouTube and Instagram on a schedule.", soon: true },
];

const faq = (signup: number | null): [string, string][] => [
  ["How does ClutchClips work?", "Upload a stream recording. The AI listens for hype, reads the transcript, finds the strongest moments, cuts them into vertical clips with your facecam on top and captions on the seam, and scores each one."],
  ["Can I paste a Twitch or YouTube link?", "Not yet. You upload the recording itself, from OBS or the VOD you downloaded from your own channel."],
  ["How long does it take?", "On our servers a 2-hour VOD takes about 11 minutes to clip once it's uploaded. Upload time depends on your connection."],
  ["What does a credit buy?", "One credit is one minute of video. A 2-hour stream uses 120 credits, however many clips you make from it. If a job fails, the credits come back automatically."],
  ["Is it free to try?", `Yes. New accounts get ${signup === null ? "free credits" : `${signup} free credits`}. No card needed.`],
  ["How long do you keep my files?", "Uploads and clips are deleted after 7 days. Download what you want to keep."],
];

function Typer() {
  const [i, setI] = useState(0), [n, setN] = useState(0), [del, setDel] = useState(false);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setN(TYPED[0].length); return; }
    const s = TYPED[i];
    const t = setTimeout(() => {
      if (!del && n < s.length) setN(n + 1);
      else if (!del) setDel(true);
      else if (n > 0) setN(n - 1);
      else { setDel(false); setI((i + 1) % TYPED.length); }
    }, !del && n === s.length ? 1600 : del ? 22 : 45);
    return () => clearTimeout(t);
  }, [i, n, del]);
  return <p className="typer" aria-label={TYPED.join(". ")}><span aria-hidden="true">{TYPED[i].slice(0, n)}</span><span className="caret" /></p>;
}

function Earnings() {
  const [clips, setClips] = useState(10), [views, setViews] = useState(5000), [rate, setRate] = useState(1);
  const total = Math.round(clips * 30 * views / 1000 * rate);
  return (
    <div className="calc">
      <div>
        <label>Clips posted per day <span>{clips}</span>
          <input type="range" min={1} max={100} value={clips} onChange={(e) => setClips(+e.target.value)} /></label>
        <label>Average views per clip <span>{views.toLocaleString()}</span>
          <input type="range" min={500} max={100000} step={500} value={views} onChange={(e) => setViews(+e.target.value)} /></label>
        <label>Campaign rate per 1K views <span>${rate.toFixed(2)}</span>
          <input type="range" min={0.25} max={5} step={0.25} value={rate} onChange={(e) => setRate(+e.target.value)} /></label>
      </div>
      <div className="calc-out">
        <p>Estimated monthly earnings</p>
        <p className="calc-num grad">${total.toLocaleString()}</p>
        <p className="small">An estimate only. Real payouts depend on the campaign and how your clips perform.</p>
      </div>
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const [auth, setAuth] = useState(false);
  const signup = useSignupCredits();

  function start(file: File) {
    setPendingFile(file);
    if (getToken()) router.push("/dashboard/");
    else setAuth(true);
  }

  return (
    <>
      <Nav />
      <main>
        <header className="hero">
          <div className="float-card left" aria-hidden="true">
            <h5>✂️ AI Clipping</h5>
            <div className="fake-video"><span className="tag">● DETECTING: CLUTCH PLAY</span><span className="scan" /><span className="time">3:42:15</span></div>
            <div className="chip-row"><span className="chip">Hype spikes</span><span className="chip">Chat speed</span></div>
          </div>
          <div className="float-card right" aria-hidden="true">
            <h5>🔥 Virality Score <small>example</small></h5>
            {[["“He actually did it”", 98], ["Chat goes crazy", 91], ["Getaway fail", 84]].map(([t, s]) => (
              <div key={t as string}><div className="moment"><span>{t}</span><b>{s}</b></div>
                <div className="score-bar"><span style={{ width: `${s}%` }} /></div></div>))}
          </div>

          <div className="container hero-content">
            <span className="pill"><span className="dot" />AI CLIPPING FOR GAMING STREAMS</span>
            <h1>Clip. Caption. <span className="grad">Go Viral.</span></h1>
            <Typer />
            <DropZone onFile={start} />
            <p className="hero-note">{freeCredits(signup)} · No credit card required</p>
          </div>
        </header>

        <p className="trusted">Works with recordings from</p>
        <div className="marquee" aria-label={SOURCES.join(", ")}>
          <div className="marquee-track" aria-hidden="true">{[...SOURCES, ...SOURCES].map((s, i) => <span key={i}>{s}</span>)}</div>
        </div>

        <div className="container stats">
          <div className="stat"><h3>~11 min</h3><p>To clip a 2-hour VOD</p></div>
          <div className="stat"><h3>4</h3><p>Aspect ratios, from 9:16 to 16:9</p></div>
          <div className="stat"><h3>5</h3><p>Animated caption styles</p></div>
        </div>

        <section>
          <div className="container">
            <h2 className="section-title">From 5-hour stream to <span className="grad">viral clips</span> in 3 steps</h2>
            <p className="section-sub">No scrubbing timelines. No manual captions. Upload, pick and post.</p>
            <ol className="steps">
              <li className="step"><h3>Upload the recording</h3><p>Straight from OBS, or the VOD you downloaded from your channel. MP4, MOV, MKV or WebM up to 8 GB.</p></li>
              <li className="step"><h3>AI finds the moments</h3><p>It listens for hype, reads the transcript, scores every moment and cuts ready-to-post clips.</p></li>
              <li className="step"><h3>Download and post</h3><p>Vertical MP4s with your facecam on top, captions on, and a title and hashtags for each.</p></li>
            </ol>
          </div>
        </section>

        <section id="tools" className="flush">
          <div className="container">
            <h2 className="section-title">Every tool a clipper needs</h2>
            <p className="section-sub">One workspace for finding, reframing and captioning clips, built only for gaming streams.</p>
            <div className="tools-grid">
              {TOOLS.map((t) => (
                <div key={t.name} className={`tool ${t.soon ? "soon" : ""}`}>
                  <div className="ico" aria-hidden="true">{t.ico}</div>
                  <h3>{t.name}{t.soon && <span className="badge">Coming soon</span>}</h3>
                  <p>{t.text}</p>
                </div>))}
            </div>
          </div>
        </section>

        <section id="earnings" className="flush">
          <div className="container">
            <h2 className="section-title">How much could you earn clipping?</h2>
            <p className="section-sub">Clipping campaigns pay per 1,000 views. Estimate your month.</p>
            <Earnings />
          </div>
        </section>

        <section className="flush">
          <div className="container">
            <h2 className="section-title">Frequently asked questions</h2>
            <p className="section-sub">Everything you need to know before you start clipping.</p>
            <div className="faq">
              {faq(signup).map(([q, a], i) => (<details key={q} open={i === 0}><summary>{q}</summary><p>{a}</p></details>))}
            </div>
          </div>
        </section>

        <section className="flush">
          <div className="container">
            <div className="cta-band">
              <h2>Stop scrubbing. <span className="grad">Start clipping.</span></h2>
              <p>Your last stream already has clips in it.</p>
              <Link href="/login/?new=1" className="btn btn-primary btn-lg">Start Clipping Free</Link>
              <p className="hero-note">{freeCredits(signup)} · No credit card required</p>
            </div>
          </div>
        </section>
      </main>
      <Footer />
      <AuthDialog open={auth} onClose={() => setAuth(false)} onDone={() => router.push("/dashboard/")}
        note="Create an account and your video starts uploading straight away." />
    </>
  );
}
