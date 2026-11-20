// Small shared pieces of the signed-in pages, in Tailwind utilities. Use these instead of new CSS classes.
import Link from "next/link";
import { Icon } from "./Icon";

// The row at the top of a page: its title on the left, its actions on the right.
// On a phone every title in it is 20 px, the back-arrow title included.
export const PAGE_HEAD = "flex flex-wrap items-center justify-between gap-3 narrow:[&_h1]:text-[20px]";
export const PAGE_TITLE = "text-[28px] font-semibold tracking-[-0.02em] narrow:text-[22px]";
// A section's heading row: a small title or count on the left, sort and filters on the right.
export const SECTION_HEAD = "flex flex-wrap items-center justify-between gap-[10px]";
// A raised strip (selection bar, balance, top-ups).
export const STRIP = "rounded-16 border border-solid border-line-soft bg-card";
// A card with a lime glow in its corner: the credit balance, the top-ups.
export const BALANCE = "flex flex-wrap items-center justify-between gap-4 rounded-[24px] border border-solid border-line-soft p-6 [background:radial-gradient(ellipse_at_0%_0%,rgba(255,255,255,.07),transparent_60%),theme(colors.card)] [&_h2]:mb-1 [&_h2]:text-[18px]";

export type Crumb = { label: string; href?: string };

const CRUMB_LINK = "min-w-0 max-w-[10rem] overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-medium text-muted hover:text-lime tiny:max-w-[6.5rem]";
const CRUMB_NOW = "min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[20px] font-semibold tracking-[-0.01em]";
const BACK_BTN = "grid h-9 w-9 flex-none place-items-center rounded-full text-muted hover:bg-chip hover:text-text";

// Home (or another ancestor) plus the current page. Last crumb is never a link. Long titles ellipsis so the header does not overflow.
export function Breadcrumb({ crumbs, id }: { crumbs: Crumb[]; id?: string }) {
  const last = crumbs.length - 1;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0 max-w-full">
      <ol className="m-0 flex min-w-0 list-none items-center gap-[6px] p-0">
        {crumbs.map((c, i) => {
          const now = i === last;
          return (
            <li key={`${c.label}-${i}`} className={`flex min-w-0 items-center gap-[6px] ${now ? "flex-1 overflow-hidden" : "max-w-[40%] flex-none overflow-hidden"}`}>
              {i > 0 && <span aria-hidden="true" className="flex-none text-[13px] text-fg-3">/</span>}
              {now ? <h1 id={id} title={c.label} aria-current="page" className={CRUMB_NOW}>{c.label}</h1>
                : c.href ? (
                  <Link href={c.href} aria-label={i === 0 ? c.label : undefined} className="flex min-w-0 items-center gap-[6px] text-muted hover:text-lime">
                    {i === 0 && <span className={BACK_BTN}><Icon name="back" size={20} /></span>}
                    <span title={c.label} className={`${CRUMB_LINK} ${i === 0 ? "tiny:sr-only" : ""}`}>{c.label}</span>
                  </Link>
                ) : <span title={c.label} className={CRUMB_LINK}>{c.label}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function homeLabel(label: string) {
  return label.replace(/^Back to /i, "").trim() || "Home";
}

// A back arrow and the page's title. `crumbs` is a richer trail; without it this is Home → title, same as before.
export function BackTitle({ title, href = "/dashboard/", label = "Back to Home", id, crumbs }: {
  title?: string; href?: string; label?: string; id?: string; crumbs?: Crumb[];
}) {
  const trail = crumbs?.length ? crumbs : [{ label: homeLabel(label), href }, { label: title || "" }];
  return <Breadcrumb crumbs={trail} id={id} />;
}
