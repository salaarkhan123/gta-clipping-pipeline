"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

export function Logo() {
  return (
    <Link href="/" className="logo" aria-label="ClutchClips home">
      <svg viewBox="0 0 28 28" width="26" height="26" aria-hidden="true">
        <rect x="1" y="1" width="26" height="26" rx="7" fill="var(--pink)" />
        <path d="M11 8.2v11.6L20.5 14z" fill="var(--ink)" />
      </svg>
      <span>ClutchClips</span>
    </Link>
  );
}

export function Nav() {
  const [authed, setAuthed] = useState(false);
  useEffect(() => setAuthed(!!getToken()), []);
  return (
    <header className="nav">
      <Logo />
      <nav>
        <Link href="/#tools">Tools</Link>
        <Link href="/pricing/">Pricing</Link>
        <a href="https://api.clutchclips.io/docs">API</a>
        {authed ? <Link href="/dashboard/" className="btn small primary">Open dashboard</Link>
          : <><Link href="/login/">Log in</Link><Link href="/login/?new=1" className="btn small primary">Sign up free</Link></>}
      </nav>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <Logo />
      <p>Upload your own recordings, or ones you have permission to clip.</p>
      <nav>
        <Link href="/pricing/">Pricing</Link>
        <a href="https://api.clutchclips.io/docs">API docs</a>
        <a href="mailto:support@clutchclips.io">support@clutchclips.io</a>
      </nav>
    </footer>
  );
}

// Virality as a five-star heat meter, like a wanted level.
export function Stars({ score }: { score: number }) {
  const lit = Math.max(1, Math.min(5, Math.round(score / 20)));
  return (
    <span className="stars" role="img" aria-label={`Virality ${score} out of 100`}>
      {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= lit ? "on" : ""}>★</i>)}
      <b>{score}</b>
    </span>
  );
}
