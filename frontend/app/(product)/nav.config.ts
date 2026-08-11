import type { NavItem } from "./components";

const PRODUCT_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: "overview", section: "primary" },
  { href: "/rankings", label: "Search Rankings", icon: "rankings", section: "primary" },
  { href: "/keyword-research", label: "Find Searches", icon: "keyword-research", section: "primary" },
  { href: "/local-visibility", label: "Local Search", icon: "local-search", section: "primary" },
  { href: "/site-health", label: "Website Health", icon: "website-health", section: "primary" },
  { href: "/opportunities", label: "Next Steps", icon: "next-steps", section: "primary" },
  { href: "/reports", label: "Reports", icon: "reports", section: "primary" },
  { href: "/settings", label: "Connection health", icon: "connections", section: "more" },
  { href: "/locations", label: "Manage locations", icon: "locations", section: "more" },
  { href: "/organic-value", label: "Search Value", icon: "search-value", section: "more" },
  { href: "/competitors", label: "Competitors", icon: "competitors", section: "more" },
  { href: "/citations", label: "Directory listings", icon: "listings", section: "more" },
  { href: "/reviews", label: "Customer reviews", icon: "reviews", section: "more" },
  { href: "/profile-campaigns", label: "Profile campaigns", icon: "profile-campaigns", section: "more" },
];

export function buildProductNav(pathname: string): NavItem[] {
  return PRODUCT_NAV_ITEMS.map((item) => ({
    ...item,
    active: pathname === item.href,
  }));
}
