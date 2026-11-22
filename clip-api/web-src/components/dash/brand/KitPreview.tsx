"use client";
// The brand kit's live preview: a frame of the chosen shape playing an approved gaming clip in the kit's layout,
// with the kit's caption style and hook drawn over it.
import { useCallback, useEffect, useRef, useState } from "react";
import { Icon, IconName } from "../Icon";
import { Pills } from "@/components/ui/Pill";
import { PhonePreview } from "@/components/ui/PhonePreview";
import { mediaUrl, useMedia } from "@/lib/media";
import { kitPreviewId } from "./Pickers";
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
// The frame's width for each shape: 303 px upright beside the cards (335 px under them), wider as the shape widens.
const PREVIEW_WIDTH: Record<Shape, string> = { "9:16": "w-[303px] wide:w-[335px]", "4:5": "w-[340px]", "1:1": "w-[340px]", "16:9": "w-full max-w-[420px] wide:w-[420px]" };
const ratio = (s: string) => { const [w, h] = s.split(":").map(Number); return w > 0 && h > 0 ? w / h : 9 / 16; };

// The footage behind the preview: the engine's own render of the kit's layout at the shape being looked at
// (public/media/kit-preview, made by scripts/make_kit_previews.py with captions and the hook off, which this
// preview draws on top). A layout the API does not offer at a shape falls back to that shape's automatic layout.
function Panels({ kit, shape, onCredit }: { kit: Kit; shape: string; onCredit?: (credit: string | null) => void }) {
  const items = useMedia("kit-preview")?.items || [];
  const item = items.find((i) => i.id === kitPreviewId(shape, kit.layout, kit.camera)) || items.find((i) => i.id === kitPreviewId(shape, "auto")) || null;
  useEffect(() => { onCredit?.(item?.credit || null); }, [item?.credit]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!item) return <span className="absolute inset-0 grid place-items-center bg-control text-[13px] text-fg-3">Preview clip unavailable</span>;
  return (
    <span className="absolute inset-0 overflow-hidden bg-black">
      <video key={item.id} muted loop autoPlay playsInline preload="metadata" poster={item.poster ? mediaUrl("kit-preview", item.poster) : undefined} aria-hidden="true"
        className="absolute inset-0 h-full w-full object-cover"><source src={mediaUrl("kit-preview", item.src)} type="video/mp4" /></video>
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

const SOCIAL: IconName[] = ["like", "send", "bookmark"];
function Social() {
  return <>
    <span className="absolute bottom-[16%] right-[3%] grid justify-items-center gap-[calc(3*var(--u))] text-white">
      <span className="aspect-square w-[calc(11*var(--u))] rounded-full border-[2px] border-solid border-white bg-lime" />
      {SOCIAL.map((i) => <span key={i} className="grid justify-items-center gap-[3px] [filter:drop-shadow(0_1px_2px_#000)]"><Icon name={i} size={22} /><span className="h-[calc(1.6*var(--u))] w-[calc(6*var(--u))] rounded-full bg-[rgba(255,255,255,.7)]" /></span>)}
    </span>
    <span className="absolute bottom-[4%] left-[5%] right-[22%] grid gap-[calc(1*var(--u))] font-sans text-white [text-shadow:0_1px_2px_#000]">
      <span className="h-[calc(3*var(--u))] w-[42%] rounded-full bg-[rgba(255,255,255,.85)]" />
      <span className="h-[calc(2.4*var(--u))] w-[78%] rounded-full bg-[rgba(255,255,255,.6)]" />
      <span className="flex items-center gap-1 opacity-85"><Icon name="music" size={12} /><span className="h-[calc(2*var(--u))] w-[34%] rounded-full bg-[rgba(255,255,255,.5)]" /></span>
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
        className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-pill border-0 bg-control px-4 font-sans text-[14px] text-text transition-colors duration-base hover:bg-control-hover aria-expanded:bg-control-hover">
        Show in preview<Icon name="chevron" size={16} className="text-muted" /></button>
      {open && <fieldset className="absolute bottom-[calc(100%+8px)] left-1/2 z-[60] m-0 grid w-[240px] -translate-x-1/2 gap-1 rounded-[14px] border-0 bg-control p-3 shadow-pop">
        <legend className="sr-only">Show in preview</legend>
        {SHOW_NAMES.map(([k, name]) => (
          <label key={k} className="m-0 flex min-h-[36px] cursor-pointer items-center gap-3 rounded-8 px-1 text-[14px] font-normal text-text">
            <input type="checkbox" checked={show[k]} onChange={(e) => onChange({ ...show, [k]: e.target.checked })} />{name}
            {k === "social" && <span className="ml-auto text-[12px] text-fg-3">Not on 16:9</span>}</label>))}
      </fieldset>}
    </div>
  );
}

export function KitPreview({ kit, shape, onShape }: { kit: Kit; shape: Shape; onShape: (s: Shape) => void }) {
  const [show, setShow] = useState<Show>({ captions: true, hook: true, social: true, safe: false });
  const [credit, setCredit] = useState<string | null>(null);
  const r = ratio(shape), vertical = r < 1, wide = shape === "16:9";
  const split = shape !== "16:9" && (hasPanels(kit.layout) || kit.layout === "auto");
  const top = kit.camera || (kit.layout === "screen_first" ? "bottom" : "top"), seam = split ? (kit.split_ratio ?? (top === "top" ? 0.38 : 0.6)) * 100 : null;
  const hookLine = HOOK_LINES[kit.hook_style] || tidy(kit.hook_style);

  // Measured from the reference: ratio pills 75 x 32 with 8 px between, the frame 303 px wide 22 px below them.
  return (
    <div className="grid justify-items-center gap-[22px]">
      <div className="flex items-center gap-3">
        <Pills label="Preview shape" className="!flex-nowrap" value={shape} onChange={onShape} options={SHAPES.map((s) => ({ value: s, label: s }))} />
        <span title={`Preview only. Clips made with this kit are cut to ${kit.aspect}.`} className="grid h-8 w-6 place-items-center text-fg-2"><Icon name="info" size={17} />
          <span className="sr-only">Preview only. Clips made with this kit are cut to {kit.aspect}.</span></span>
      </div>
      <div id="kit-preview" className={`[container-type:inline-size] ${PREVIEW_WIDTH[shape]} max-w-full`}
        style={{ "--u": `${UNIT[shape]}cqw` } as React.CSSProperties}>
        <PhonePreview ratio={shape} label={`Preview at ${shape}`}>
          <Panels kit={kit} shape={shape} onCredit={setCredit} />
          {show.hook && kit.hook_overlay && <span className={`absolute grid place-items-center ${wide ? "inset-x-[24%] top-[8%]" : shape === "9:16" ? "inset-x-[10%] top-[9%]" : "inset-x-[14%] top-[7%]"}`}>
            <span className="rounded-[calc(1.6*var(--u))] bg-white px-[calc(3*var(--u))] py-[calc(1.4*var(--u))] text-center font-sans text-[calc(4.6*var(--u))] font-bold leading-[1.15] text-black shadow-[0_2px_8px_rgba(0,0,0,.35)]">{hookLine}</span></span>}
          {show.captions && kit.captions && <Caption kit={kit} seam={seam} />}
          {show.social && !wide && <Social />}
          {show.safe && <span aria-hidden="true" className="absolute bottom-[18%] left-[5%] right-[16%] top-[10%] rounded-[calc(2*var(--u))] border-[1.5px] border-dashed border-[rgba(60,240,255,.9)]" />}
        </PhonePreview>
      </div>
      <div className="grid justify-items-center gap-2">
        <ShowMenu show={show} onChange={setShow} />
        {credit && <p className="m-0 text-[11.5px] text-fg-3">{credit}</p>}
      </div>
    </div>
  );
}
