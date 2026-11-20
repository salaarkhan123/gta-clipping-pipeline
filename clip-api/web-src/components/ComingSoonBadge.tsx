// The one "Coming soon" mark for anything planned but not built: nav items, landing sections, app tools.
// Whatever carries it is never a link to a page that does not exist. `short` says "Soon" where space is tight.
export function ComingSoonBadge({ short, className = "" }: { short?: boolean; className?: string }) {
  return (
    <span className={`inline-flex flex-none items-center whitespace-nowrap rounded-pill border border-solid border-line-strong px-2 py-[3px] font-sans text-[11px] font-medium uppercase leading-none tracking-[.04em] text-fg-2 ${className}`}>
      {short ? "Soon" : "Coming soon"}
    </span>
  );
}
