import type { ProductIconName } from "../components";

export type HelpAudience = "solo" | "multi" | "team";

export type HelpGuide = {
  id: string;
  title: string;
  summary: string;
  category: "Get started" | "Understand results" | "Take action" | "Fix a problem";
  icon: ProductIconName;
  audiences: HelpAudience[];
  steps: string[];
  actionLabel: string;
  actionHref: string;
  searchTerms: string[];
};

export type GlossaryTerm = {
  term: string;
  meaning: string;
  usefulBecause: string;
  searchTerms: string[];
};

export const HELP_AUDIENCES: Array<{
  id: HelpAudience;
  label: string;
  description: string;
}> = [
  {
    id: "solo",
    label: "One business",
    description: "Set up and improve one service business.",
  },
  {
    id: "multi",
    label: "Several locations",
    description: "Compare and manage several business locations.",
  },
  {
    id: "team",
    label: "Team or agency",
    description: "Review work and reports across client locations.",
  },
];

export const HELP_GUIDES: HelpGuide[] = [
  {
    id: "finish-first-setup",
    title: "Finish your first business setup",
    summary: "Save the business, its services, the places it serves, and the first checks.",
    category: "Get started",
    icon: "check",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Overview and choose Set up your business.",
      "Add the business name and website.",
      "List the services customers can hire you for.",
      "Add the cities, counties, or ZIP codes the business serves.",
      "Stay on the final step until each first check is complete or clearly marked for follow-up.",
    ],
    actionLabel: "Open Overview",
    actionHref: "/dashboard",
    searchTerms: ["onboarding", "new business", "website", "services", "service areas", "zip codes"],
  },
  {
    id: "connect-google-search",
    title: "Connect Google search results",
    summary: "Bring in the searches, appearances, visits, and average position Google has saved for the website.",
    category: "Get started",
    icon: "connections",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Connection health.",
      "Find Google search results and choose Connect or Reconnect.",
      "Sign in with an account that can view the website in Google Search Console.",
      "Match the correct website to the correct business location.",
      "Return to Connection health and confirm that the latest update is current.",
    ],
    actionLabel: "Open Connection health",
    actionHref: "/settings",
    searchTerms: ["google", "search console", "connect", "reconnect", "property", "website data"],
  },
  {
    id: "connect-google-listing",
    title: "Connect a Google business listing",
    summary: "Match each location to the listing that customers see in Google Search and Maps.",
    category: "Get started",
    icon: "local-search",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Connection health and find Google business listings.",
      "Sign in with an account that manages the listing.",
      "Choose the listing that belongs to the selected location.",
      "Repeat the match for each additional location.",
      "Leave a healthy connection alone unless it stops updating.",
    ],
    actionLabel: "Open Connection health",
    actionHref: "/settings",
    searchTerms: ["maps", "business listing", "google profile", "location", "match listing"],
  },
  {
    id: "connect-workflow-tool",
    title: "Connect Zapier, Make, or n8n",
    summary: "Send selected InsightOS updates to the tools your business already uses.",
    category: "Get started",
    icon: "connections",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Settings, choose Workflow tools, then choose Send updates to another tool.",
      "Select Zapier, Make, Pipedream, or n8n and follow the short guide shown for that tool.",
      "Copy the receiving address from the workflow tool and paste it into InsightOS.",
      "Choose the updates you want, save the connection, and keep the one-time security key private.",
      "Send the safe test and confirm the matching sample or execution appears in the workflow tool.",
      "Do not call it finished until InsightOS shows the test as accepted; the first real update adds production proof.",
    ],
    actionLabel: "Open Workflow tools",
    actionHref: "/settings#external-automation",
    searchTerms: [
      "workflow",
      "automation",
      "zapier",
      "make",
      "n8n",
      "pipedream",
      "webhook",
      "receiving address",
      "test connection",
    ],
  },
  {
    id: "choose-searches",
    title: "Choose searches worth tracking",
    summary: "Keep the phrases that describe profitable work in the places the business actually serves.",
    category: "Get started",
    icon: "keyword-research",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Find Searches for the correct location.",
      "Confirm the services and service areas first.",
      "Review the strongest matches and remove unrelated ideas.",
      "Select the phrases that match real customer work.",
      "Choose Track selected to move them into Search Rankings.",
    ],
    actionLabel: "Open Find Searches",
    actionHref: "/keyword-research",
    searchTerms: ["keywords", "phrases", "search ideas", "track searches", "irrelevant searches"],
  },
  {
    id: "read-overview",
    title: "Understand the Overview numbers",
    summary: "Start with visits, appearances, and average Google position before opening more detail.",
    category: "Understand results",
    icon: "overview",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Confirm the correct location in the menu at the top.",
      "Read the most important change and the suggested next action.",
      "Use the green and red direction labels to see what improved or slipped.",
      "Change the dates when you need a longer comparison.",
      "Open source details only when a number looks missing or unexpected.",
    ],
    actionLabel: "Open Overview",
    actionHref: "/dashboard",
    searchTerms: ["dashboard", "overview", "visits", "appearances", "position", "dates", "charts"],
  },
  {
    id: "read-rankings",
    title: "Read a search ranking",
    summary: "A smaller position number means the business appeared closer to the top for that search.",
    category: "Understand results",
    icon: "rankings",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Choose the location you want to review.",
      "Start with the phrase that slipped the most.",
      "Check its current position and the earlier position.",
      "Review the matching page before changing content.",
      "Use Next Steps when the system has enough information to recommend work.",
    ],
    actionLabel: "Open Search Rankings",
    actionHref: "/rankings",
    searchTerms: ["rank", "ranking", "position", "keyword", "top 10", "page one"],
  },
  {
    id: "read-local-grid",
    title: "Run and read a local search map",
    summary: "See how close to the top the listing appears from different points around the service area.",
    category: "Understand results",
    icon: "local-search",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Local Search and choose one tracked phrase.",
      "Confirm the map center and the area you want to measure.",
      "Review the credit price before starting a paid map check.",
      "Run the check and wait for every map point to finish.",
      "Compare later checks to see where coverage improved or slipped.",
    ],
    actionLabel: "Open Local Search",
    actionHref: "/local-visibility",
    searchTerms: ["heatmap", "grid", "map", "local ranking", "map points", "near me"],
  },
  {
    id: "work-next-steps",
    title: "Finish a recommended action",
    summary: "Work through one checklist, record what was completed, and return when it is time to measure the result.",
    category: "Take action",
    icon: "next-steps",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Next Steps and start with the first action.",
      "Read why the action matters and what number it is meant to improve.",
      "Complete each checklist item in order.",
      "Mark the work complete only after it was actually done.",
      "Return after the stated waiting period to check the measured result.",
    ],
    actionLabel: "Open Next Steps",
    actionHref: "/opportunities",
    searchTerms: ["recommendation", "checklist", "action", "daily", "weekly", "monthly", "complete"],
  },
  {
    id: "create-report",
    title: "Create and share a business report",
    summary: "Package saved results, improvements, concerns, and the next useful actions into one clear update.",
    category: "Take action",
    icon: "reports",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Reports and check whether the business has enough current information.",
      "Choose the report month and create the detailed report.",
      "Review the headline, charts, concerns, and numbered actions.",
      "Download the file or create a private link only after the report is ready.",
      "For several locations, use the all-location PDF after each location has a matching saved report.",
    ],
    actionLabel: "Open Reports",
    actionHref: "/reports",
    searchTerms: ["report", "pdf", "share", "download", "client", "all locations"],
  },
  {
    id: "manage-locations",
    title: "Keep several locations separate",
    summary: "Give every location its own website, listing, tracked searches, checks, actions, and reports.",
    category: "Take action",
    icon: "locations",
    audiences: ["multi", "team"],
    steps: [
      "Open Manage locations and confirm every location belongs to the right account group.",
      "Give each location its own website and home market.",
      "Match search and listing connections separately for each location.",
      "Use the location menu before reviewing or changing work.",
      "Use portfolio views to compare locations without combining their numbers.",
    ],
    actionLabel: "Open Manage locations",
    actionHref: "/locations",
    searchTerms: ["multi location", "subaccounts", "groups", "portfolio", "switch location", "agency"],
  },
  {
    id: "fix-stale-data",
    title: "Fix information that stopped updating",
    summary: "Reconnect only the source marked as needing attention and leave healthy connections alone.",
    category: "Fix a problem",
    icon: "warning",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Connection health and choose the affected location.",
      "Find the source marked Needs attention or Stale.",
      "Read the last successful update and the recovery instruction.",
      "Reconnect the source or correct its location match.",
      "Run one fresh update and confirm the new date before changing anything else.",
    ],
    actionLabel: "Open Connection health",
    actionHref: "/settings",
    searchTerms: ["stale", "old data", "not updating", "failed", "reconnect", "missing data"],
  },
  {
    id: "fix-website-check",
    title: "Start with the first website problem",
    summary: "Fix the first red or amber item, then run another check before moving to a lower-priority problem.",
    category: "Fix a problem",
    icon: "website-health",
    audiences: ["solo", "multi", "team"],
    steps: [
      "Open Website Health for the correct location.",
      "Start with the first item marked Fix this first.",
      "Read the customer-facing effect before opening the detailed explanation.",
      "Complete the suggested repair or send it to the person who manages the website.",
      "Run another website check and compare the measured result.",
    ],
    actionLabel: "Open Website Health",
    actionHref: "/site-health",
    searchTerms: ["website", "speed", "broken", "health", "page problem", "scan"],
  },
];

export const GLOSSARY_TERMS: GlossaryTerm[] = [
  {
    term: "Times shown on Google",
    meaning: "How many times pages from the website appeared in Google search results during the selected dates.",
    usefulBecause: "It shows whether more or fewer searchers had a chance to see the business.",
    searchTerms: ["appearances", "impressions", "shown"],
  },
  {
    term: "Visits from Google",
    meaning: "The number of times someone chose a website result from Google and opened the site.",
    usefulBecause: "It shows how often a Google appearance became an actual website visit.",
    searchTerms: ["clicks", "traffic", "website visits"],
  },
  {
    term: "Average Google position",
    meaning: "The average place where the website appeared across the Google searches that produced an appearance.",
    usefulBecause: "A smaller number generally means the website appeared closer to the top, but it is an average across many searches.",
    searchTerms: ["rank", "ranking", "position"],
  },
  {
    term: "Tracked search",
    meaning: "A customer phrase the business chose to check regularly for one location.",
    usefulBecause: "It keeps measurement focused on services and places that matter to the business.",
    searchTerms: ["keyword", "phrase", "search term"],
  },
  {
    term: "Local search map",
    meaning: "A map that checks where a Google business listing appears from several points around an area.",
    usefulBecause: "It shows that a business can rank well near its address but poorly farther away.",
    searchTerms: ["heatmap", "grid", "map ranking", "local finder"],
  },
  {
    term: "Website check",
    meaning: "A saved review of website pages, loading behavior, broken items, and other problems that can affect visitors or Google.",
    usefulBecause: "It helps the owner fix the most important website problem first and check the result afterward.",
    searchTerms: ["site health", "scan", "page speed", "broken page"],
  },
  {
    term: "Search Value",
    meaning: "An estimate of what similar visits might have cost if the business had paid for them through search ads.",
    usefulBecause: "It helps compare organic search work with paid-search costs. It is not revenue or guaranteed savings.",
    searchTerms: ["value", "money", "ads", "replacement cost"],
  },
  {
    term: "Current and earlier dates",
    meaning: "Two date ranges of the same length used to show what changed over time.",
    usefulBecause: "Equal date ranges make the direction easier to understand without shifting later days into the wrong comparison.",
    searchTerms: ["comparison", "previous period", "date range", "chart"],
  },
  {
    term: "Needs attention",
    meaning: "A connection, measurement, or action has a clear problem that requires a person to check it.",
    usefulBecause: "It separates real blockers from healthy items that can be left alone.",
    searchTerms: ["error", "warning", "failed", "blocked"],
  },
  {
    term: "Waiting for more information",
    meaning: "InsightOS does not yet have enough current measurements to make a responsible comparison or estimate.",
    usefulBecause: "Missing information stays visible instead of being treated as a zero or a successful result.",
    searchTerms: ["not measured", "missing", "insufficient", "unavailable"],
  },
];

export function matchesHelpSearch(
  values: Array<string | undefined>,
  query: string,
): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return values.some((value) => String(value || "").toLowerCase().includes(normalized));
}
