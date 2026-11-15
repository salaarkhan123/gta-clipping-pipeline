"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

export function Logo() {
  return (
    <Link href="/" className="logo" aria-label="ClutchClips home">
      <span className="logo-mark" aria-hidden="true">CC</span>
      <span>ClutchClips</span>
    </Link>
  );
}

export function Nav() {
  const [authed, setAuthed] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => setAuthed(!!getToken()), []);
  return (
    <header className="nav">
      <div className="nav-inner">
        <Logo />
        <nav className={`nav-links ${open ? "open" : ""}`}>
          <Link href="/#tools">Tools</Link>
          <Link href="/#earnings">Earnings</Link>
          <Link href="/pricing/">Pricing</Link>
          <a href="https://api.clutchclips.io/docs">API</a>
          <Link href="/contact/">Contact</Link>
        </nav>
        <div className="nav-cta">
          {authed ? <Link href="/dashboard/" className="btn btn-primary">Open dashboard</Link>
            : <><Link href="/login/" className="login">Log in</Link><Link href="/login/?new=1" className="btn btn-primary">Start free</Link></>}
          <button className="burger" aria-label="Menu" aria-expanded={open} onClick={() => setOpen(!open)}>☰</button>
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="footer">
      <div className="container footer-inner">
        <div>
          <Logo />
          <p className="muted">AI clipping for gaming streams. Upload your own recordings, or ones you have permission to clip.</p>
        </div>
        <nav>
          <h4>Product</h4>
          <Link href="/#tools">Tools</Link>
          <Link href="/pricing/">Pricing</Link>
          <a href="https://api.clutchclips.io/docs">API docs</a>
        </nav>
        <nav>
          <h4>Company</h4>
          <Link href="/contact/">Contact</Link>
          <a href="mailto:support@clutchclips.io">support@clutchclips.io</a>
        </nav>
      </div>
      <p className="container copy">© {new Date().getFullYear()} ClutchClips</p>
    </footer>
  );
}

// Virality score as a bar, like the reference design.
export function Stars({ score }: { score: number }) {
  return (
    <span className="vscore" role="img" aria-label={`Virality ${score} out of 100`}>
      <span className="score-bar"><span style={{ width: `${score}%` }} /></span><b>{score}</b>
    </span>
  );
}
