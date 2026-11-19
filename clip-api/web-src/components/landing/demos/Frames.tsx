"use client";

// Stand-ins for footage, drawn until the media pipeline delivers a section (./Footage.tsx): a dark gradient with a
// label, never a real video.

export type Game = "gta" | "valorant" | "fortnite" | "apex" | "lol" | "cs2" | "minecraft" | "rust";
const SKY: Record<Game, [string, string, string]> = {
  gta: ["#1b2340", "#c4643a", "#24262d"],
  valorant: ["#24101a", "#b8434f", "#1d1a22"],
  fortnite: ["#14205a", "#3f8fd8", "#1c2a3a"],
  apex: ["#2a1a14", "#b5552f", "#26201c"],
  lol: ["#0c2328", "#2b9a80", "#16231f"],
  cs2: ["#1e1c16", "#b08e45", "#22211c"],
  minecraft: ["#123049", "#4d9bd1", "#24351f"],
  rust: ["#1f1b18", "#8a6a45", "#211d1a"],
};
export const GAME_LABEL: Record<Game, string> = { gta: "GTA 5", valorant: "Valorant", fortnite: "Fortnite", apex: "Apex Legends",
  lol: "League of Legends", cs2: "Counter-Strike 2", minecraft: "Minecraft", rust: "Rust" };

// Gameplay: sky, horizon and ground in the game's colours, a minimap and a health bar so it reads as a game.
export function Gameplay({ game = "gta", label = true, hud = true, className = "" }: {
  game?: Game; label?: boolean | string; hud?: boolean; className?: string }) {
  const [sky, glow, ground] = SKY[game];
  return (
    <span className={`absolute inset-0 overflow-hidden ${className}`} aria-hidden="true"
      style={{ background: `radial-gradient(60% 40% at 62% 52%, ${glow}88, transparent 70%), linear-gradient(180deg, ${sky} 0%, ${glow}55 50%, ${ground} 51%, #0b0c0f 100%)` }}>
      <span className="absolute left-[8%] top-[46%] h-[14%] w-[22%] rounded-[3px] opacity-60" style={{ background: `linear-gradient(180deg, ${ground}, #0b0c0f)` }} />
      <span className="absolute right-[14%] top-[40%] h-[20%] w-[12%] rounded-[3px] opacity-50" style={{ background: `linear-gradient(180deg, ${ground}, #0b0c0f)` }} />
      {hud && <><span className="absolute bottom-[7%] right-[4%] aspect-square w-[13%] rounded-[6px] border border-white/25 bg-black/30" />
        <span className="absolute bottom-[8%] left-[4%] h-[3%] w-[18%] overflow-hidden rounded-full bg-black/40"><span className="block h-full w-2/3 bg-white/60" /></span></>}
      {label && <span className="absolute left-2 top-2 rounded-[6px] bg-black/45 px-1.5 py-0.5 text-[10px] font-medium leading-tight text-white/70">
        {typeof label === "string" ? label : `${GAME_LABEL[game]} gameplay`}</span>}
    </span>
  );
}

// A facecam: head and shoulders in silhouette.
export function Cam({ label = false, className = "" }: { label?: boolean; className?: string }) {
  return (
    <span className={`absolute inset-0 overflow-hidden ${className}`} aria-hidden="true"
      style={{ background: "radial-gradient(70% 60% at 50% 30%, #3a4a66, #161b26 75%)" }}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMax meet" className="absolute inset-x-0 bottom-0 mx-auto h-[86%] w-full">
        <circle cx="50" cy="42" r="17" fill="#6b7a96" />
        <path d="M18 100c0-20 14-34 32-34s32 14 32 34z" fill="#56637d" />
        <rect x="26" y="30" width="48" height="7" rx="3.5" fill="#2a3242" />
      </svg>
      {label && <span className="absolute left-1.5 top-1.5 rounded-[5px] bg-black/45 px-1.5 py-0.5 text-[10px] font-medium text-white/70">Facecam</span>}
    </span>
  );
}

// A finished vertical clip: camera panel over gameplay, a third of the height ("Split in two", layouts.py split2).
export function SplitClip({ game = "gta", camShare = 33, className = "" }: { game?: Game; camShare?: number; className?: string }) {
  return (
    <span className={`absolute inset-0 grid ${className}`} style={{ gridTemplateRows: `${camShare}% 1fr` }}>
      <span className="relative"><Cam /></span>
      <span className="relative border-t border-black/60"><Gameplay game={game} label={false} hud={false} /></span>
    </span>
  );
}
