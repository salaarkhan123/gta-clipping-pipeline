import { ComingSoonBadge } from "../../ComingSoonBadge";

// A carousel card for something not built yet: the badge, what it will do, and an outline drawing. No output is
// drawn and nothing is clickable, so nothing on it looks like it works today.
function SoonCard({ title, text, sketch }: { title: string; text: string; sketch: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center gap-12 narrow:flex-col narrow:gap-6">
      <div className="flex max-w-[380px] flex-col items-start gap-4 narrow:items-center narrow:text-center">
        <ComingSoonBadge />
        <h3 className="text-h3 text-fg">{title}</h3>
        <p className="text-body-lg text-fg-2">{text}</p>
      </div>
      <div className="opacity-70" aria-hidden="true">{sketch}</div>
    </div>
  );
}

const dashed = "rounded-[14px] border-2 border-dashed border-white/25";

export function BRollSoon() {
  return <SoonCard title="AI B-roll" text="ClutchClips will add cutaway shots that match what you're talking about, placed over the slower parts of a clip."
    sketch={<div className="flex flex-col items-center gap-4">
      <div className={`${dashed} aspect-[9/16] h-[260px] narrow:h-[160px]`} />
      <div className="flex gap-2">{[64, 40, 88, 52].map((w, i) => <span key={i} className={`${dashed} h-10 rounded-[8px]`} style={{ width: w }} />)}</div>
    </div>} />;
}

export function VoiceSoon() {
  return <SoonCard title="Voiced hooks" text="ClutchClips will be able to read your hook line out loud in a voice you pick, so the opening works with the sound on."
    sketch={<div className="flex flex-col items-center gap-4">
      <div className={`${dashed} flex h-[150px] w-[300px] flex-col gap-3 p-4 narrow:h-[110px] narrow:w-[240px]`}>
        <span className="h-3 w-24 rounded-full bg-white/15" /><span className="h-9 rounded-[8px] bg-white/10" /><span className="h-3 w-40 rounded-full bg-white/15" />
      </div>
      <div className="flex h-10 items-center gap-1">{Array.from({ length: 28 }, (_, i) => <span key={i} className="w-1 rounded-full border border-dashed border-white/30" style={{ height: 8 + ((i * 7) % 26) }} />)}</div>
    </div>} />;
}
