import { Badge } from "./ui/Badge";

// The one "Coming soon" mark for anything planned but not built: nav items, landing sections, app tools.
// Whatever carries it is never a link to a page that does not exist. `short` says "Soon" where space is tight.
export function ComingSoonBadge({ short, className = "" }: { short?: boolean; className?: string }) {
  return <Badge tone="soon" className={className}>{short ? "Soon" : "Coming soon"}</Badge>;
}
