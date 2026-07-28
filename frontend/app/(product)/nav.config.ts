import type { NavItem } from "./components";

const PRODUCT_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Overview", section: "primary" },
  { href: "/rankings", label: "Rankings", section: "primary" },
  { href: "/local-visibility", label: "Local Visibility", section: "primary" },
  { href: "/site-health", label: "Site Health", section: "primary" },
  { href: "/opportunities", label: "Next Steps", section: "primary" },
  { href: "/reports", label: "Reports", section: "primary" },
  { href: "/settings", label: "Settings", hidden: true },
  { href: "/locations", label: "Manage locations", section: "more" },
  { href: "/organic-value", label: "Organic Value", section: "more" },
  { href: "/competitors", label: "Competitors", section: "more" },
  { href: "/citations", label: "Citations", section: "more" },
];

export function buildProductNav(pathname: string): NavItem[] {
  return PRODUCT_NAV_ITEMS.map((item) => ({
    ...item,
    active: pathname === item.href,
  }));
}
