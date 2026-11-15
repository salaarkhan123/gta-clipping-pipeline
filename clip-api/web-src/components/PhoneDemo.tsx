"use client";
import { useEffect, useState } from "react";
import { Stars } from "./Chrome";

const LINES = [["HE", "DID", "NOT"], ["SEE", "THAT", "COMING"], ["NO", "WAY", "BRO"]];

// A drawn example of what comes back: camera on top, gameplay below, captions on the seam.
export function PhoneDemo() {
  const [tick, setTick] = useState(4);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setTick((t) => (t + 1) % 9), 520);
    return () => clearInterval(id);
  }, []);
  const line = LINES[Math.floor(tick / 3)], word = tick % 3;
  return (
    <figure className="phone" aria-label="Example clip: the streamer's camera stacked over gameplay, with captions">
      <div className="phone-cam"><span className="head" /><span className="body" /><span className="mic" /></div>
      <div className="phone-game"><span className="sun" /><span className="road" /><span className="car" /></div>
      <p className="phone-cap">{line.map((w, i) => <span key={i} className={i === word ? "hot" : ""}>{w} </span>)}</p>
      <figcaption>
        <strong>He did not see that coming</strong>
        <Stars score={87} />
      </figcaption>
    </figure>
  );
}
