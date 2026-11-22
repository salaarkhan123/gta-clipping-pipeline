"use client";
// The bar above every signed-in page: on a phone the menu button and the logo, then Find, notifications, the credit
// balance and Add credits. It sits beside the sidebar, never over it.
import Link from "next/link";
import { Logo } from "@/components/Chrome";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { shortcutLabel } from "@/lib/globalFind";
import { Icon } from "../Icon";

// `quiet`: a page whose own header row sits where the bar would be (Brand kit). The bar then shows only on a phone,
// where it holds the menu button.
export function TopBar({ me, onMenu, onFind, quiet }: { me: any; onMenu: () => void; onFind: () => void; quiet?: boolean }) {
  const keys = shortcutLabel();
  return (
    <header className={`sticky top-0 z-40 ${quiet ? "hidden narrow:flex" : "flex"} h-[60px] items-center justify-end gap-2 bg-bg pl-6 pr-6 narrow:justify-between narrow:pl-2 narrow:pr-3`}>
      <div className="hidden items-center gap-1 narrow:flex">
        <button type="button" onClick={onMenu} aria-label="Open menu"
          className="grid h-10 w-10 cursor-pointer place-items-center rounded-control border-0 bg-transparent text-text hover:bg-control"><Icon name="menu" size={22} /></button>
        <Logo small />
      </div>
      <div className="flex items-center gap-1 tiny:gap-0">
        <button type="button" onClick={onFind} title={`Find moments (${keys})`}
          className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-control border-0 bg-transparent px-[10px] text-fg-2 transition-colors duration-base hover:bg-control hover:text-text">
          <Icon name="search" size={18} /><span className="text-[14px] tiny:hidden">Find</span>
          <kbd className="rounded-[6px] bg-control px-[6px] py-px font-mono text-[11px] text-fg-2 tiny:hidden">{keys}</kbd>
        </button>
        {/* No notifications API yet: the bell is shown as planned and does nothing. */}
        <span aria-disabled="true" title="Notifications: coming soon" className="relative inline-flex h-9 items-center gap-[6px] rounded-control px-[10px] text-fg-3 tiny:hidden">
          <Icon name="bell" size={18} /><span className="sr-only">Notifications</span><ComingSoonBadge short /></span>
        <Link href="/dashboard/credits/" title="Your credits. One credit is one minute of video. See how they were used."
          className="mr-2 inline-flex h-9 items-center gap-[6px] rounded-control px-[10px] tabular-nums text-lime no-underline transition-colors duration-base hover:bg-control">
          <Icon name="bolt" size={17} /><b className="font-sans text-[15px] font-medium leading-none text-text">{Number(me.credits).toLocaleString()}</b>
          <span className="sr-only"> credits</span></Link>
        <Link href="/dashboard/pricing/" className="btn small ghost whitespace-nowrap">Add credits</Link>
      </div>
    </header>
  );
}
