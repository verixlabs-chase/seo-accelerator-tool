import type { NavItem } from "./components";

const PRODUCT_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Overview", section: "primary" },
  { href: "/rankings", label: "Search Rankings", section: "primary" },
  { href: "/local-visibility", label: "Local Search", section: "primary" },
  { href: "/site-health", label: "Website Health", section: "primary" },
  { href: "/opportunities", label: "Next Steps", section: "primary" },
  { href: "/reports", label: "Reports", section: "primary" },
  { href: "/settings", label: "Data connections", section: "more" },
  { href: "/locations", label: "Manage locations", section: "more" },
  { href: "/organic-value", label: "Search Value", section: "more" },
  { href: "/competitors", label: "Competitors", section: "more" },
  { href: "/citations", label: "Directory listings", section: "more" },
];

export function buildProductNav(pathname: string): NavItem[] {
  return PRODUCT_NAV_ITEMS.map((item) => ({
    ...item,
    active: pathname === item.href,
  }));
}
