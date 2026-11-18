import { ComingSoon } from "../demos/Bits";
import { SectionHead } from "./SectionHead";

// Templates per game and your own saved looks, team workspaces (not built), and the public API.
// Game and template names are the API's own (app/templates.py).
const GAMES = ["GTA 5", "Valorant", "Fortnite", "Apex Legends", "League of Legends", "CS2", "Minecraft", "Rust"];
const GTA_TEMPLATES = ["GTA RP reaction", "Car chase", "Heist moments", "Funny fails"];

function TemplatesVisual() {
  return (
    <div className="flex w-full max-w-[330px] flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        {GAMES.slice(0, 5).map((g, i) => <span key={g} className={`rounded-full px-2.5 py-1 text-[11px] ${i === 0 ? "bg-white font-semibold text-black" : "bg-white/10 text-white/70"}`}>{g}</span>)}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {GTA_TEMPLATES.map((t, i) => <span key={t} className={`rounded-[8px] px-2.5 py-2 text-[12px] ${i === 1 ? "bg-lime/15 text-lime ring-1 ring-lime/50" : "bg-black/40 text-white/80 ring-1 ring-white/10"}`}>{t}</span>)}
      </div>
      <div className="rounded-[10px] bg-black/40 p-2.5 ring-1 ring-white/10">
        <p className="text-[10px] font-semibold uppercase tracking-[.08em] text-white/45">My templates</p>
        <p className="mt-1 text-[13px] font-medium">Friday RP look</p>
        <p className="text-[11px] text-white/55">9:16 · Split in two · Impact captions · Excited hook</p>
      </div>
    </div>
  );
}

function TeamVisual() {
  return (
    <div className="flex w-full max-w-[260px] flex-col gap-2 opacity-70">
      {["Shared folder", "Review queue", "Members"].map((t) => <span key={t} className="flex h-10 items-center rounded-[9px] border border-dashed border-white/25 px-3 text-[12px] text-white/50">{t}</span>)}
    </div>
  );
}

function ApiVisual() {
  return (
    <pre className="w-full max-w-[340px] overflow-hidden rounded-[12px] bg-black/50 p-3.5 text-[11.5px] leading-[1.6] text-white/80 ring-1 ring-white/10">
      <code>
        <span className="text-cyan">POST</span> /v1/clips{"\n"}
        {"{"} <span className="text-lime">&quot;upload_id&quot;</span>: &quot;up_8f2…&quot;,{"\n"}
        {"  "}<span className="text-lime">&quot;options&quot;</span>: {"{"} <span className="text-lime">&quot;template&quot;</span>: &quot;car-chase&quot; {"}"} {"}"}{"\n\n"}
        <span className="text-white/45">→ clips, best first, with the AI rating:</span>{"\n"}
        {"  "}title, start_sec, end_sec,{"\n"}
        {"  "}display_score, video_url
      </code>
    </pre>
  );
}

const CARDS = [
  { title: "Templates for your game", soon: false, visual: <TemplatesVisual />,
    text: "Pick a template for GTA 5, Valorant, Fortnite, League and more, and the layout, captions and clip length are set for that game. Save your own look and reuse it next stream." },
  { title: "Team workspace", soon: true, visual: <TeamVisual />,
    text: "Clipping teams will be able to share projects and templates and work from one credit balance." },
  { title: "API for developers", soon: false, visual: <ApiVisual />,
    text: "The same public API this site runs on. Upload, get a credit quote, start a job and fetch ranked clips. Create API keys in your dashboard." },
];

export function TeamsSection() {
  return (
    <section aria-labelledby="teams-title" className="px-5">
      <SectionHead id="teams-title" icon="people" label="For clippers and developers" title={<>One setup for<br className="narrow:hidden" /> every game you clip</>}
        sub="Templates tuned per game, your own saved looks, and an API when you want to plug clipping into your own tools." />
      <div className="mx-auto grid max-w-[1180px] grid-cols-3 gap-6 mid:grid-cols-1 mid:max-w-[560px]">
        {CARDS.map((c) => (
          <article key={c.title} className="flex flex-col rounded-[24px] bg-white/[.04] p-7 ring-1 ring-white/[.06]">
            <div className="flex h-[220px] items-center justify-center" aria-hidden="true">{c.visual}</div>
            <h3 className="mt-6 flex flex-wrap items-center gap-2.5 text-[22px] font-semibold">{c.title}{c.soon && <ComingSoon />}</h3>
            <p className="mt-3 text-[16px] leading-relaxed text-white/60">{c.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
