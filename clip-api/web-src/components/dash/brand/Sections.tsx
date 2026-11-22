"use client";
// Brand kit settings column: Basic, Styles, Layout, Editing, Intro & outro, Media. Each group is a card of compact
// rows; a row's choices open in a picker (Pickers.tsx). Only what a saved look stores can be changed: logos,
// intros, outros, music and overlays are Coming soon and save nothing.
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { More, SectionCard } from "@/components/ui/SectionCard";
import { Icon, IconName } from "../Icon";
import { Switch } from "../setup/parts";
import type { Kit } from "@/lib/brandkit";
import type { Listed } from "@/lib/options";
import { CaptionRow, HookRow, KitActions, LayoutRows } from "./Pickers";

const LIME = "#b8ff3c";
const SUB = "m-0 flex flex-wrap items-center gap-2 font-sans text-[15px] font-medium text-text";
const NOTE = "text-[12.5px] font-normal text-fg-2";

// A settings group: the shared collapsible card, labelled in small capitals.
export function Section({ title, hint, children, defaultOpen = true }: {
  title: string; hint?: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  return <SectionCard label={title} hint={hint} defaultOpen={defaultOpen}>{children}</SectionCard>;
}

// A planned asset slot: a dashed tile that does nothing, its label under it.
function SoonTile({ label, icon = "plus", wide }: { label: string; icon?: IconName; wide?: boolean }) {
  return (
    <span aria-disabled="true" className="grid justify-items-center gap-2">
      <span className={`grid place-items-center rounded-12 border border-dashed border-line-strong bg-control text-fg-2 ${wide ? "h-[72px] w-[96px]" : "h-16 w-16"}`}><Icon name={icon} size={20} /></span>
      <span className="text-[12.5px] text-fg-3">{label}</span>
    </span>
  );
}

// An on/off setting as one compact row: its name and one sentence, the switch on the right.
function ToggleRow({ name, hint, on, onChange }: { name: string; hint: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <div className="flex min-h-[48px] items-center gap-4">
      <div className="grid min-w-0 flex-1 gap-[6px]">
        <span className="font-sans text-[15px] font-medium leading-[22px] text-text">{name}</span>
        <span className="font-sans text-[14px] leading-[20px] text-fg-2">{hint}</span>
      </div>
      <Switch on={on} label={name} onChange={onChange} />
    </div>
  );
}

export function KitForm({ kit, listed, set, actions }: { kit: Kit; listed: Listed; set: (patch: Partial<Kit>) => void; actions: KitActions }) {
  const has = (k: string) => k in listed;
  return (
    <div className="grid gap-5">
      <Section title="Basic">
        <div className="grid gap-4">
          <p className={SUB}>Logos <span className={NOTE}>(PNG, JPG, SVG, WebP)</span><ComingSoonBadge /></p>
          <div className="flex items-start gap-5">
            <SoonTile label="Add" />
            {has("caption_accent") && <label className="m-0 grid cursor-pointer justify-items-center gap-2" title="Brand colour: the keyword colour of Impact captions. Other caption styles keep their own colours.">
              <span className="relative block h-16 w-16 overflow-hidden rounded-12 border border-solid border-line" style={{ background: kit.caption_accent || LIME }}>
                <input type="color" aria-label="Brand colour" value={kit.caption_accent || LIME} onChange={(e) => set({ caption_accent: e.target.value })}
                  className="absolute -inset-2 h-[150%] w-[150%] cursor-pointer !border-0 !p-0 opacity-0" /></span>
              <span className="text-[12.5px] font-normal text-fg-2">Brand colour</span>
            </label>}
          </div>
        </div>
      </Section>

      <Section title="Styles" hint="How captions and the opening hook look on every clip made with this kit.">
        <div className="grid gap-5">
          {has("captions") && <CaptionRow kit={kit} listed={listed} set={set} actions={actions} />}
          {has("hook_overlay") && has("hook_style") && <HookRow kit={kit} listed={listed} set={set} actions={actions} />}
        </div>
      </Section>

      <Section title="Layout" hint="The shape clips are cut to, and how the gameplay and camera are framed in it.">
        <LayoutRows kit={kit} listed={listed} set={set} />
      </Section>

      <Section title="Editing" hint="Cuts and moves the AI makes on every clip.">
        <div className="grid gap-5">
          {has("flash_forward") && <ToggleRow name="Open on the peak" hint="Starts with a flash of the best moment, then plays from the start."
            on={kit.flash_forward} onChange={(v) => set({ flash_forward: v })} />}
          {has("tighten") && <ToggleRow name="Cut dead air" hint="Removes long silences and filler words." on={kit.tighten} onChange={(v) => set({ tighten: v })} />}
          {has("punch_zoom") && <ToggleRow name="Punch-in zoom" hint="A slight zoom on the gameplay at the big moments." on={kit.punch_zoom} onChange={(v) => set({ punch_zoom: v })} />}
        </div>
      </Section>

      <Section title="Intro & outro">
        <p className="m-0 -mt-3 flex flex-wrap items-center gap-2 text-[14px] leading-[20px] text-fg-2">A short opener and end card for each shape.<ComingSoonBadge /></p>
        <div className="grid grid-cols-2 gap-6 narrow:grid-cols-1">
          {["9:16", "16:9"].map((s) => (
            <div key={s} className="grid gap-4">
              <span className="flex items-center gap-[10px] font-sans text-[15px] font-medium text-text">
                <span className={`rounded-[3px] border-[1.5px] border-solid border-text ${s === "16:9" ? "h-[10px] w-[16px]" : "h-[16px] w-[10px]"}`} aria-hidden="true" />{s}</span>
              <div className="flex gap-4"><SoonTile label="Intro" wide /><SoonTile label="Outro" wide /></div>
            </div>))}
        </div>
      </Section>

      <Section title="Media">
        <div className="grid gap-4">
          <p className={SUB}>Music <span className={NOTE}>(a track under every clip)</span><ComingSoonBadge /></p>
          <div className="flex gap-3"><SoonTile label="Add" icon="music" /></div>
        </div>
        <More>
          <div className="grid gap-4">
            <p className={SUB}>Overlays <span className={NOTE}>(watermarks and lower-thirds)</span><ComingSoonBadge /></p>
            <div className="flex gap-3"><SoonTile label="Add" icon="image" /></div>
          </div>
        </More>
      </Section>
    </div>
  );
}
