"use client";
// The bar above every signed-in page: on a phone the menu button and the logo, then notifications, the credit
// balance and Add credits. It sits beside the sidebar, never over it.
import Link from "next/link";
import { Logo } from "@/components/Chrome";
import { ComingSoonBadge } from "@/components/ComingSoonBadge";
import { Icon } from "../Icon";

export function TopBar({ me, onMenu }: { me: any; onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-40 flex h-topbar items-center justify-end gap-2 bg-[rgba(0,0,0,.85)] px-5 [backdrop-filter:blur(12px)]
      narrow:justify-between narrow:border-0 narrow:border-b narrow:border-solid narrow:border-line-soft narrow:pl-2 narrow:pr-3">
      <div className="hidden items-center gap-1 narrow:flex">
        <button type="button" onClick={onMenu} aria-label="Open menu"
          className="grid h-10 w-10 cursor-pointer place-items-center rounded-8 border-0 bg-transparent text-text hover:bg-chip"><Icon name="menu" size={22} /></button>
        <Logo small />
      </div>
      <div className="flex items-center gap-2 tiny:gap-1">
        {/* No notifications API yet: the bell is shown as planned and does nothing. */}
        <span aria-disabled="true" title="Notifications: coming soon" className="relative inline-flex h-9 items-center gap-1 rounded-8 px-2 text-fg-3 tiny:hidden">
          <Icon name="bell" size={19} /><span className="sr-only">Notifications</span><ComingSoonBadge short /></span>
        <Link href="/dashboard/credits/" title="Your credits. One credit is one minute of video. See how they were used."
          className="inline-flex h-9 items-center gap-[6px] rounded-full px-3 tabular-nums text-lime no-underline hover:bg-chip">
          <Icon name="bolt" size={17} /><b className="font-sans text-[14.5px] font-semibold leading-none text-text">{Number(me.credits).toLocaleString()}</b>
          <span className="sr-only"> credits</span></Link>
        <Link href="/dashboard/pricing/" className="btn small primary whitespace-nowrap px-[14px] py-[7px] shadow-none">Add credits</Link>
      </div>
    </header>
  );
}
