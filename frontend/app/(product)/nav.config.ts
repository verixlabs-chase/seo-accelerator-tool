import type { NavItem } from "./components";

const PRODUCT_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: "overview", section: "most-used" },
  { href: "/opportunities", label: "Next Steps", icon: "next-steps", section: "most-used" },
  { href: "/reviews", label: "Customer Reviews", icon: "reviews", section: "most-used" },
  { href: "/reports", label: "Reports", icon: "reports", section: "most-used" },

  { href: "/rankings", label: "Search Rankings", icon: "rankings", section: "performance" },
  { href: "/local-visibility", label: "Local Search", icon: "local-search", section: "performance" },
  { href: "/site-health", label: "Website Health", icon: "website-health", section: "performance" },
  { href: "/organic-value", label: "Search Value", icon: "search-value", section: "performance" },
  { href: "/ai-visibility", label: "AI Search", icon: "ai-search", section: "performance", badge: "Beta" },

  { href: "/keyword-research", label: "Find Searches", icon: "keyword-research", section: "improve" },
  { href: "/competitors", label: "Competitors", icon: "competitors", section: "improve" },
  { href: "/content", label: "Content", icon: "content", section: "improve" },
  { href: "/citations", label: "Directory Listings", icon: "listings", section: "improve" },
  { href: "/profile-campaigns", label: "Profile Campaigns", icon: "profile-campaigns", section: "improve" },

  { href: "/locations", label: "Locations", icon: "locations", section: "workspace" },
  { href: "/settings", label: "Settings & Connections", icon: "connections", section: "workspace" },
  { href: "/client-access", label: "Client Access", icon: "client-access", section: "workspace" },
  { href: "/activity", label: "Team Activity", icon: "activity", section: "workspace" },

  { href: "/help", label: "Help Center", icon: "help", section: "help" },
];

export function buildProductNav(pathname: string): NavItem[] {
  return PRODUCT_NAV_ITEMS.map((item) => ({
    ...item,
    active: pathname === item.href,
  }));
}
