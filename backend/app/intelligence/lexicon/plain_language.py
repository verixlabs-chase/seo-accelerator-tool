from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import re


SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION = "service-business-plain-language-v1"
SUMMARY_MAX_WORDS = 32
WHY_NOW_MAX_WORDS = 24
ACTION_FIRST_VERBS = frozenset(
    {
        "add",
        "ask",
        "change",
        "check",
        "choose",
        "compare",
        "connect",
        "correct",
        "create",
        "earn",
        "fix",
        "focus",
        "improve",
        "keep",
        "make",
        "match",
        "publish",
        "remove",
        "review",
        "run",
        "set",
        "speed",
        "start",
        "test",
        "track",
        "update",
        "use",
        "write",
    }
)

_GUIDE_PATH = Path(__file__).with_name("service_business_language_guide.md")
_DISALLOWED_PATTERNS = (
    ("deterministic", re.compile(r"\bdeterministic\b", re.IGNORECASE)),
    ("intelligence", re.compile(r"\bintelligence\b", re.IGNORECASE)),
    ("lexicon", re.compile(r"\blexicon\b", re.IGNORECASE)),
    ("heuristic", re.compile(r"\bheuristic\b", re.IGNORECASE)),
    ("provider", re.compile(r"\bprovider\b", re.IGNORECASE)),
    ("API", re.compile(r"\bapi\b", re.IGNORECASE)),
    ("runtime", re.compile(r"\bruntime\b", re.IGNORECASE)),
    (
        "evidence identifier",
        re.compile(r"\bevidence (?:identifier|id)\b", re.IGNORECASE),
    ),
    ("composite score", re.compile(r"\bcomposite score\b", re.IGNORECASE)),
    ("visibility score", re.compile(r"\bvisibility score\b", re.IGNORECASE)),
    (
        "online presence score",
        re.compile(r"\bonline presence score\b", re.IGNORECASE),
    ),
    ("velocity", re.compile(r"\bvelocity\b", re.IGNORECASE)),
    ("throughput", re.compile(r"\bthroughput\b", re.IGNORECASE)),
    ("GBP", re.compile(r"\bgbp\b", re.IGNORECASE)),
    (
        "Google Business Profile",
        re.compile(r"\bgoogle business profile\b", re.IGNORECASE),
    ),
    ("SERP", re.compile(r"\bserps?\b", re.IGNORECASE)),
    ("CTR", re.compile(r"\bctr\b", re.IGNORECASE)),
    ("LCP", re.compile(r"\blcp\b", re.IGNORECASE)),
    ("INP", re.compile(r"\binp\b", re.IGNORECASE)),
    ("CLS", re.compile(r"\bcls\b", re.IGNORECASE)),
    ("NAP", re.compile(r"\bnap\b", re.IGNORECASE)),
    ("backlink", re.compile(r"\bbacklinks?\b", re.IGNORECASE)),
    ("schema markup", re.compile(r"\bschema markup\b", re.IGNORECASE)),
    ("canonical tag", re.compile(r"\bcanonical tags?\b", re.IGNORECASE)),
    ("crawl depth", re.compile(r"\bcrawl depth\b", re.IGNORECASE)),
    ("crawl", re.compile(r"\bcrawl(?:ed|ing|s)?\b", re.IGNORECASE)),
    ("indexation", re.compile(r"\bindexation\b", re.IGNORECASE)),
    ("Core Web Vitals", re.compile(r"\bcore web vitals\b", re.IGNORECASE)),
    ("technical", re.compile(r"\btechnical\b", re.IGNORECASE)),
    ("SEO", re.compile(r"\bseo\b", re.IGNORECASE)),
    ("confidence", re.compile(r"\bconfidence\b", re.IGNORECASE)),
    ("risk tier", re.compile(r"\brisk tier\b", re.IGNORECASE)),
    ("campaign", re.compile(r"\bcampaign\b", re.IGNORECASE)),
    ("citation", re.compile(r"\bcitations?\b", re.IGNORECASE)),
    ("meta title", re.compile(r"\bmeta title\b", re.IGNORECASE)),
    ("meta description", re.compile(r"\bmeta description\b", re.IGNORECASE)),
)

_PLAIN_REPLACEMENTS = (
    (re.compile(r"\bdeterministic intelligence engine\b", re.IGNORECASE), "InsightOS"),
    (re.compile(r"\bdeterministic engine\b", re.IGNORECASE), "InsightOS"),
    (re.compile(r"\bGoogle Business Profile\b", re.IGNORECASE), "Google business listing"),
    (re.compile(r"\bGBP\b", re.IGNORECASE), "Google business listing"),
    (re.compile(r"\bCore Web Vitals\b", re.IGNORECASE), "website speed and stability"),
    (re.compile(r"\bLargest Contentful Paint\b", re.IGNORECASE), "main content load time"),
    (re.compile(r"\bLCP\b", re.IGNORECASE), "main content load time"),
    (re.compile(r"\bbacklinks?\b", re.IGNORECASE), "links from trusted websites"),
    (re.compile(r"\bschema markup\b", re.IGNORECASE), "business details that help Google understand the page"),
    (
        re.compile(r"\bNAP(?: consistency| inconsistency)?\b", re.IGNORECASE),
        "matching business name, address, and phone number",
    ),
    (re.compile(r"\bCTR\b", re.IGNORECASE), "the share of searchers who choose your listing"),
    (re.compile(r"\bindexation\b", re.IGNORECASE), "showing the page in Google"),
    (re.compile(r"\blexicon-approved\b", re.IGNORECASE), "safe"),
    (re.compile(r"\bheuristic\b", re.IGNORECASE), "estimate"),
    (re.compile(r"\bprovider\b", re.IGNORECASE), "data source"),
)


@lru_cache(maxsize=1)
def load_service_business_language_guide() -> str:
    guide = _GUIDE_PATH.read_text(encoding="utf-8").strip()
    if not guide:
        raise RuntimeError("The service-business language guide is empty.")
    return guide


def service_business_language_guide_hash() -> str:
    return hashlib.sha256(
        load_service_business_language_guide().encode("utf-8")
    ).hexdigest()


def find_disallowed_customer_terms(value: str) -> list[str]:
    return [
        label
        for label, pattern in _DISALLOWED_PATTERNS
        if pattern.search(value)
    ]


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def sentence_count(value: str) -> int:
    sentences = [
        item
        for item in re.split(r"(?<=[.!?])(?:\s+|$)", value.strip())
        if item.strip()
    ]
    return max(1, len(sentences)) if value.strip() else 0


def starts_with_action(value: str) -> bool:
    first_word = re.match(r"\s*([A-Za-z]+)", value)
    return bool(
        first_word
        and first_word.group(1).lower() in ACTION_FIRST_VERBS
    )


def ensure_action_first(value: str, *, max_words: int) -> str:
    normalized = " ".join(value.strip().split())
    if not starts_with_action(normalized):
        normalized = f"Review this issue. {normalized}"
    words = normalized.split()
    if len(words) <= max_words:
        return normalized
    return " ".join(words[:max_words]).rstrip(" ,;:") + "."


def simplify_internal_language(
    value: str,
    *,
    max_words: int,
    max_sentences: int = 2,
    action_first: bool = True,
) -> str:
    simplified = " ".join(value.strip().split())
    for pattern, replacement in _PLAIN_REPLACEMENTS:
        simplified = pattern.sub(replacement, simplified)
    if find_disallowed_customer_terms(simplified):
        return ""
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", simplified)
        if item.strip()
    ]
    simplified = " ".join(sentences[:max_sentences])
    if action_first:
        return ensure_action_first(simplified, max_words=max_words)
    words = simplified.split()
    if len(words) <= max_words:
        return simplified
    return " ".join(words[:max_words]).rstrip(" ,;:") + "."
