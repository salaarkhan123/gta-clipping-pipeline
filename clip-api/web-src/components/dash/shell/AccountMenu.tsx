"use client";
// The account card at the top of the sidebar and the menu it opens: who is signed in and on which plan, billing,
// credit usage, language, API keys, other ClutchClips products, log out.
import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { accountName, usePlanName } from "@/lib/account";
import { API } from "@/lib/api";
import { useLanguageSwitches } from "@/lib/languages";
import { isBuilt, toolHref, TOOLS } from "@/lib/tools";
import { Icon, IconName } from "../Icon";
import { useDismiss } from "./useDismiss";

const ITEM = "flex min-h-[38px] w-full cursor-pointer items-center gap-[10px] rounded-8 border-0 bg-transparent px-[10px] py-[6px] text-left font-sans text-[14px] font-medium leading-[normal] text-text no-underline hover:bg-chip-hover";
const OFF = "flex min-h-[38px] w-full cursor-default items-center gap-[10px] rounded-8 px-[10px] py-[6px] font-sans text-[14px] font-medium leading-[normal] text-fg-2";
// Other ClutchClips products, from the tools list: a link once built, Coming soon until then.
const PRODUCTS = ["thumbnail", "live"];

export function Avatar({ email, size = 32 }: { email: string; size?: number }) {
  return (
    <span aria-hidden="true" style={{ width: size, height: size, fontSize: size * 0.44 }}
      className="grid flex-none place-items-center rounded-full bg-[linear-gradient(135deg,theme(colors.lime),theme(colors.cyan))] font-sans font-bold leading-none text-ink">
      {(email[0] || "?").toUpperCase()}</span>
  );
}

export const PlanBadge = ({ name }: { name: string }) => (
  <span className="inline-flex flex-none items-center rounded-[6px] bg-raised px-[6px] py-[2px] font-sans text-[11.5px] font-medium leading-[1.3] text-label">{name}</span>
);

const Row = ({ href, icon, children }: { href: string; icon: IconName; children: React.ReactNode }) => (
  <Link className={ITEM} href={href}><Icon name={icon} size={18} className="text-muted" />{children}</Link>
);

// `compact`: the collapsed sidebar, where only the avatar shows.
export function AccountMenu({ me, onLogout, compact }: { me: any; onLogout: () => void; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), btn = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, box, btn);
  const plan = usePlanName(me.plan), name = accountName(me.email), on = useLanguageSwitches();

  return (
    <div ref={box} className="relative">
      <button ref={btn} type="button" aria-expanded={open} aria-label={`Account: ${name}, ${plan} plan`} onClick={() => setOpen(!open)}
        className={`flex w-full cursor-pointer items-center rounded-12 border border-solid border-line-soft bg-card font-sans text-text hover:bg-chip aria-expanded:bg-chip
          ${compact ? "flex-col gap-1 px-1 py-2" : "gap-[10px] px-[10px] py-[9px] text-left"}`}>
        <Avatar email={me.email} size={compact ? 30 : 34} />
        {!compact && <span className="grid min-w-0 flex-1 gap-[3px]">
          <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[14px] font-semibold leading-[1.2]" title={me.email}>{name}</span>
          <span className="flex"><PlanBadge name={plan} /></span>
        </span>}
        <Icon name="chevron" size={compact ? 14 : 16} className="text-muted" />
      </button>
      {open && <div aria-label="Account menu" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) close(); }}
        className="absolute left-0 top-[calc(100%+8px)] z-[70] grid w-[268px] max-w-[calc(100vw-24px)] gap-[2px] rounded-16 border border-solid border-line bg-card-2 p-2 shadow-pop">
        <p className="m-0 px-[10px] pb-1 pt-[6px] text-[12px] font-medium text-muted">Account</p>
        <div className="mb-1 flex items-center gap-[10px] border-0 border-b border-solid border-line px-[10px] pb-[10px] pt-1">
          <Avatar email={me.email} size={30} />
          <span className="grid min-w-0 gap-[2px]">
            <span className="flex min-w-0 items-center gap-2 text-[14px] font-semibold">
              <span className="overflow-hidden text-ellipsis whitespace-nowrap">{name}</span><PlanBadge name={plan} /></span>
            <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[12.5px] text-muted" title={me.email}>{me.email}</span>
          </span>
        </div>
        <Row href="/dashboard/billing/" icon="card">Subscription</Row>
        <Row href="/dashboard/credits/" icon="bolt">Credit usage history</Row>
        <Row href="/dashboard/cases/#remove-imports" icon="shield">Remove my imports</Row>
        <span className={OFF} aria-disabled="true" title="The app is in English for now. Captions follow the language spoken in your video.">
          <Icon name="globe" size={18} />Language<span className="ml-auto text-[13px] font-normal">English</span><ComingSoonBadge short /></span>
        <Row href="/dashboard/keys/" icon="key">API keys</Row>
        <a className={ITEM} href={`${API}/docs`} target="_blank" rel="noreferrer"><Icon name="external" size={18} className="text-muted" />API docs</a>
        <div className="my-1 h-px bg-line" role="separator" />
        {TOOLS.filter((t) => PRODUCTS.includes(t.id)).map((t) => isBuilt(t, on)
          ? <Link key={t.id} className={ITEM} href={toolHref(t)}><Icon name={t.icon} size={18} className="text-muted" />ClutchClips {t.name}</Link>
          : <span key={t.id} className={OFF} aria-disabled="true"><Icon name={t.icon} size={18} />ClutchClips {t.name}<ComingSoonBadge short className="ml-auto" /></span>)}
        <div className="my-1 h-px bg-line" role="separator" />
        <button type="button" className={ITEM} onClick={onLogout}><Icon name="logout" size={18} className="text-muted" />Log out</button>
      </div>}
    </div>
  );
}
