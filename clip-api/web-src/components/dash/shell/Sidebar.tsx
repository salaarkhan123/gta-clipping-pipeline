"use client";
// The app's sidebar: our logo, the account card, then the pages in groups. On a computer it is either expanded
// (icons and labels) or collapsed (icons only). On a phone it is a drawer opened from the top bar, always expanded.
import Link from "next/link";
import { Logo } from "@/components/Chrome";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon } from "../Icon";
import { AccountMenu } from "./AccountMenu";
import { isHere, NAV, NavItem } from "./nav";

// Widths measured from the reference app: 224 px with labels, 60 px as an icon rail (--side-open, --side-shut).
export const SIDE_OPEN = 224, SIDE_SHUT = 60;

const ITEM = "flex h-10 items-center gap-[10px] rounded-control font-sans text-[15px] font-normal leading-[1.2] no-underline transition-colors duration-base";
const SQUARE = "grid h-[37px] w-[37px] flex-none cursor-pointer place-items-center rounded-control border border-solid border-line bg-transparent text-text transition-colors duration-base hover:bg-control";

function Item({ item, path, compact }: { item: NavItem; path: string; compact: boolean }) {
  const here = isHere(path, item);
  const pad = compact ? "justify-center px-0 relative" : "px-[10px]";
  if (!item.href) return (
    <span aria-disabled="true" title={`${item.label}: coming soon`} className={`${ITEM} ${pad} cursor-default text-fg-3`}>
      <Icon name={item.icon} size={18} />
      {compact ? <span className="sr-only">{item.label}, coming soon</span>
        : <><span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{item.label}</span><ComingSoonBadge short /></>}
    </span>
  );
  return (
    <Link href={item.href} aria-current={here ? "page" : undefined} title={compact ? item.label : undefined}
      className={`${ITEM} ${pad} text-text hover:bg-card aria-[current=page]:bg-control`}>
      <Icon name={item.icon} size={18} />
      {compact ? <span className="sr-only">{item.label}</span> : <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{item.label}</span>}
    </Link>
  );
}

// `compact`: icons only. `onToggle`: the collapse button (a computer); `onClose`: the drawer's close button (a phone).
export function Sidebar({ me, path, compact, onToggle, onClose, onLogout }: { me: any; path: string; compact: boolean;
  onToggle?: () => void; onClose?: () => void; onLogout: () => void }) {
  return (
    <div className="flex h-full flex-col px-3 pb-4 pt-[14px]">
      <div className={`flex items-center ${compact ? "flex-col gap-[22px]" : "h-[37px] justify-between pl-1"}`}>
        {compact ? null : onClose ? <Logo /> : <Logo small />}
        {onToggle && <button type="button" onClick={onToggle} aria-label={compact ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!compact}
          title={compact ? "Expand sidebar" : "Collapse sidebar"} className={SQUARE}>
          <Icon name="sidebar" size={18} /></button>}
        {onClose && <button type="button" onClick={onClose} aria-label="Close menu" className={SQUARE}><Icon name="close" size={18} /></button>}
      </div>
      <div className="mt-[25px]"><AccountMenu me={me} onLogout={onLogout} compact={compact} /></div>
      {/* The slot under the account card: the one thing most visits start with. */}
      <Link href="/dashboard/" title="New project" aria-label="New project"
        className={`mt-4 flex h-[37px] flex-none items-center justify-center gap-2 rounded-control border border-solid border-line bg-transparent font-sans text-[14px] text-text no-underline transition-colors duration-base hover:bg-control ${compact ? "w-[37px] self-center" : ""}`}>
        <Icon name="plus" size={17} />{!compact && "New project"}</Link>
      <nav aria-label="App" className="-mx-1 mt-[52px] flex-1 overflow-y-auto px-1">
        {NAV.map((group, i) => (
          <ul key={i} className={`m-0 grid list-none gap-[6px] p-0 ${i ? "mt-[22px]" : ""}`}>
            {group.map((item) => <li key={item.label}><Item item={item} path={path} compact={compact} /></li>)}
          </ul>
        ))}
      </nav>
    </div>
  );
}
