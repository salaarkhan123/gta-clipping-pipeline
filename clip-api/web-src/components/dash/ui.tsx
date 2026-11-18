// Small shared pieces of the signed-in pages, in Tailwind utilities. Use these instead of new CSS classes.
import Link from "next/link";
import { Icon } from "./Icon";

// The row at the top of a page: its title on the left, its actions on the right.
export const PAGE_HEAD = "flex flex-wrap items-center justify-between gap-3";
export const PAGE_TITLE = "text-[22px] narrow:text-[20px]";
// A section's heading row: a small title or count on the left, sort and filters on the right.
export const SECTION_HEAD = "flex flex-wrap items-center justify-between gap-[10px]";
// A raised strip (selection bar, balance, top-ups).
export const STRIP = "rounded-12 border border-solid border-line-soft bg-panel";
// A card with a lime glow in its corner: the credit balance, the top-ups.
export const BALANCE = "flex flex-wrap items-center justify-between gap-4 rounded-16 border border-solid border-line-soft p-[22px] [background:radial-gradient(ellipse_at_0%_0%,theme(colors.lime-wash),transparent_60%),theme(colors.panel)] [&_h2]:mb-1 [&_h2]:text-[18px]";

// A back arrow and the page's title, cut short with an ellipsis when it is long.
export function BackTitle({ title, href = "/dashboard/", label = "Back to Home", id }: { title: string; href?: string; label?: string; id?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-[10px]">
      <Link href={href} aria-label={label} className="grid h-9 w-9 flex-none place-items-center rounded-8 text-muted hover:bg-chip hover:text-text"><Icon name="back" size={20} /></Link>
      <h1 id={id} title={title} className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[18px]">{title}</h1>
    </div>
  );
}
