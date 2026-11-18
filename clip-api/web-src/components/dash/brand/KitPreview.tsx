"use client";
// The brand kit's live preview: a phone (or a frame of the chosen shape) showing the kit's layout, caption style
// and hook over a gameplay frame. Everything in it is drawn here in CSS, our own artwork: no footage, no game art.
import { useCallback, useRef, useState } from "react";
import { Icon, IconName } from "../Icon";
import { Tabs } from "../Tabs";
import { CAPTION, HOOK_LINES } from "../setup/Styles";
import { useDismiss } from "../shell/useDismiss";
import type { Kit } from "@/lib/brandkit";
import { hasPanels, tidy } from "@/lib/templates";

export const SHAPES = ["9:16", "16:9", "1:1", "4:5"] as const;
export type Shape = (typeof SHAPES)[number];
type Show = { captions: boolean; hook: boolean; social: boolean; safe: boolean };
const SHOW_NAMES: [keyof Show, string][] = [["captions", "Captions"], ["hook", "Hook"], ["social", "App buttons"], ["safe", "Safe zones"]];
// Overlay text is sized to the frame's width, scaled per shape so a wide frame doesn't get giant captions.
const UNIT: Record<Shape, number> = { "9:16": 1, "4:5": 0.8, "1:1": 0.72, "16:9": 0.56 };
const ratio = (s: string) => { const [w, h] = s.split(":").map(Number); return w > 0 && h > 0 ? w / h : 9 / 16; };

// A city at dusk, a road and a HUD: reads as open-world gameplay at a glance.
function Gameplay() {
  return (
    <span className="absolute inset-0 overflow-hidden bg-[linear-gradient(180deg,#ffb36b_0%,#f0708a_34%,#5b3a7a_56%,#1d1830_57%)]">
      <span className="absolute inset-x-0 bottom-[43%] h-[22%] [background:linear-gradient(90deg,#241c38_0_7%,transparent_7%_9%,#2c2244_9%_15%,transparent_15%_18%,#1f1932_18%_30%,transparent_30%_33%,#2a2142_33%_38%,transparent_38%_44%,#221b36_44%_57%,transparent_57%_60%,#2d2346_60%_66%,transparent_66%_70%,#1f1932_70%_84%,transparent_84%_87%,#2a2142_87%_100%)]" />
      <span className="absolute inset-x-0 bottom-[43%] h-[12%] [background:linear-gradient(90deg,#191428_0_12%,transparent_12%_22%,#191428_22%_26%,transparent_26%_48%,#191428_48%_55%,transparent_55%_74%,#191428_74%_80%,transparent_80%)]" />
      <span className="absolute bottom-0 left-[-20%] right-[-20%] h-[43%] bg-[#2b2b35] [clip-path:polygon(42%_0,58%_0,100%_100%,0_100%)]" />
      <span className="absolute bottom-0 left-1/2 h-[43%] w-[3%] -translate-x-1/2 [background:repeating-linear-gradient(180deg,#f5d76e_0_12%,transparent_12%_24%)] [clip-path:polygon(40%_0,60%_0,100%_100%,0_100%)]" />
      <span className="absolute bottom-[9%] left-1/2 h-[13%] w-[22%] -translate-x-1/2 rounded-t-[30%] rounded-b-[12%] bg-[linear-gradient(180deg,#e8384f,#9b1530)] shadow-[0_4px_10px_rgba(0,0,0,.5)]">
        <span className="absolute left-[14%] right-[14%] top-[14%] h-[30%] rounded-[30%] bg-[rgba(30,30,40,.85)]" />
        <span className="absolute bottom-[12%] left-[8%] h-[14%] w-[16%] rounded-full bg-[#ffd36b]" /><span className="absolute bottom-[12%] right-[8%] h-[14%] w-[16%] rounded-full bg-[#ffd36b]" />
      </span>
      <span className="absolute right-[4%] top-[4%] font-sans text-[calc(3.2*var(--u))] tracking-[.1em] text-white [text-shadow:0_1px_2px_#000]">★★★☆☆</span>
    </span>
  );
}

// A streamer at a desk, lit by an RGB strip.
function Camera() {
  return (
    <span className="absolute inset-0 overflow-hidden bg-[linear-gradient(160deg,#2b1f45,#120e1d)]">
      <span className="absolute inset-x-0 top-[18%] h-[4%] bg-[linear-gradient(90deg,#ff3cac,#784ba0,#2b86c5,#3cf0ff)] opacity-70 blur-[2px]" />
      <span className="absolute bottom-[-6%] left-1/2 h-[46%] w-[58%] -translate-x-1/2 rounded-t-[50%] bg-[#40345c]" />
      <span className="absolute bottom-[34%] left-1/2 aspect-square h-[36%] -translate-x-1/2 rounded-full bg-[#8a7a9c]" />
      <span className="absolute bottom-[50%] left-1/2 h-[10%] w-[34%] -translate-x-1/2 rounded-t-full border-[3px] border-b-0 border-solid border-[#1a1426]" />
      <span className="absolute bottom-[8%] right-[18%] h-[30%] w-[5%] rounded-full bg-[#15111f]" />
    </span>
  );
}

function Panels({ kit, shape }: { kit: Kit; shape: string }) {
  const wide = shape === "16:9", layout = kit.layout;
  if (layout === "fit" || layout === "classic") return (
    <span className="absolute inset-0 overflow-hidden bg-black">
      {layout === "classic" && <span className="absolute inset-[-10%] scale-110 opacity-70 blur-[10px]"><Gameplay /></span>}
      <span className="absolute inset-x-0 top-1/2 aspect-video -translate-y-1/2"><Gameplay /></span>
    </span>
  );
  const split = !wide && (hasPanels(layout) || layout === "auto");
  if (!split) return (
    <span className="absolute inset-0"><Gameplay />
      {(layout === "pip" || (wide && layout === "auto")) && <span className="absolute bottom-[6%] right-[5%] aspect-video w-[30%] overflow-hidden rounded-[6px] ring-1 ring-[rgba(255,255,255,.6)]"><Camera /></span>}
    </span>
  );
  const top = kit.camera || (layout === "screen_first" ? "bottom" : "top"), share = (kit.split_ratio ?? (top === "top" ? 0.38 : 0.6)) * 100;
  return (
    <span className="absolute inset-0 grid" style={{ gridTemplateRows: `${share}% 1fr` }}>
      <span className="relative">{top === "top" ? <Camera /> : <Gameplay />}</span>
      <span className="relative">{top === "top" ? <Gameplay /> : <Camera />}</span>
    </span>
  );
}

function Caption({ kit, seam }: { kit: Kit; seam: number | null }) {
  const c = CAPTION[kit.caption_style] || CAPTION.clean, [a, b] = c.text || ["no way", "he hit that"];
  const [hot, ...rest] = b.split(" ");
  const at = kit.caption_position === "center" ? 50 : kit.caption_position === "lower" || seam === null ? 72 : seam;
  // The accent colour is the impact style's keyword colour; other styles keep their own.
  const accent = kit.caption_style === "impact" && kit.caption_accent ? { color: kit.caption_accent } : undefined;
  return (
    <span className="absolute inset-x-[6%] grid -translate-y-1/2 place-items-center text-center" style={{ top: `${at}%` }}>
      <span className={`font-sans text-[calc(6.4*var(--u))] leading-[1.1] ${c.box}`}><span>{a} <span className={c.hot} style={accent}>{hot}</span> {rest.join(" ")}</span></span>
    </span>
  );
}

const SOCIAL: [IconName, string][] = [["like", "48.2K"], ["send", "1.9K"], ["bookmark", "6.1K"]];
function Social() {
  return <>
    <span className="absolute bottom-[16%] right-[3%] grid justify-items-center gap-[calc(3*var(--u))] text-white">
      <span className="aspect-square w-[calc(11*var(--u))] rounded-full border-[2px] border-solid border-white bg-[linear-gradient(135deg,theme(colors.lime),theme(colors.cyan))]" />
      {SOCIAL.map(([i, n]) => <span key={i} className="grid justify-items-center gap-[1px] font-sans text-[calc(3*var(--u))] font-semibold [text-shadow:0_1px_2px_#000]"><Icon name={i} size={22} />{n}</span>)}
    </span>
    <span className="absolute bottom-[4%] left-[5%] right-[22%] grid gap-[calc(1*var(--u))] font-sans text-white [text-shadow:0_1px_2px_#000]">
      <b className="text-[calc(4*var(--u))]">@yourchannel</b>
      <span className="text-[calc(3.4*var(--u))]">Clutch of the night #gaming #clips</span>
      <span className="flex items-center gap-1 text-[calc(3*var(--u))] opacity-85"><Icon name="music" size={12} />Original sound</span>
    </span>
  </>;
}

// "Show in preview": what the preview draws over the frame. Opens upward, centred under the preview.
function ShowMenu({ show, onChange }: { show: Show; onChange: (s: Show) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, box, btn);
  return (
    <div ref={box} className="relative">
      <button ref={btn} type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="inline-flex min-h-[38px] cursor-pointer items-center gap-2 rounded-full border border-solid border-line-soft bg-transparent px-4 font-sans text-[14px] text-text hover:bg-chip aria-expanded:bg-chip">
        <Icon name="eye" size={17} className="text-muted" />Show in preview<Icon name="chevron" size={16} className="text-muted" /></button>
      {open && <fieldset className="absolute bottom-[calc(100%+8px)] left-1/2 z-[60] m-0 grid w-[240px] -translate-x-1/2 gap-1 rounded-16 border border-solid border-line bg-card-2 p-3 shadow-pop">
        <legend className="sr-only">Show in preview</legend>
        {SHOW_NAMES.map(([k, name]) => (
          <label key={k} className="m-0 flex min-h-[36px] cursor-pointer items-center gap-3 rounded-8 px-1 text-[14px] font-normal text-text">
            <input type="checkbox" checked={show[k]} onChange={(e) => onChange({ ...show, [k]: e.target.checked })} />{name}
            {k === "social" && <span className="ml-auto text-[12px] text-fg-3">Upright shapes</span>}</label>))}
      </fieldset>}
    </div>
  );
}

export function KitPreview({ kit, shape, onShape }: { kit: Kit; shape: Shape; onShape: (s: Shape) => void }) {
  const [show, setShow] = useState<Show>({ captions: true, hook: true, social: true, safe: false });
  const r = ratio(shape), phone = shape === "9:16", vertical = r < 1;
  const split = shape !== "16:9" && (hasPanels(kit.layout) || kit.layout === "auto");
  const top = kit.camera || (kit.layout === "screen_first" ? "bottom" : "top"), seam = split ? (kit.split_ratio ?? (top === "top" ? 0.38 : 0.6)) * 100 : null;
  const hookLine = HOOK_LINES[kit.hook_style] || tidy(kit.hook_style);

  return (
    <div className="grid justify-items-center gap-4">
      <div className="flex items-center gap-2">
        <Tabs seg label="Preview shape" panel="kit-preview" value={shape} onChange={onShape} tabs={SHAPES.map((s) => [s, s])} />
        <span title={`Preview only. Clips made with this kit are cut to ${kit.aspect}.`} className="grid h-8 w-8 place-items-center text-muted"><Icon name="info" size={18} />
          <span className="sr-only">Preview only. Clips made with this kit are cut to {kit.aspect}.</span></span>
      </div>
      <div id="kit-preview" role="tabpanel" aria-label={`Preview at ${shape}`} className="grid h-[min(64vh,600px)] min-h-[360px] w-full place-items-center narrow:h-[440px] narrow:min-h-0">
        <div className={`relative overflow-hidden bg-black [container-type:inline-size] ${phone ? "rounded-[34px] border-[7px] border-solid border-[#1c1c1c] shadow-[0_0_0_1px_rgba(255,255,255,.12),0_30px_60px_rgba(0,0,0,.6)]"
          : "rounded-16 shadow-[0_0_0_1px_rgba(255,255,255,.12),0_30px_60px_rgba(0,0,0,.6)]"}`}
          style={{ "--u": `${UNIT[shape]}cqw`, aspectRatio: r, height: vertical ? "100%" : "auto", width: vertical ? "auto" : "100%", maxWidth: "100%", maxHeight: "100%" } as React.CSSProperties}>
          <Panels kit={kit} shape={shape} />
          {show.hook && kit.hook_overlay && <span className="absolute inset-x-[10%] top-[9%] grid place-items-center">
            <span className="rounded-[calc(1.6*var(--u))] bg-white px-[calc(3*var(--u))] py-[calc(1.4*var(--u))] text-center font-sans text-[calc(4.6*var(--u))] font-bold leading-[1.15] text-black shadow-[0_2px_8px_rgba(0,0,0,.35)]">{hookLine}</span></span>}
          {show.captions && kit.captions && <Caption kit={kit} seam={seam} />}
          {show.social && vertical && <Social />}
          {show.safe && <span aria-hidden="true" className="absolute bottom-[18%] left-[5%] right-[16%] top-[10%] rounded-[calc(2*var(--u))] border-[1.5px] border-dashed border-[rgba(60,240,255,.9)]" />}
          {phone && <span aria-hidden="true" className="absolute left-1/2 top-[1.4%] h-[2.4%] w-[26%] -translate-x-1/2 rounded-full bg-[#0a0a0a]" />}
        </div>
      </div>
      <ShowMenu show={show} onChange={setShow} />
    </div>
  );
}
