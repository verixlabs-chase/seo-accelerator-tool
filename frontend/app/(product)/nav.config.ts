import type { NavItem } from "./components";

const PRODUCT_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/rankings", label: "Rankings" },
  { href: "/reports", label: "Reports" },
  { href: "/opportunities", label: "Opportunities" },
  { href: "/settings", label: "Settings", hidden: true },
  { href: "/locations", label: "Locations", hidden: true },
  { href: "/local-visibility", label: "Local SEO" },
  { href: "/site-health", label: "Technical Health" },
  { href: "/competitors", label: "Competitors" },
];

export function buildProductNav(pathname: string): NavItem[] {
  return PRODUCT_NAV_ITEMS.map((item) => ({
    ...item,
    active: pathname === item.href,
  }));
}
