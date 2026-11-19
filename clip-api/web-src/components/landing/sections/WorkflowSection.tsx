"use client";
import { useRef } from "react";
import { ComingSoonBadge } from "../../ComingSoonBadge";
import { LinkIcon } from "../demos/Bits";
import { Credits, Footage, useItems } from "../demos/Footage";
import { useInView } from "../demos/motion";
import { Section } from "../../site/Section";
import { EyebrowIcon } from "./EyebrowIcon";

// Import, auto edit, post. Importing and editing work today; posting on a schedule is not built and says so.
function Arrow() {
  return (
    <span className="flex items-center gap-1 text-white/35 narrow:rotate-90" aria-hidden="true">
      <span className="h-px w-6 border-t border-dashed border-current" />
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
    </span>
  );
}

const STEPS = [
  { title: "Import", soon: false, icon: <path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14" />,
    text: "Paste Twitch or Kick links, several at once, or a Google Drive or Dropbox share link. Or upload the recording itself.",
    visual: <div className="flex w-full max-w-[230px] flex-col gap-2">
      {["twitch.tv/videos/…", "kick.com/…/videos/…", "stream-friday.mkv"].map((t, i) =>
        <span key={t} className="flex items-center gap-2 rounded-[9px] bg-black/40 px-3 py-2 text-[12px] text-white/80 ring-1 ring-white/10">
          {i < 2 ? <LinkIcon className="h-3.5 w-3.5 text-white/50" /> : <span className="h-3.5 w-3.5 rounded-[3px] border border-white/40" />}{t}</span>)}
    </div> },
  { title: "Auto editing", soon: false, icon: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M14 6l4 4" /></>,
    text: "In one run the AI finds the moments, reframes them to vertical, adds captions and a hook, and cuts the dead air.",
    visual: <EditedClips /> },
  { title: "Auto posting", soon: true, icon: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></>,
    text: "ClutchClips will post the clips you pick to TikTok, YouTube Shorts and Instagram on a schedule you set. Until then, download and post.",
    visual: <div className="grid w-full max-w-[200px] grid-cols-4 gap-1.5 opacity-70">
      {Array.from({ length: 12 }, (_, i) => <span key={i} className="aspect-square rounded-[6px] border border-dashed border-white/25" />)}
    </div> },
];

// Three finished clips from three different games, from the media pipeline. Empty frames until it has them.
function EditedClips() {
  const box = useRef<HTMLDivElement>(null), seen = useInView(box, "0px");
  const games = new Set<string>();
  const clips = useItems("hero-vertical-clips").filter((i) => /^clip-\d+$/.test(i.id) && i.game && !games.has(i.game) && !!games.add(i.game)).slice(0, 3);
  return (
    <div ref={box} className="flex flex-col items-center gap-2">
      <div className="flex items-end gap-2">
        {[0, 1, 2].map((i) => <span key={clips[i]?.id ?? i} className="relative aspect-[9/16] overflow-hidden rounded-[9px] bg-white/[.04] ring-1 ring-white/10" style={{ height: 130 - i * 14 }}>
          {clips[i] && <Footage section="hero-vertical-clips" item={clips[i]} play={seen} />}</span>)}
      </div>
      <Credits items={clips} />
    </div>
  );
}

export function WorkflowSection() {
  return (
    <Section id="workflow" eyebrow="Workflow" icon={<EyebrowIcon name="loop" />} title={<>Your clipping routine,<br className="narrow:hidden" /> mostly on autopilot</>}
      sub="Bring in last night's stream, let the AI do the edit, and download clips ready to post. Posting for you is next.">
      <div className="flex items-start justify-center gap-4 rounded-stage px-10 py-14 shadow-card narrow:flex-col narrow:items-center narrow:px-5 narrow:py-8"
        style={{ background: "radial-gradient(90% 120% at 20% 10%, #33281e, #121214 75%)" }}>
        {STEPS.map((st, i) => (
          <div key={st.title} className="contents">
            {i > 0 && <span className="mt-[72px] narrow:mt-0"><Arrow /></span>}
            <article className="flex max-w-[300px] flex-1 flex-col items-start gap-5 narrow:max-w-[340px]">
              <div className="flex h-[150px] w-full items-center justify-center" aria-hidden="true">{st.visual}</div>
              <h3 className="flex flex-wrap items-center gap-2.5 text-h3 text-fg">
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{st.icon}</svg>
                {st.title}{st.soon && <ComingSoonBadge />}
              </h3>
              <p className="-mt-2 text-body-lg text-fg-2">{st.text}</p>
            </article>
          </div>
        ))}
      </div>
    </Section>
  );
}
