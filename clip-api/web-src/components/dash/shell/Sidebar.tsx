"use client";
// The app's sidebar: our logo, the account card, then the pages in groups. On a computer it is either expanded
// (icons and labels) or collapsed (icons only). On a phone it is a drawer opened from the top bar, always expanded.
import Link from "next/link";
import { Logo } from "@/components/Chrome";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon } from "../Icon";
import { AccountMenu } from "./AccountMenu";
import { isHere, NAV, NavItem } from "./nav";

export const SIDE_OPEN = 248, SIDE_SHUT = 72;

const ITEM = "flex min-h-[40px] items-center gap-3 rounded-12 font-sans text-[14.5px] font-medium leading-[1.2] no-underline";

function Item({ item, path, compact }: { item: NavItem; path: string; compact: boolean }) {
  const here = isHere(path, item);
  const pad = compact ? "justify-center px-0 relative" : "px-3";
  if (!item.href) return (
    <span aria-disabled="true" title={`${item.label}: coming soon`} className={`${ITEM} ${pad} cursor-default text-fg-3`}>
      <Icon name={item.icon} size={20} />
      {compact ? <><span className="sr-only">{item.label}, coming soon</span>
          <span aria-hidden="true" className="absolute right-[10px] top-[8px] h-[6px] w-[6px] rounded-full bg-line-strong" /></>
        : <><span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{item.label}</span><ComingSoonBadge short /></>}
    </span>
  );
  return (
    <Link href={item.href} aria-current={here ? "page" : undefined} title={compact ? item.label : undefined}
      className={`${ITEM} ${pad} text-fg-2 hover:bg-chip hover:text-text aria-[current=page]:bg-chip-hover aria-[current=page]:text-text`}>
      <Icon name={item.icon} size={20} />
      {compact ? <span className="sr-only">{item.label}</span> : <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{item.label}</span>}
    </Link>
  );
}

// `compact`: icons only. `onToggle`: the collapse button (a computer); `onClose`: the drawer's close button (a phone).
export function Sidebar({ me, path, compact, onToggle, onClose, onLogout }: { me: any; path: string; compact: boolean;
  onToggle?: () => void; onClose?: () => void; onLogout: () => void }) {
  return (
    <div className={`flex h-full flex-col gap-4 ${compact ? "px-[10px]" : "px-3"} pb-4 pt-[14px]`}>
      <div className={`flex min-h-[40px] items-center ${compact ? "flex-col gap-3" : "justify-between pl-1"}`}>
        {compact ? <Link href="/dashboard/" aria-label="ClutchClips home" className="grid h-9 w-9 place-items-center"><img src="/icon.svg" alt="" width={28} height={28} className="block" /></Link>
          : onClose ? <Logo /> : <Logo small />}
        {onToggle && <button type="button" onClick={onToggle} aria-label={compact ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!compact}
          title={compact ? "Expand sidebar" : "Collapse sidebar"}
          className="grid h-9 w-9 cursor-pointer place-items-center rounded-8 border border-solid border-line-soft bg-transparent text-muted hover:bg-chip hover:text-text">
          <Icon name="sidebar" size={18} /></button>}
        {onClose && <button type="button" onClick={onClose} aria-label="Close menu"
          className="grid h-10 w-10 cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-muted hover:bg-chip hover:text-text">
          <Icon name="close" size={20} /></button>}
      </div>
      <AccountMenu me={me} onLogout={onLogout} compact={compact} />
      <nav aria-label="App" className="-mx-1 flex-1 overflow-y-auto px-1">
        {NAV.map((group, i) => (
          <ul key={i} className={`m-0 grid list-none gap-[2px] p-0 ${i ? "mt-3 border-0 border-t border-solid border-line-soft pt-3" : ""}`}>
            {group.map((item) => <li key={item.label}><Item item={item} path={path} compact={compact} /></li>)}
          </ul>
        ))}
      </nav>
    </div>
  );
}
