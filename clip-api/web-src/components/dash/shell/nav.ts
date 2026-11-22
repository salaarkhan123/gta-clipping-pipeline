import type { IconName } from "../Icon";

// The sidebar, in groups. An item without `href` is planned but not built: it carries the Coming soon mark and is
// never a link. `under` lists other routes that light the item up.
// The template gallery (/dashboard/templates/) is not listed: templates are picked in job setup. The page stays.
export type NavItem = { label: string; icon: IconName; href?: string; under?: string[]; exact?: boolean };
// `label` is the small grey heading over the group; the group without one is pinned to the bottom of the sidebar.
export type NavGroup = { label?: string; items: NavItem[] };

export const NAV: NavGroup[] = [
  { label: "Create", items: [
    { label: "Home", icon: "home", href: "/dashboard/", exact: true, under: ["/dashboard/start"] },
    { label: "My projects", icon: "library", href: "/dashboard/library/",
      under: ["/dashboard/project", "/dashboard/edit", "/dashboard/transcript", "/dashboard/summary"] },
    { label: "Brand kit", icon: "palette", href: "/dashboard/brand-kit/" },
    { label: "Asset library", icon: "folder", href: "/dashboard/assets/" },
  ] },
  { label: "Post", items: [
    { label: "Calendar", icon: "calendar", href: "/dashboard/calendar/" },
    { label: "Analytics", icon: "chart", href: "/dashboard/analytics/" },
    { label: "Social accounts", icon: "share", href: "/dashboard/social-accounts/" },
    { label: "Creators League", icon: "gamepad", href: "/dashboard/league/" },
  ] },
  { items: [
    { label: "Labs", icon: "flask" },
    { label: "API access", icon: "code", href: "/dashboard/keys/" },
    { label: "Learning centre", icon: "book" },
    { label: "Help", icon: "help", href: "/contact/" },
  ] },
];

const bare = (p: string) => p.replace(/\/+$/, "");
export const isHere = (path: string, item: NavItem) => {
  if (!item.href) return false;
  const p = bare(path), h = bare(item.href);
  return p === h || (!item.exact && p.startsWith(h + "/")) || (item.under || []).some((u) => p === u || p.startsWith(u + "/"));
};
