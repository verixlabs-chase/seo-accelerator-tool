from __future__ import annotations

from app.intelligence.lexicon.loader import get_builtin_lexicon

DEPRECATED_RUNTIME = True
# Threshold contract metadata (frozen location per master spec).
version_id = "v1.0.0"
threshold_source = "Google Search Central + web.dev + Google Business Profile guidance"
THRESHOLD_PROVENANCE = {
    "source_type": "official_documentation",
    "last_reviewed_at": "2026-02-25T00:00:00Z",
    "owner": "strategy_engine",
}

CITATION_URLS: dict[str, str] = {
    "search_titles_guidance": "https://developers.google.com/search/docs/appearance/title-link",
    "core_web_vitals": "https://web.dev/articles/vitals",
    "gbp_reviews": "https://support.google.com/business/answer/3474122",
}
_LEXICON_METRICS = get_builtin_lexicon().metric_index


def _good(metric_id: str) -> float:
    thresholds = _LEXICON_METRICS[metric_id].thresholds
    if thresholds is None:
        raise RuntimeError(f"Lexicon metric {metric_id} is missing thresholds")
    return float(thresholds.good_boundary)


def _poor(metric_id: str) -> float:
    thresholds = _LEXICON_METRICS[metric_id].thresholds
    if thresholds is None:
        raise RuntimeError(f"Lexicon metric {metric_id} is missing thresholds")
    return float(thresholds.poor_boundary)


CTR_LOW_THRESHOLD = _poor("organic.ctr")
HIGH_IMPRESSIONS_THRESHOLD = _good("organic.impressions")
CTR_POSITION_MIN_THRESHOLD = 3.0
CTR_POSITION_MAX_THRESHOLD = 8.0
CTR_COMPETITOR_GAP_THRESHOLD = _poor("competitive.ctr_gap")

LCP_THRESHOLD_SECONDS = _good("cwv.lcp") / 1000.0
CLS_THRESHOLD = _good("cwv.cls")
INP_THRESHOLD_MS = _good("cwv.inp")
TTFB_THRESHOLD_MS = _good("web_vital.ttfb")
CWV_SEVERITY_CAP = 2.0
CWV_LCP_WEIGHT = 0.35
CWV_CLS_WEIGHT = 0.2
CWV_INP_WEIGHT = 0.25
CWV_TTFB_WEIGHT = 0.2
CWV_BASE_CONFIDENCE = 0.5
CWV_CONFIDENCE_MULTIPLIER = 0.5

GBP_REVIEW_VELOCITY_THRESHOLD = _good("local.review_velocity_30d")
GBP_REVIEW_RESPONSE_RATE_THRESHOLD = _poor("local.review_response_rate")
GBP_COMPETITOR_REVIEW_COUNT_GAP_THRESHOLD = _poor("local.review_count_gap")

RANKING_POSITION_DROP_THRESHOLD = _good("organic.position_delta")
RANKING_SEVERE_POSITION_DROP_THRESHOLD = _poor("organic.position_delta")
RANKING_TRAFFIC_DECLINE_THRESHOLD = _good("organic.traffic_growth")
RANKING_SEVERE_TRAFFIC_DECLINE_THRESHOLD = _poor("organic.traffic_growth")

COMPETITOR_REQUIRED_SIGNAL_MIN_COUNT = 2
COMPETITOR_RATING_GAP_THRESHOLD = _poor("competitive.rating_gap")
COMPETITOR_POSITION_GAP_THRESHOLD = _poor("competitive.position_gap")

DIAGNOSTIC_CONFIDENCE_LOW = 0.55
DIAGNOSTIC_CONFIDENCE_MEDIUM = 0.7
DIAGNOSTIC_CONFIDENCE_HIGH = 0.85
LOW_PRIORITY_SIGNAL_MAGNITUDE = 0.1
MEDIUM_PRIORITY_SIGNAL_MAGNITUDE = 0.5
HIGH_PRIORITY_SIGNAL_MAGNITUDE = 0.8
