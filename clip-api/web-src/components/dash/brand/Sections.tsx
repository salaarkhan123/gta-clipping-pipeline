"use client";
// Brand kit settings column: Basic → Styles → Layout → Additional assets (collapsed). Only what a saved look
// stores can be changed; logos, intro/outro, music and overlays stay Coming soon and save nothing.
import { useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { LookSketch } from "../LookSketch";
import { Icon, IconName } from "../Icon";
import { CaptionStyles, HookTones } from "../setup/Styles";
import { InlineSelect, SettingRow, Switch, Tile } from "../setup/parts";
import type { Kit } from "@/lib/brandkit";
import { KIT_NAME_MAX } from "@/lib/brandkit";
import type { Listed } from "@/lib/options";
import { DEFAULT_PANELS, hasPanels, layoutChoices, layoutName } from "@/lib/templates";

const LIME = "#b8ff3c";

export function Section({ title, hint, children, defaultOpen = true }: {
  title: string; hint?: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = `kit-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className="rounded-[20px] border border-solid border-line-soft bg-card" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="m-0">
        <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
          className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-[20px] border-0 bg-transparent px-5 py-4 text-left font-sans text-[12px] font-semibold uppercase tracking-[.1em] text-muted hover:text-text narrow:px-4">
          {title}<Icon name="chevron" size={18} className={`shrink-0 transition-transform ${open ? "rotate-180" : ""}`} /></button>
      </h2>
      {open && <div id={id} className="grid gap-4 border-t border-solid border-line-soft px-5 pb-5 pt-4 narrow:px-4 narrow:pb-4">
        {hint && <p className="m-0 text-[13px] leading-[1.5] text-muted">{hint}</p>}
        {children}
      </div>}
    </section>
  );
}

function SoonTile({ label, icon = "plus", wide }: { label: string; icon?: IconName; wide?: boolean }) {
  return (
    <span aria-disabled="true" className="grid justify-items-center gap-[6px]">
      <span className={`grid place-items-center rounded-16 border border-dashed border-line text-fg-3 ${wide ? "aspect-video w-[120px]" : "h-[72px] w-[72px]"}`}><Icon name={icon} size={20} /></span>
      <span className="text-[12px] text-fg-3">{label}</span>
    </span>
  );
}

export function KitForm({ kit, listed, set, name, onName }: {
  kit: Kit; listed: Listed; set: (patch: Partial<Kit>) => void; name: string; onName: (name: string) => void;
}) {
  const has = (k: string) => k in listed;
  const aspects: string[] = (listed.aspect?.values || ["9:16"]).filter((a: string) => ["9:16", "16:9", "1:1", "4:5"].includes(a));
  const layouts = layoutChoices(listed, kit.aspect, kit.layout);
  const setLayout = (layout: string) => set(hasPanels(layout) ? { layout, camera: kit.camera ?? DEFAULT_PANELS.camera, split_ratio: kit.split_ratio ?? DEFAULT_PANELS.split_ratio }
    : { layout, camera: null, split_ratio: null });
  const setAspect = (aspect: string) => {
    const fits = layoutChoices(listed, aspect, "auto").includes(kit.layout);
    set({ aspect, vertical: true, ...(fits ? {} : { layout: "auto", camera: null, split_ratio: null }) });
  };
  const accentOn = kit.caption_accent !== null;

  return (
    <div className="grid gap-3">
      <Section title="Basic" hint="Name this look, then set brand colour. Logos land here when uploads ship.">
        <label className="m-0 grid gap-2 text-[13px] font-medium text-muted">Kit name
          <input value={name} maxLength={KIT_NAME_MAX} onChange={(e) => onName(e.target.value)}
            aria-label="Kit name" className="w-full max-w-md" /></label>
        <div className="grid gap-3">
          <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] font-medium text-text">Logos <span className="text-[12.5px] font-normal text-muted">(PNG, JPG, SVG, WebP)</span><ComingSoonBadge /></p>
          <div className="flex gap-3"><SoonTile label="Add" /></div>
        </div>
        {has("caption_accent") && <div className="grid gap-2">
          <p className="m-0 text-[15px] font-medium text-text">Brand colour</p>
          <p className="m-0 text-[13px] text-muted">Keyword accent on Impact captions. Other styles keep their own colours.</p>
          <label className="m-0 inline-flex min-h-[40px] w-max cursor-pointer items-center gap-3 rounded-12 border border-solid border-line-soft bg-surface px-3 text-[14px] font-normal text-label">
            <input type="checkbox" checked={accentOn} onChange={(e) => set({ caption_accent: e.target.checked ? (kit.caption_accent || LIME) : null })} />
            Custom accent
            {accentOn && <input type="color" aria-label="Brand colour" value={kit.caption_accent || LIME}
              onChange={(e) => set({ caption_accent: e.target.value })}
              className="h-8 w-10 cursor-pointer rounded-8 border border-solid border-line bg-transparent p-0" />}
          </label>
        </div>}
      </Section>

      <Section title="Styles" hint="Caption look and opening hook tone for every clip made with this kit.">
        <div className="grid gap-5">
          {has("captions") && <div className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-0.5">
                <span className="text-[15px] font-medium text-text">Captions</span>
                <span className="text-[13px] text-muted">Word-by-word, timed to the voice.</span>
              </div>
              <Switch on={kit.captions} label="Captions" onChange={(v) => set({ captions: v, ...(v ? {} : { caption_emoji: false }) })} />
            </div>
            {kit.captions && <div className="grid gap-3">
              {has("caption_style") && <CaptionStyles styles={listed.caption_style.values || []} value={kit.caption_style} onChange={(s) => set({ caption_style: s })} />}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {has("caption_position") && kit.caption_style === "impact" && <InlineSelect label="Position" value={kit.caption_position} shown={kit.caption_position === "auto" ? "Automatic" : kit.caption_position === "seam" ? "Between panels" : kit.caption_position === "lower" ? "Lower third" : "Centre"}
                  onChange={(v) => set({ caption_position: v })}>
                  {(listed.caption_position.values || []).map((v: string) => <option key={v} value={v}>{v === "auto" ? "Automatic" : v === "seam" ? "Between panels" : v === "lower" ? "Lower third" : "Centre"}</option>)}
                </InlineSelect>}
                {has("caption_emoji") && <label className="m-0 inline-flex min-h-[36px] cursor-pointer items-center gap-2 px-3 text-[14px] font-normal text-label">
                  <input type="checkbox" checked={kit.caption_emoji} onChange={(e) => set({ caption_emoji: e.target.checked })} />Emojis</label>}
                {has("censor") && <label className="m-0 inline-flex min-h-[36px] cursor-pointer items-center gap-2 px-3 text-[14px] font-normal text-label">
                  <input type="checkbox" checked={kit.censor} onChange={(e) => set({ censor: e.target.checked })} />Censor swears</label>}
              </div>
            </div>}
          </div>}
          {has("hook_overlay") && <div className="grid gap-3 border-t border-solid border-line-soft pt-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-0.5">
                <span className="text-[15px] font-medium text-text">Hook</span>
                <span className="text-[13px] text-muted">Short opening line for the first seconds.</span>
              </div>
              <Switch on={kit.hook_overlay} label="Hook" onChange={(v) => set({ hook_overlay: v })} />
            </div>
            {kit.hook_overlay && has("hook_style") && <HookTones tones={listed.hook_style.values || []} catalogue={listed.hook_style.catalogue} value={kit.hook_style} onChange={(s) => set({ hook_style: s })} />}
          </div>}
        </div>
      </Section>

      <Section title="Layout" hint="Shape and framing. Only layouts this render backend accepts for the chosen shape.">
        {has("aspect") && <div className="flex flex-wrap gap-2" role="group" aria-label="Shape">
          {aspects.map((a) => <button key={a} type="button" aria-pressed={kit.aspect === a} onClick={() => setAspect(a)}
            className={`inline-flex min-h-[38px] cursor-pointer items-center gap-2 rounded-12 border border-solid px-3.5 font-sans text-[14px] font-medium
              ${kit.aspect === a ? "border-text bg-text text-bg" : "border-line bg-transparent text-text hover:bg-chip"}`}>
            <Icon name={a === "16:9" ? "film" : "phone"} size={16} />{a}</button>)}
        </div>}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2.5" role="group" aria-label="Layout">
          {layouts.map((l) => <Tile key={l} name={layoutName(l)} on={kit.layout === l} onClick={() => setLayout(l)} className="aspect-square w-full bg-surface">
            <LookSketch aspect={kit.aspect} layout={l} camera={kit.layout === l ? kit.camera : null} split={kit.layout === l ? kit.split_ratio : null} captions={false} box={1} />
          </Tile>)}
        </div>
        {hasPanels(kit.layout) && has("camera") && <div className="flex flex-wrap items-center gap-2">
          <InlineSelect label="Camera" value={kit.camera || "bottom"} shown={(kit.camera || "bottom") === "top" ? "On top" : "Below the gameplay"} onChange={(v) => set({ camera: v })}>
            <option value="top">On top</option><option value="bottom">Below the gameplay</option></InlineSelect>
        </div>}
        <p className="m-0 flex flex-wrap items-center gap-2 text-[13px] text-fg-3">A different layout for each shape<ComingSoonBadge short /></p>
      </Section>

      <Section title="Additional assets" defaultOpen={false}
        hint="Editing switches apply today. Intro, outro, logo overlays and music stay Coming soon.">
        <div className="grid divide-x-0 divide-y divide-solid divide-line-soft">
          {has("flash_forward") && <SettingRow icon="rewind" name="Open on the peak" hint="Starts with a flash of the best moment, then plays from the start.">
            <Switch on={kit.flash_forward} label="Open on the peak" onChange={(v) => set({ flash_forward: v })} /></SettingRow>}
          {has("tighten") && <SettingRow icon="scissors" name="Cut dead air" hint="Removes long silences and filler words.">
            <Switch on={kit.tighten} label="Cut dead air" onChange={(v) => set({ tighten: v })} /></SettingRow>}
          {has("punch_zoom") && <SettingRow icon="zoomIn" name="Punch-in zoom" hint="A slight zoom on the gameplay at the big moments.">
            <Switch on={kit.punch_zoom} label="Punch-in zoom" onChange={(v) => set({ punch_zoom: v })} /></SettingRow>}
        </div>
        <div className="grid gap-3 pt-2">
          <p className="m-0 flex flex-wrap items-center gap-2 text-[14px] text-muted">A short opener and end card for each shape.<ComingSoonBadge /></p>
          <div className="grid grid-cols-2 gap-5 narrow:grid-cols-1">
            {[["9:16", "phone"], ["16:9", "film"]].map(([s, i]) => (
              <div key={s} className="grid gap-3">
                <span className="flex items-center gap-2 text-[14px] font-medium text-text"><Icon name={i as IconName} size={17} className="text-muted" />{s}</span>
                <div className="flex gap-3"><SoonTile label="Intro" wide={s === "16:9"} /><SoonTile label="Outro" wide={s === "16:9"} /></div>
              </div>))}
          </div>
        </div>
        <div className="grid gap-3 border-t border-solid border-line-soft pt-4">
          <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] font-medium text-text">Music <span className="text-[12.5px] font-normal text-muted">(background track under every clip)</span><ComingSoonBadge /></p>
          <div className="flex gap-3"><SoonTile label="Add" icon="music" /></div>
        </div>
        <div className="grid gap-3 border-t border-solid border-line-soft pt-4">
          <p className="m-0 flex flex-wrap items-center gap-2 text-[15px] font-medium text-text">Overlays <span className="text-[12.5px] font-normal text-muted">(watermarks and lower-thirds)</span><ComingSoonBadge /></p>
          <div className="flex gap-3"><SoonTile label="Add" icon="image" /></div>
        </div>
      </Section>
    </div>
  );
}
