"use client";
// The layout popover: the clip's shape, the layout (or "AI picks", the API's `auto`), the camera side for a
// two-panel layout, and where chat goes. Only what GET /v1/options lists can be picked; layouts our renderer
// has but this API does not list yet, and the parts not built, carry the Coming soon mark.
import { useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { allows, Listed } from "@/lib/options";
import { hasPanels, layoutChoices, Look } from "@/lib/templates";
import { Icon } from "../Icon";
import { LookSketch } from "../LookSketch";
import { LABEL, Popover, Tile } from "./parts";

// Our names for the layouts. A layout id not named here is shown tidied up.
export const LAYOUT_NAMES: Record<string, string> = { auto: "AI picks", full: "Fill", fill: "Fill", fit: "Fit", split2: "Split", split: "Split",
  screen_first: "Gameplay first", pip: "Corner cam", gameplay_a: "Cam over game", gameplay_b: "Big cam over game", classic: "Classic", trio: "Three", grid4: "Four", ots: "Over the shoulder" };
// Layouts that are planned for this screen but not offered by the API yet: shown, never picked.
const PLANNED = ["trio", "grid4"];
const CHAT: [string, string][] = [["none", "Not shown"], ["top-right", "Top right"], ["top-left", "Top left"], ["top-center", "Top centre"],
  ["bottom-right", "Bottom right"], ["bottom-left", "Bottom left"]];
const CROPS = ["Original", "4:3", "1:1"];
const ratio = (a: string) => { const [w, h] = a.split(":").map(Number); return w > 0 && h > 0 ? w / h : 9 / 16; };
export const layoutLabel = (id: string) => LAYOUT_NAMES[id] || id.replace(/[_-]+/g, " ").replace(/^./, (c) => c.toUpperCase());

// A layout's picture: the owner's still once it is in /media/setup/, our own sketch until then.
function LayoutArt({ id, aspect, look }: { id: string; aspect: string; look: Look }) {
  const [still, setStill] = useState(true);
  return still && id !== "auto"
    ? <img src={`/media/setup/layout-${id}.webp`} alt="" className="h-full w-full object-cover" onError={() => setStill(false)} />
    : id === "auto" ? <span className="grid place-items-center gap-1 text-[12px] font-medium text-fg-2"><Icon name="sparkle" size={22} /></span>
    : <span className="grid h-full w-full place-items-center [&_.mock]:h-[86%]"><LookSketch aspect={aspect} layout={id} captions={false} camera={look.camera} split={look.split_ratio} /></span>;
}

export function LayoutPicker({ listed, look, onLook, setAspect, chat, onChat }: { listed: Listed; look: Look; onLook: (c: Partial<Look>) => void;
  setAspect: (a: string) => void; chat: string; onChat: (v: string) => void }) {
  const aspects: string[] = listed.aspect?.values || [look.aspect];
  const offered = layoutChoices(listed, look.aspect, look.layout).filter((l) => l !== "auto");
  const planned = PLANNED.filter((l) => !offered.includes(l));
  const setLayout = (layout: string) => onLook({ layout, ...(hasPanels(layout) ? {} : { camera: null, split_ratio: null }) });
  const tall = ratio(look.aspect) < 1;
  const art = tall ? "aspect-[9/16] w-full" : "aspect-video w-full";
  return (
    <Popover wide label="Shape and layout" button={<><Icon name="phone" size={18} className="text-muted" /><span className="text-muted">Layout</span>
      <span>{look.aspect}, {layoutLabel(look.layout)}</span><Icon name="chevron" size={16} className="text-muted" /></>}>
      <section className="grid gap-3" aria-label="Shape">
        <h3 className={`m-0 ${LABEL}`}>Shape</h3>
        <div className="flex flex-wrap items-end gap-3">
          {aspects.map((a) => <Tile key={a} name={a} on={look.aspect === a} onClick={() => setAspect(a)} className="h-[76px]" >
            <span className="block h-[64px] rounded-[6px] border-2 border-solid border-[rgba(255,255,255,.5)]" style={{ aspectRatio: ratio(a) }} /></Tile>)}
        </div>
      </section>
      <section className="grid gap-3" aria-label="Layout">
        <h3 className={`m-0 ${LABEL}`}>Layout</h3>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(76px,1fr))] gap-3">
          <Tile name="AI picks" on={look.layout === "auto"} onClick={() => setLayout("auto")} className={art}><LayoutArt id="auto" aspect={look.aspect} look={look} /></Tile>
          {offered.map((l) => <Tile key={l} name={layoutLabel(l)} on={look.layout === l} onClick={() => setLayout(l)} className={art}><LayoutArt id={l} aspect={look.aspect} look={look} /></Tile>)}
          {planned.map((l) => <Tile key={l} name={layoutLabel(l)} soon className={art}><LayoutArt id={l} aspect={look.aspect} look={look} /></Tile>)}
        </div>
        <p className="m-0 flex flex-wrap items-center gap-2 text-[12.5px] text-muted">AI picks chooses the layout for each clip. Letting it choose from a set you pick <ComingSoonBadge short /></p>
      </section>
      {hasPanels(look.layout) && "camera" in listed && <label className="m-0 grid gap-2 text-[13px] font-normal text-muted">Facecam panel
        <select value={look.camera || ""} onChange={(e) => onLook({ camera: e.target.value || null, split_ratio: null })} className="rounded-full">
          {listed.camera?.nullable !== false && <option value="">Where the layout puts it</option>}
          {(listed.camera?.values || ["top", "bottom"]).map((c: string) => <option key={c} value={c}>{c === "top" ? "On top" : "At the bottom"}</option>)}</select></label>}
      {"chat_region" in listed && <label className="m-0 grid gap-2 text-[13px] font-normal text-muted">Stream chat on screen
        <select value={chat} onChange={(e) => onChat(e.target.value)} className="rounded-full">
          {CHAT.filter(([v]) => allows(listed, "chat_region", v)).map(([v, name]) => <option key={v} value={v}>{name}</option>)}</select></label>}
      <section className="grid gap-3" aria-label="Fit crop">
        <h3 className={`m-0 flex items-center gap-2 ${LABEL}`}>Fit layout crop <ComingSoonBadge short /></h3>
        <div className="flex gap-3">{CROPS.map((c) => <Tile key={c} name={c} soon className="h-[64px] w-[48px]"><span className="block h-[60%] w-[80%] rounded-[4px] bg-[rgba(255,255,255,.2)]" /></Tile>)}</div>
      </section>
    </Popover>
  );
}
