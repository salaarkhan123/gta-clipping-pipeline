"use client";
// The design system on one page, for review: every token (app/tokens.css) and every shared component
// (components/ui/). Not linked from the site. The left half is the public site's theme, the toggle switches the page
// to the app's theme so the same components can be checked in both.
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ClipCard } from "@/components/ui/ClipCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field, ImportField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { PhonePreview, PREVIEW_RATIOS, PreviewRatio } from "@/components/ui/PhonePreview";
import { Pills, Tabs } from "@/components/ui/Pill";
import { PlatformBadge } from "@/components/ui/PlatformGlyph";
import { Score } from "@/components/ui/Score";
import { More, SectionCard } from "@/components/ui/SectionCard";
import { aiRated, useItems } from "@/components/landing/demos/Footage";
import { mediaUrl } from "@/lib/media";

const SURFACES = ["canvas", "canvas-2", "panel", "card", "surface", "control", "control-hover", "raised"];
const LINES = ["line-soft", "line", "line-strong"];
const TEXTS = ["fg", "text", "fg-2", "fg-3", "accent", "danger", "warn"];
const TYPE: [string, string, string][] = [
  ["text-display", "Display", "Turn streams into clips"], ["text-h2", "Heading", "Clips that look ready to post"], ["text-h3", "Subheading", "Find highlights"],
  ["text-title", "Title", "Import gameplay"], ["text-lead", "Lead", "One grey sentence under a headline."], ["text-body", "Body", "Settings, descriptions and table text."],
  ["text-small", "Small", "Meta lines under a clip."], ["text-caption", "Caption", "Credits and hints."], ["text-label", "LABEL", "BASIC · CAPTION STYLES · LAYOUT"],
];
const RADII = ["radius-xs", "radius-sm", "radius-md", "radius-card", "radius-stage", "radius-control"];
const SPACES = ["space-1", "space-2", "space-3", "space-4", "space-5", "space-6", "space-7", "space-8", "space-9"];
const MOTION = ["dur-fast", "dur", "dur-slow"];

const Group = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="grid gap-4 !p-0"><h2 className="m-0 text-[12px] font-medium uppercase tracking-[.08em] text-fg-2">{title}</h2>{children}</section>
);
const value = (name: string) => (typeof window === "undefined" ? "" : getComputedStyle(document.getElementById("design-root")!).getPropertyValue(`--${name}`).trim());

export default function DesignPage() {
  const [theme, setTheme] = useState<"site" | "app">("site");
  const [pill, setPill] = useState("9:16"), [tab, setTab] = useState("all"), [ratio, setRatio] = useState<PreviewRatio>("9:16");
  const [, bump] = useState(0);
  const clips = useItems("hero-vertical-clips").filter((i) => /^clip-\d+$/.test(i.id)).slice(0, 3);
  const pick = (t: "site" | "app") => { setTheme(t); setTimeout(() => bump((n) => n + 1), 0); };

  return (
    <div id="design-root" data-theme={theme === "app" ? "app" : undefined} className="min-h-screen bg-bg font-sans text-text">
      <main className="mx-auto grid max-w-[1120px] gap-12 px-6 py-12 narrow:px-4 narrow:py-8">
        <PageHeader title="ClutchClips design system" hint="Tokens and shared components. One source: app/tokens.css and components/ui.">
          <Pills label="Theme" value={theme} onChange={pick} options={[{ value: "site", label: "Public site" }, { value: "app", label: "App" }]} />
        </PageHeader>

        <Group title="Surfaces">
          <div className="grid grid-cols-4 gap-3 narrow:grid-cols-2">
            {SURFACES.map((n) => <div key={n} className="grid gap-2"><span className="h-16 rounded-12 shadow-[inset_0_0_0_1px_var(--line)]" style={{ background: `var(--${n})` }} />
              <span className="text-[12px] text-fg-2"><b className="font-medium text-text">--{n}</b> <span suppressHydrationWarning>{value(n)}</span></span></div>)}
          </div>
        </Group>
        <Group title="Lines, text and accent">
          <div className="grid grid-cols-5 gap-3 narrow:grid-cols-2">
            {LINES.map((n) => <div key={n} className="grid gap-2"><span className="h-12 rounded-12 bg-card" style={{ boxShadow: `inset 0 0 0 1px var(--${n})` }} /><span className="text-[12px] text-fg-2">--{n}</span></div>)}
            {TEXTS.map((n) => <div key={n} className="grid gap-2"><span className="grid h-12 place-items-center rounded-12 bg-card text-[20px] font-semibold" style={{ color: `var(--${n})` }}>Aa</span>
              <span className="text-[12px] text-fg-2">--{n} <span suppressHydrationWarning>{value(n)}</span></span></div>)}
          </div>
        </Group>
        <Group title="Type scale">
          <div className="grid gap-4">
            {TYPE.map(([token, name, sample]) => <div key={token} className="grid grid-cols-[150px_minmax(0,1fr)] items-baseline gap-4 narrow:grid-cols-1 narrow:gap-1">
              <span className="text-[12px] text-fg-2">{name} · --{token}</span>
              <span className="font-semibold tracking-[-0.02em] text-fg" style={{ fontSize: `var(--${token})`, lineHeight: 1.15, fontWeight: token.match(/display|h2|h3|title/) ? 600 : 400 }}>{sample}</span></div>)}
          </div>
        </Group>
        <Group title="Radius, spacing, motion">
          <div className="flex flex-wrap items-end gap-4">
            {RADII.map((n) => <div key={n} className="grid justify-items-center gap-2"><span className="h-14 w-20 bg-control" style={{ borderRadius: `var(--${n})` }} /><span className="text-[12px] text-fg-2">--{n}</span></div>)}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {SPACES.map((n) => <div key={n} className="grid justify-items-center gap-2"><span className="w-6 rounded-[3px] bg-lime" style={{ height: `var(--${n})` }} /><span className="text-[11px] text-fg-2">{n.replace("space-", "")}</span></div>)}
          </div>
          <div className="flex flex-wrap gap-3">
            {MOTION.map((n) => <button key={n} type="button" className="group h-11 w-[150px] cursor-pointer overflow-hidden rounded-12 border-0 bg-control p-0 text-left text-[12px] text-fg-2">
              <span className="block h-full w-10 bg-lime/70 ease-out group-hover:translate-x-[110px]" style={{ transition: `transform var(--${n}) var(--ease-out)` }} />
              <span className="pointer-events-none -mt-8 block pl-3 text-text">--{n}</span></button>)}
            <p className="m-0 self-center text-[12px] text-fg-2">Point at a block. All durations are 0 under prefers-reduced-motion.</p>
          </div>
        </Group>

        <Group title="Button">
          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg">Primary</Button><Button>Primary</Button><Button size="sm">Primary</Button>
            <Button variant="secondary" size="lg">Secondary</Button><Button variant="secondary">Secondary</Button><Button variant="secondary" size="sm">Secondary</Button>
            <Button variant="ghost">Ghost</Button><Button disabled>Disabled</Button>
          </div>
        </Group>
        <Group title="Field and ImportField">
          <div className="grid max-w-[560px] gap-4">
            <ImportField id="design-import" placeholder="Paste a recorded video link or upload a file." cta="Get clips" onLink={() => {}} onFile={() => {}} accept="video/*" size="xl" />
            <ImportField id="design-import-lg" placeholder="Paste a recorded video link or upload a file." cta="Get clips" onLink={() => {}} onFile={() => {}} accept="video/*" problem="That doesn't look like a link." />
            <Field label="Kit name" hint="up to 80 characters" defaultValue="My brand kit" />
          </div>
        </Group>
        <Group title="Pills, Tabs, Badge, platform badges">
          <div className="flex flex-wrap items-center gap-6">
            <Pills label="Shape" value={pill} onChange={setPill} options={["9:16", "16:9", "1:1", "4:5"].map((v) => ({ value: v, label: v }))} />
            <Tabs label="Kind" value={tab} onChange={setTab} options={[{ value: "all", label: "All" }, { value: "clutch", label: "Clutch" }, { value: "funny", label: "Funny" }, { value: "fail", label: "Fail" }]} />
            <span className="flex items-center gap-2"><Badge tone="soon" /><Badge tone="unavailable" /><Badge tone="new" /><Badge>Free</Badge></span>
            <span className="flex items-center gap-2">{(["youtube", "tiktok", "instagram", "facebook"] as const).map((p) => <PlatformBadge key={p} id={p} className="h-9 w-9" />)}</span>
          </div>
        </Group>
        <Group title="Score and ClipCard">
          <div className="flex flex-wrap items-end gap-4">
            <Score value={92} kind="ai" /><Score value={92} kind="ai" size="sm" /><Score value={1} of={6} kind="rank" /><Score value={1} of={6} kind="rank" size="sm" />
            <p className="m-0 max-w-[420px] text-[12px] text-fg-2">One mark everywhere a score shows: md on cards, sm on small tiles. An AI score is lime; a clip the AI did not rate shows its rank in white. The numbers here are the approved clips' own ratings.</p>
          </div>
          <div className="grid grid-cols-4 gap-4 narrow:grid-cols-2">
            {clips.map((c) => <ClipCard key={c.id} poster={c.poster ? mediaUrl("hero-vertical-clips", c.poster) : null} video={mediaUrl("hero-vertical-clips", c.src)}
              title={c.game} meta={c.credit} why="Why this clip: one short line." score={aiRated(c) ? <Score value={c.rating!} kind="ai" /> : undefined}
              actions={<Button variant="secondary" size="sm">Edit clip</Button>} />)}
            <ClipCard title="No footage for this game yet" meta="Empty slot" />
          </div>
        </Group>
        <Group title="Card, SectionCard, PageHeader, EmptyState, PhonePreview">
          <div className="grid grid-cols-[minmax(0,1fr)_260px] items-start gap-6 narrow:grid-cols-1">
            <div className="grid gap-5">
              <Card><p className="m-0 text-[14px] text-fg-2">Card: a surface one step above the canvas, 20 px corners, no shadow.</p></Card>
              <SectionCard label="Basic" hint="A settings group with a small uppercase label. The chevron folds it away.">
                <Field label="Kit name" defaultValue="My brand kit" />
                <More><p className="m-0 text-[14px] text-fg-2">Advanced settings stay behind More.</p></More>
              </SectionCard>
              <SectionCard label="Additional assets" defaultOpen={false}><p className="m-0 text-[14px] text-fg-2">Closed by default.</p></SectionCard>
              <EmptyState title="No clips yet" action={<Button size="sm">Make clips</Button>}>What belongs here, and the one action that fills it.</EmptyState>
            </div>
            <div className="grid justify-items-center gap-4">
              <Pills size="sm" label="Ratio" value={ratio} onChange={setRatio} options={PREVIEW_RATIOS.map((r) => ({ value: r, label: r }))} />
              <PhonePreview ratio={ratio} label="Preview">
                {clips[0] && <video muted loop autoPlay playsInline className="absolute inset-0 h-full w-full object-cover" poster={clips[0].poster ? mediaUrl("hero-vertical-clips", clips[0].poster) : undefined}>
                  <source src={mediaUrl("hero-vertical-clips", clips[0].src)} type="video/mp4" /></video>}
              </PhonePreview>
              {clips[0]?.credit && <p className="m-0 text-[11.5px] text-fg-3">{clips[0].credit}</p>}
            </div>
          </div>
        </Group>
      </main>
    </div>
  );
}
