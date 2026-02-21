from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

CANONICAL_SIGNAL_FIELDS: frozenset[str] = frozenset(
    {
        "clicks",
        "impressions",
        "ctr",
        "avg_position",
        "position_delta",
        "traffic_growth_percent",
        "sessions",
        "conversions",
        "profile_views",
        "direction_requests",
        "phone_calls",
        "photo_views",
        "review_count",
        "review_velocity",
        "avg_rating",
        "review_response_rate",
        "lcp",
        "cls",
        "inp",
        "ttfb",
        "index_coverage_errors",
        "crawl_errors",
        "mobile_usability_errors",
        "structured_data_present",
        "duplicate_title_flag",
        "cannibalization_flag",
        "competitor_avg_position",
        "competitor_ctr_estimate",
        "competitor_lcp",
        "competitor_word_count",
        "competitor_schema_presence",
        "competitor_review_count",
        "competitor_rating",
    }
)

SIGNAL_ALIASES: dict[str, str] = {
    "gbp_total_views": "profile_views",
    "gbp_direction_requests": "direction_requests",
    "gbp_calls": "phone_calls",
    "gbp_photo_views": "photo_views",
    "total_reviews": "review_count",
    "review_velocity_90d": "review_velocity",
    "average_rating": "avg_rating",
    "competitor_average_rating": "competitor_rating",
    "LCP": "lcp",
    "CLS": "cls",
    "INP": "inp",
    "TTFB": "ttfb",
}


class StrategyEngineSignals(BaseModel):
    """Canonical deterministic signal model consumed by downstream diagnostics."""

    model_config = ConfigDict(extra="forbid")

    clicks: float | None = Field(default=None, ge=0)
    impressions: float | None = Field(default=None, ge=0)
    ctr: float | None = Field(default=None, ge=0, le=1)
    avg_position: float | None = Field(default=None, ge=0)
    position_delta: float | None = None
    traffic_growth_percent: float | None = None
    sessions: float | None = Field(default=None, ge=0)
    conversions: float | None = Field(default=None, ge=0)

    profile_views: float | None = Field(default=None, ge=0)
    direction_requests: float | None = Field(default=None, ge=0)
    phone_calls: float | None = Field(default=None, ge=0)
    photo_views: float | None = Field(default=None, ge=0)
    review_count: float | None = Field(default=None, ge=0)
    review_velocity: float | None = Field(default=None, ge=0)
    avg_rating: float | None = Field(default=None, ge=0, le=5)
    review_response_rate: float | None = Field(default=None, ge=0, le=1)

    lcp: float | None = Field(default=None, ge=0)
    cls: float | None = Field(default=None, ge=0)
    inp: float | None = Field(default=None, ge=0)
    ttfb: float | None = Field(default=None, ge=0)

    index_coverage_errors: float | None = Field(default=None, ge=0)
    crawl_errors: float | None = Field(default=None, ge=0)
    mobile_usability_errors: float | None = Field(default=None, ge=0)
    structured_data_present: bool | None = None
    duplicate_title_flag: bool | None = None
    cannibalization_flag: bool | None = None

    competitor_avg_position: float | None = Field(default=None, ge=0)
    competitor_ctr_estimate: float | None = Field(default=None, ge=0, le=1)
    competitor_lcp: float | None = Field(default=None, ge=0)
    competitor_word_count: float | None = Field(default=None, ge=0)
    competitor_schema_presence: bool | None = None
    competitor_review_count: float | None = Field(default=None, ge=0)
    competitor_rating: float | None = Field(default=None, ge=0, le=5)

    @field_validator("clicks", "impressions", mode="after")
    @classmethod
    def _clicks_impressions_integrity(cls, value: float | None) -> float | None:
        return value


def normalize_signal_payload(raw_signals: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize raw signals into canonical names.

    Raises:
        ValueError: if unknown signal names are encountered.
    """
    normalized: dict[str, Any] = {}
    unknown_fields: list[str] = []

    for key, value in raw_signals.items():
        canonical_key = SIGNAL_ALIASES.get(key, key)
        if canonical_key not in CANONICAL_SIGNAL_FIELDS:
            unknown_fields.append(key)
            continue
        normalized[canonical_key] = value

    if unknown_fields:
        raise ValueError(f"Unknown signal fields: {sorted(unknown_fields)}")

    return normalized


def build_signal_model(raw_signals: dict[str, Any]) -> StrategyEngineSignals:
    """Build and validate the canonical signal model from a raw payload."""
    normalized = normalize_signal_payload(raw_signals)
    return StrategyEngineSignals.model_validate(normalized)

