import type { IconName } from "../Icon";

// The sidebar, in groups. An item without `href` is planned but not built: it carries the Coming soon mark and is
// never a link. `under` lists other routes that light the item up.
export type NavItem = { label: string; icon: IconName; href?: string; under?: string[]; exact?: boolean };

export const NAV: NavItem[][] = [
  [
    { label: "Home", icon: "home", href: "/dashboard/", exact: true, under: ["/dashboard/start"] },
    { label: "Projects", icon: "library", href: "/dashboard/library/",
      under: ["/dashboard/project", "/dashboard/edit", "/dashboard/transcript", "/dashboard/summary"] },
    { label: "Brand kit", icon: "palette", href: "/dashboard/brand-kit/" },
    { label: "Asset library", icon: "folder", href: "/dashboard/assets/" },
    { label: "Templates", icon: "template", href: "/dashboard/templates/" },
  ],
  [
    { label: "Calendar", icon: "calendar" },
    { label: "Analytics", icon: "chart" },
    { label: "Social accounts", icon: "share" },
  ],
  [
    { label: "Labs", icon: "flask" },
    { label: "API access", icon: "code", href: "/dashboard/keys/" },
    { label: "Learning centre", icon: "book" },
  ],
];

const bare = (p: string) => p.replace(/\/+$/, "");
export const isHere = (path: string, item: NavItem) => {
  if (!item.href) return false;
  const p = bare(path), h = bare(item.href);
  return p === h || (!item.exact && p.startsWith(h + "/")) || (item.under || []).some((u) => p === u || p.startsWith(u + "/"));
};
