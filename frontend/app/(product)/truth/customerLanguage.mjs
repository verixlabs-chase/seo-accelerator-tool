export const CUSTOMER_LANGUAGE_VERSION = "service-business-plain-language-v2";

export const PROHIBITED_PRIMARY_PHRASES = Object.freeze([
  "deterministic summary",
  "governed location target",
  "deeper review",
  "possible benefit",
  "evidence classification",
  "engine-selected action",
  "decision authority",
  "provider state",
  "runtime state",
]);

const CUSTOMER_LANGUAGE_REPLACEMENTS = Object.freeze([
  [/deterministic SEO intelligence/gi, "InsightOS"],
  [/deterministic intelligence/gi, "InsightOS"],
  [/intelligence engine/gi, "recommendation system"],
  [/governed location target/gi, "saved goal for this location"],
  [/deterministic summary/gi, "saved explanation"],
  [/deeper review/gi, "more information"],
  [
    /possible benefit(?:\s*[—-]\s*more evidence needed)?/gi,
    "we need more information before estimating the result",
  ],
  [/reach more eligible completed customers/gi, "Get more reviews from recent customers"],
  [/eligible completed customers/gi, "recent customers"],
  [/completed customers/gi, "recent customers"],
  [
    /measure the share of eligible customers receiving a request/gi,
    "Count how many recent customers were asked for a review",
  ],
  [/eligible customers receiving a request/gi, "recent customers who were asked for a review"],
  [/eligible customers/gi, "recent customers"],
  [
    /choose compliant post-service request moments/gi,
    "Choose times after a job when Google allows you to ask for a review",
  ],
  [/post-service request moments/gi, "times after a job when you can ask for a review"],
  [/service-completion touchpoints/gi, "follow-ups after a job is finished"],
  [/review request template/gi, "review-request message"],
  [
    /add approved requests without incentives or review gating/gi,
    "Ask recent customers for reviews without rewards or filtering who gets asked",
  ],
  [/review gating/gi, "filtering who gets asked"],
  [/policy-compliant/gi, "allowed by Google"],
  [/social proof/gi, "recent customer reviews"],
  [/\btouchpoints\b/gi, "follow-ups"],
  [/\brationale\b/gi, "reason"],
  [/composite score/gi, "overall search result"],
  [/\bGoogle Business Profile\b/gi, "Google business listing"],
  [/\bGBP\b/g, "Google business listing"],
  [/\bCore Web Vitals\b/gi, "website speed and stability"],
  [/\bLargest Contentful Paint\b/gi, "main content load time"],
  [/\bLCP\b/g, "main content load time"],
  [/\bbacklinks?\b/gi, "links from trusted websites"],
  [/\bschema markup\b/gi, "business details that help Google understand the page"],
  [/\bNAP\b/g, "business name, address, and phone number"],
  [/\bCTR\b/g, "the share of searchers who choose your listing"],
  [/\bindexation\b/gi, "showing the page in Google"],
  [/review acquisition velocity/gi, "new review activity"],
  [/content throughput/gi, "new content"],
  [/backlink acquisition velocity/gi, "new trusted links"],
  [/\bheuristic\b/gi, "estimate"],
  [/\bprovider\b/gi, "data source"],
]);

export function findProhibitedPrimaryPhrases(value) {
  const normalized = String(value || "").toLowerCase();
  return PROHIBITED_PRIMARY_PHRASES.filter((phrase) => normalized.includes(phrase));
}

export function simplifyCustomerCopy(value, { fallback = "" } = {}) {
  let simplified = String(value || "").trim().replace(/\s+/g, " ");
  for (const [pattern, replacement] of CUSTOMER_LANGUAGE_REPLACEMENTS) {
    simplified = simplified.replace(pattern, replacement);
  }

  if (findProhibitedPrimaryPhrases(simplified).length > 0) {
    return fallback;
  }
  return simplified;
}

export function describeChange(tone) {
  if (tone === "positive") {
    return "Improving";
  }
  if (tone === "negative") {
    return "Slipping";
  }
  return "No clear change";
}

export function customerCopyStats(value) {
  const normalized = String(value || "").trim();
  const words = normalized.match(/\b[\w'-]+\b/g) || [];
  const sentences = normalized
    .split(/(?<=[.!?])(?:\s+|$)/)
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    words: words.length,
    sentences: sentences.length,
    averageWordsPerSentence:
      sentences.length === 0 ? 0 : Number((words.length / sentences.length).toFixed(1)),
  };
}
