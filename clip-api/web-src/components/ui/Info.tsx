"use client";
import { Icon } from "@/components/dash/Icon";
import { Dropdown } from "./Dropdown";

// Help that stays out of the way: a small "i" beside a heading that opens the explanation in a panel.
export function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Dropdown label={label} kind="dialog" align="center" panelClass="w-[320px] rounded-[14px] px-4 py-3"
      trigger={(t) => <button {...t} type="button" aria-label={label} title={label}
        className="grid h-6 w-6 cursor-pointer place-items-center rounded-full border-0 bg-transparent p-0 text-fg-2 transition-colors duration-base hover:text-text aria-expanded:text-text"><Icon name="info" size={16} /></button>}>
      <div className="font-sans text-[13.5px] font-normal leading-[1.5] text-text [&_a]:text-lime">{children}</div>
    </Dropdown>
  );
}
