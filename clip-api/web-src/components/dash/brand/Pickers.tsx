"use client";
// The brand kit's compact rows and the pickers they open. A style row is a title, one sentence and a small
// preview of the current choice; pressing it opens a picker: the choices as a two-column grid on the left, a
// large preview and the controls that style really has on the right, then Reset, Save as new and Save.
// A layout row is one shape with the layout it uses; its picker shows the layouts as pictures with a tick.
import { useRef } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Dropdown } from "@/components/ui/Dropdown";
import { hookCatalogueOf, hookToneDescription, hookToneLabel } from "@/lib/hookStyles";
import type { Kit } from "@/lib/brandkit";
import type { Listed } from "@/lib/options";
import { DEFAULT_PANELS, hasPanels, layoutChoices, layoutName, tidy } from "@/lib/templates";
import { mediaUrl, useMedia } from "@/lib/media";
import { Icon } from "../Icon";
import { LookSketch } from "../LookSketch";
import { CAPTION, captionName, HOOK_LINES } from "../setup/Styles";
import { Switch } from "../setup/parts";

const LIME = "#b8ff3c";
const POSITIONS: Record<string, string> = { auto: "Automatic", seam: "Between panels", lower: "Lower third", center: "Centre" };
const HOOK_BACKS = ["linear-gradient(170deg,#3a2a1f,#0f0d0c)", "linear-gradient(170deg,#1f2a3a,#0b0e13)", "linear-gradient(170deg,#2a1f3a,#0e0b13)", "linear-gradient(170deg,#1f3a2c,#0b130f)"];

// What the pickers' footers do: the page's own Save as new kit and Save changes. `baseline` is the kit as last
// saved (a new kit's starting look until then): Reset puts a picker's settings back to it.
export type KitActions = { saveNew: () => void; save: () => void; canSave: boolean; busy: boolean; baseline: Kit };
type Props = { kit: Kit; listed: Listed; set: (patch: Partial<Kit>) => void; actions: KitActions };
// The caption and hook rows read and write only these, so job setup can use them for one job's look.
// Without `actions` (job setup: nothing to save, the job takes what is on screen) the picker ends in Done.
// `title` and `hint` let the row sit under a setting that already has its own name and switch.
export type StyleLook = Pick<Kit, "captions" | "caption_style" | "caption_position" | "caption_accent" | "caption_emoji" | "censor" | "hook_overlay" | "hook_style">;
type StyleProps = { kit: StyleLook; listed: Listed; set: (patch: Partial<StyleLook>) => void; actions?: KitActions; title?: string; hint?: string };

const FIELD = "h-[38px] rounded-8 border border-solid border-line bg-transparent font-sans text-[14px] text-text";
const ICON_TOGGLE = "grid h-9 w-9 cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-text transition-colors duration-base hover:bg-control-hover aria-pressed:bg-btn aria-pressed:text-btn-ink";

function CaptionSample({ style, accent, size }: { style: string; accent?: string | null; size: string }) {
  const c = CAPTION[style] || CAPTION.clean, [a, b] = c.text || ["no way", "he hit that"], [hot, ...rest] = b.split(" ");
  return (
    <span className={`grid place-items-center px-2 text-center font-sans leading-[1.1] ${size} ${c.box}`}>
      <span>{a} <span className={c.hot} style={style === "impact" && accent ? { color: accent } : undefined}>{hot}</span> {rest.join(" ")}</span>
    </span>
  );
}

const HookSample = ({ tone, size }: { tone: string; size: string }) => (
  <span className={`rounded-[4px] bg-white text-center font-sans font-bold leading-[1.15] text-black ${size}`}>{HOOK_LINES[tone] || tidy(tone)}</span>
);

// One row of STYLES. `preview` is the 96 x 72 tile; `children` is the picker (given `close`), which opens under
// the row, lined up with the card's edge.
function StyleRow({ title, hint, off, preview, children }: { title: string; hint: string; off?: boolean; preview: React.ReactNode;
  children: (close: () => void) => React.ReactNode }) {
  const row = useRef<HTMLDivElement>(null);
  return (
    <div ref={row} className="flex min-h-[72px] items-center gap-4">
      <div className="grid min-w-0 flex-1 gap-[6px]">
        <span className="font-sans text-[15px] font-medium leading-[22px] text-text">{title}</span>
        <span className="font-sans text-[14px] leading-[20px] text-fg-2">{hint}</span>
      </div>
      <Dropdown label={`${title} style`} kind="dialog" anchor={row} dx={-30} panelClass="w-[663px] rounded-[24px] p-6 narrow:p-4"
        trigger={(t, open) => (
          <button {...t} type="button" aria-label={`${title}: change the style`} className="group flex cursor-pointer items-center gap-[10px] border-0 bg-transparent p-0 text-fg-2">
            <span className={`relative grid h-[72px] w-[96px] place-items-center overflow-hidden rounded-12 border border-solid border-line bg-panel transition-colors duration-base group-hover:border-line-strong ${off ? "opacity-50" : ""}`}>{preview}</span>
            <Icon name="chevron" size={18} className={`transition-transform duration-base ${open ? "rotate-180" : ""}`} />
          </button>)}>
        {children}
      </Dropdown>
    </div>
  );
}

// The picker's frame: choices left, preview and controls right, the three actions along the bottom right.
function Picker({ choices, preview, controls, onReset, actions, close }: { choices: React.ReactNode; preview: React.ReactNode; controls: React.ReactNode;
  onReset: () => void; actions?: KitActions; close: () => void }) {
  return (
    <div className="grid grid-cols-[244px_1px_minmax(0,1fr)] gap-x-7 narrow:grid-cols-1 narrow:gap-y-4">
      <div className="-mr-3 max-h-[409px] overflow-y-auto pr-3 narrow:max-h-[240px]">{choices}</div>
      <div className="bg-line narrow:hidden" aria-hidden="true" />
      <div className="grid min-h-[409px] grid-rows-[auto_auto_1fr_auto] gap-5 narrow:min-h-0">
        <div className="relative grid h-[180px] place-items-center overflow-hidden rounded-12 bg-raised narrow:h-[140px]">{preview}</div>
        <div className="grid gap-4">{controls}</div>
        <span />
        <div className="flex items-center justify-end gap-2">
          {actions ? <>
            <button type="button" data-item onClick={onReset} className="mr-auto h-[38px] cursor-pointer rounded-control border-0 bg-transparent px-4 font-sans text-[14px] text-fg-2 hover:text-text">Reset</button>
            <button type="button" data-item disabled={actions.busy} onClick={() => { close(); actions.saveNew(); }} className="btn ghost !h-[38px] !bg-control-hover !px-4 !text-[14px]">Save as new</button>
            <button type="button" data-item disabled={actions.busy || !actions.canSave} onClick={() => { close(); actions.save(); }} className="btn ghost !h-[38px] min-w-[96px] !bg-control-hover !px-4 !text-[14px]">Save</button>
          </> : <button type="button" data-item onClick={close} className="btn ghost !h-[38px] min-w-[96px] !bg-control-hover !px-4 !text-[14px]">Done</button>}
        </div>
      </div>
    </div>
  );
}

// A choice in a picker's grid: the picture, a white outline when chosen, its name under it.
function Choice({ name, on, onClick, tall, children, title }: { name: string; on: boolean; onClick: () => void; tall?: boolean; children: React.ReactNode; title?: string }) {
  return (
    <button type="button" data-item role="radio" aria-checked={on} title={title} onClick={onClick} className="group grid w-full cursor-pointer content-start gap-[10px] border-0 bg-transparent p-0 font-sans">
      <span className={`relative grid place-items-center overflow-hidden rounded-8 bg-raised transition-shadow duration-fast ${tall ? "aspect-[4/5]" : "h-[87px]"}
        ${on ? "shadow-[0_0_0_2px_theme(colors.text)]" : "group-hover:shadow-[0_0_0_1px_theme(colors.line-strong)]"}`}>{children}</span>
      <span className={`text-center text-[13px] leading-[1.3] ${on ? "text-text" : "text-fg-2"}`}>{name}</span>
    </button>
  );
}

const ControlRow = ({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) => (
  <div className="flex min-h-[38px] items-center justify-between gap-3">
    <span className="grid gap-[2px]"><span className="font-sans text-[14px] text-text">{label}</span>{hint && <span className="font-sans text-[12.5px] leading-[1.35] text-fg-2">{hint}</span>}</span>
    {children}
  </div>
);

export function CaptionRow({ kit, listed, set, actions, title = "Captions", hint = "Word-by-word captions, timed to the voice." }: StyleProps) {
  const has = (k: string) => k in listed;
  const styles: string[] = listed.caption_style?.values || [];
  const impact = kit.caption_style === "impact";
  const reset = () => { const b = actions?.baseline; if (b) set({ captions: b.captions, caption_style: b.caption_style, caption_position: b.caption_position, caption_accent: b.caption_accent, caption_emoji: b.caption_emoji, censor: b.censor }); };
  return (
    <StyleRow title={title} hint={hint} off={!kit.captions}
      preview={kit.captions ? <CaptionSample style={kit.caption_style} accent={kit.caption_accent} size="text-[11px]" /> : <span className="font-sans text-[13px] text-fg-2">Off</span>}>
      {(close) => <Picker close={close} actions={actions} onReset={reset}
        choices={<div role="radiogroup" aria-label="Caption style" className="grid grid-cols-2 gap-x-3 gap-y-4 p-[2px]">
          {styles.map((s) => <Choice key={s} name={captionName(s)} on={kit.captions && kit.caption_style === s} onClick={() => set({ captions: true, caption_style: s })}>
            <CaptionSample style={s} size="text-[15px]" /></Choice>)}
        </div>}
        preview={kit.captions ? <CaptionSample style={kit.caption_style} accent={kit.caption_accent} size="text-[26px]" /> : <span className="font-sans text-[14px] text-fg-2">Captions are off for this kit</span>}
        controls={<>
          {has("captions") && <ControlRow label="Show captions"><Switch on={kit.captions} label="Captions" onChange={(v) => set({ captions: v, ...(v ? {} : { caption_emoji: false }) })} /></ControlRow>}
          {kit.captions && <div className="flex flex-wrap items-center gap-2">
            {has("caption_position") && <label className="relative m-0" title={impact ? "Where the captions sit" : "Position can be set for the Impact style"}>
              <span className="sr-only">Position</span>
              <select value={kit.caption_position} disabled={!impact} onChange={(e) => set({ caption_position: e.target.value })}
                className={`${FIELD} w-[160px] cursor-pointer appearance-none !rounded-8 !bg-transparent !py-0 !pl-3 !pr-8 disabled:cursor-default disabled:opacity-45`}>
                {(listed.caption_position.values || []).map((v: string) => <option key={v} value={v}>{POSITIONS[v] || tidy(v)}</option>)}
              </select>
              <Icon name="chevron" size={16} className="pointer-events-none absolute right-[10px] top-[11px] text-fg-2" />
            </label>}
            {has("caption_accent") && <label title={impact ? "Keyword colour" : "The keyword colour applies to the Impact style"}
              className={`m-0 grid h-9 w-9 cursor-pointer place-items-center rounded-8 hover:bg-control-hover ${impact ? "" : "pointer-events-none opacity-45"}`}>
              <span className="sr-only">Keyword colour</span>
              <span className="relative block h-[22px] w-[22px] overflow-hidden rounded-full border border-solid border-line-strong" style={{ background: kit.caption_accent || LIME }}>
                <input type="color" aria-label="Keyword colour" disabled={!impact} value={kit.caption_accent || LIME} onChange={(e) => set({ caption_accent: e.target.value })}
                  className="absolute -inset-2 h-[200%] w-[200%] cursor-pointer !border-0 !p-0 opacity-0" /></span>
            </label>}
            {has("caption_emoji") && <button type="button" className={ICON_TOGGLE} aria-pressed={kit.caption_emoji} title="Emojis in captions" aria-label="Emojis in captions"
              onClick={() => set({ caption_emoji: !kit.caption_emoji })}><Icon name="smile" size={20} /></button>}
            {has("censor") && <button type="button" className={ICON_TOGGLE} aria-pressed={kit.censor} title="Censor swears" aria-label="Censor swears"
              onClick={() => set({ censor: !kit.censor })}><Icon name="shield" size={20} /></button>}
            {impact && kit.caption_accent !== null && <button type="button" className="h-9 cursor-pointer rounded-8 border-0 bg-transparent px-2 font-sans text-[13px] text-fg-2 hover:text-text"
              onClick={() => set({ caption_accent: null })}>Default colour</button>}
          </div>}
        </>} />}
    </StyleRow>
  );
}

export function HookRow({ kit, listed, set, actions, title = "Hook", hint = "A short opening line over the first seconds." }: StyleProps) {
  const tones: string[] = listed.hook_style?.values || [], entries = hookCatalogueOf(listed.hook_style?.catalogue);
  const reset = () => { const b = actions?.baseline; if (b) set({ hook_overlay: b.hook_overlay, hook_style: b.hook_style }); };
  const about = hookToneDescription(kit.hook_style, entries);
  return (
    <StyleRow title={title} hint={hint} off={!kit.hook_overlay}
      preview={kit.hook_overlay ? <span className="px-2"><HookSample tone={kit.hook_style} size="block px-[5px] py-[3px] text-[8px]" /></span> : <span className="font-sans text-[13px] text-fg-2">Off</span>}>
      {(close) => <Picker close={close} actions={actions} onReset={reset}
        choices={<div role="radiogroup" aria-label="Hook tone" className="grid grid-cols-2 gap-x-3 gap-y-4 p-[2px]">
          {tones.map((s, i) => <Choice key={s} tall name={hookToneLabel(s, entries)} title={hookToneDescription(s, entries)} on={kit.hook_overlay && kit.hook_style === s}
            onClick={() => set({ hook_overlay: true, hook_style: s })}>
            <span className="absolute inset-0" style={{ background: HOOK_BACKS[i % 4] }} />
            <img src={`/media/setup/hook-${(i % 3) + 2}.webp`} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            <span className="absolute inset-x-2 top-[14%] grid"><HookSample tone={s} size="px-1 py-[3px] text-[9.5px]" /></span>
          </Choice>)}
        </div>}
        preview={<>
          <img src="/media/setup/caption-bg.webp" alt="" className="absolute inset-0 h-full w-full object-cover opacity-70" onError={(e) => { e.currentTarget.style.display = "none"; }} />
          {kit.hook_overlay ? <span className="relative px-6"><HookSample tone={kit.hook_style} size="block px-3 py-[6px] text-[17px] shadow-[0_2px_8px_rgba(0,0,0,.35)]" /></span>
            : <span className="relative font-sans text-[14px] text-text">The hook is off for this kit</span>}
        </>}
        controls={<>
          <ControlRow label="Show the hook"><Switch on={kit.hook_overlay} label="Hook" onChange={(v) => set({ hook_overlay: v })} /></ControlRow>
          {kit.hook_overlay && <ControlRow label={`Tone: ${hookToneLabel(kit.hook_style, entries)}`} hint={about || "The AI writes the line for each clip in this tone."}><span /></ControlRow>}
        </>} />}
    </StyleRow>
  );
}

const RATIOS = ["9:16", "16:9", "1:1", "4:5"];
const RATIO_BOX: Record<string, string> = { "9:16": "h-[16px] w-[10px]", "16:9": "h-[10px] w-[16px]", "1:1": "h-[13px] w-[13px]", "4:5": "h-[15px] w-[12px]" };
// A layout's picture in its picker: a small frame of the shape itself.
const TILE: Record<string, string> = { "9:16": "h-[96px]", "4:5": "h-[80px]", "1:1": "h-[72px]", "16:9": "h-[63px]" };
const TILE_WIDTH: Record<string, string> = { "9:16": "w-[54px]", "4:5": "w-[64px]", "1:1": "w-[72px]", "16:9": "w-[112px]" };
const SHORT: Record<string, string> = { auto: "Auto", full: "Full", fill: "Full", fit: "Fit", split: "Split", split2: "Split", pip: "Inset", screen_first: "Screen",
  gameplay_a: "Game A", gameplay_b: "Game B", classic: "Blurred" };
const PROVISIONAL = ["gameplay_a", "gameplay_b"];
// The real render of a layout at a shape (public/media/kit-preview, made by scripts/make_kit_previews.py).
export const kitPreviewId = (aspect: string, layout: string, camera?: string | null) =>
  [aspect.replace(":", "x"), layout === "split" ? "split2" : layout === "fill" ? "full" : layout, hasPanels(layout) ? camera || DEFAULT_PANELS.camera : ""].filter(Boolean).join("-");

// LAYOUT: one row per shape, naming its layout. A kit cuts clips to one shape, so one row is in use (its words are
// white); the others show what they would use, in grey. Picking a layout under another shape moves the kit to it.
export function LayoutRows({ kit, listed, set }: Omit<Props, "actions">) {
  const aspects: string[] = RATIOS.filter((a) => (listed.aspect?.values || ["9:16"]).includes(a));
  const pictures = useMedia("kit-preview")?.items || [];
  const pick = (aspect: string, layout: string) => set({ aspect, vertical: true, layout,
    ...(hasPanels(layout) ? { camera: kit.camera ?? DEFAULT_PANELS.camera, split_ratio: kit.split_ratio ?? DEFAULT_PANELS.split_ratio } : { camera: null, split_ratio: null }) });
  return (
    <div className="-mx-3 -mt-3 grid grid-cols-2 gap-x-6 narrow:grid-cols-1" role="group" aria-label="Layout for each shape">
      {aspects.map((a) => {
        const used = kit.aspect === a, layouts = layoutChoices(listed, a, used ? kit.layout : "auto");
        return (
          <Dropdown key={a} label={`Layouts for ${a}`} kind="dialog" className="w-full" panelClass="rounded-[20px] px-[18px] pb-[18px] pt-4"
            trigger={(t, open) => (
              <button {...t} type="button" title={used ? `This kit cuts clips to ${a}` : `Not this kit's shape. Pick a layout here to cut clips to ${a} instead.`}
                className={`flex h-12 w-full min-w-0 cursor-pointer items-center gap-[10px] rounded-control border-0 px-3 text-left font-sans transition-colors duration-base hover:bg-control ${open ? "bg-control" : "bg-transparent"}`}>
                <span className={`flex-none rounded-[3px] border-[1.5px] border-solid ${used ? "border-text" : "border-fg-2"} ${RATIO_BOX[a]}`} aria-hidden="true" />
                <span className={`w-[42px] flex-none text-[15px] font-medium ${used ? "text-text" : "text-fg-2"}`}>{a}</span>
                <span className={`min-w-0 truncate text-[14.5px] ${used ? "text-text" : "text-fg-3"}`}>{layoutName(used ? kit.layout : "auto")}</span>
                <Icon name="chevron" size={16} className={`flex-none text-fg-2 transition-transform duration-base ${open ? "rotate-180" : ""}`} />
              </button>)}>
            <p className="m-0 flex items-center gap-[6px] pb-3 font-sans text-[14px] text-text">Layouts for {a}
              <span title="Each picture is that layout cut by our renderer at this shape. Captions and the hook are added on top." className="grid text-fg-2"><Icon name="info" size={15} /></span></p>
            <div role="radiogroup" aria-label={`Layout at ${a}`} className="flex max-w-[558px] flex-wrap gap-x-2 gap-y-3 p-[4px]">
              {layouts.map((l) => {
                const on = used && kit.layout === l, picture = pictures.find((i) => i.id === kitPreviewId(a, l, on ? kit.camera : null));
                return (
                  <button key={l} type="button" data-item role="radio" aria-checked={on} title={layoutName(l)} onClick={() => pick(a, l)}
                    className={`group grid cursor-pointer content-start justify-items-center gap-[5px] border-0 bg-transparent p-0 pb-[3px] font-sans ${TILE_WIDTH[a]} ${on ? "shadow-[0_0_0_2px_theme(colors.control),0_0_0_3.5px_theme(colors.text)]" : ""}`}>
                    <span className={`relative grid w-full place-items-center overflow-hidden rounded-8 bg-raised ${TILE[a]}`}>
                      {picture?.poster ? <img src={mediaUrl("kit-preview", picture.poster)} alt="" loading="lazy" className="h-full w-full object-cover" />
                        : <LookSketch aspect={a} layout={l} captions={false} box={ratioOf(a)} />}
                      {on && <span className="absolute right-[4px] top-[4px] grid h-[15px] w-[15px] place-items-center rounded-full bg-text text-bg" aria-hidden="true"><Icon name="check" size={11} /></span>}
                    </span>
                    <span className={`max-w-full truncate text-center text-[11.5px] leading-[1.25] ${on ? "text-text" : "text-fg-2"}`}>{SHORT[l] || tidy(l)}</span>
                    {PROVISIONAL.includes(l) && <span className="-mt-[3px] rounded-[4px] bg-control-hover px-[3px] text-[8.5px] leading-[13px] text-fg-2">Provisional</span>}
                  </button>);
              })}
            </div>
            {used && hasPanels(kit.layout) && "camera" in listed && <div className="mt-4 grid gap-2">
              <p className="m-0 font-sans text-[14px] text-text">Camera panel</p>
              <div className="flex gap-2" role="radiogroup" aria-label="Camera panel">
                {[["top", "On top"], ["bottom", "Below"]].map(([v, name]) => <button key={v} type="button" data-item role="radio" aria-checked={(kit.camera || "bottom") === v} onClick={() => set({ camera: v })}
                  className="h-9 w-[112px] cursor-pointer rounded-8 border-0 bg-control-hover font-sans text-[13px] text-text aria-checked:bg-btn aria-checked:text-btn-ink">{name}</button>)}
              </div>
            </div>}
          </Dropdown>);
      })}
      <p className="col-span-full m-0 flex flex-wrap items-center gap-2 px-3 pt-3 font-sans text-[13px] text-fg-3">Clips are cut to one shape per kit, the row in white. A layout for every shape in one kit<ComingSoonBadge short /></p>
    </div>
  );
}
const ratioOf = (a: string) => { const [w, h] = a.split(":").map(Number); return w / h; };
