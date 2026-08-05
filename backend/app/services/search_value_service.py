from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion


FORMULA_VERSION = "search-value-2026-08-v1"
CTR_MODEL_VERSION = "blended-organic-ctr-2026-08-v1"
CURRENCY = "USD"
HISTORY_LIMIT = 13
GSC_OBSERVATION_DAYS = Decimal("90")
MONTH_DAYS = Decimal("30")
MIN_GSC_IMPRESSIONS = 10
FRESH_DAYS = 45
WITHHOLD_DAYS = 90
MONEY = Decimal("0.01")
ZERO = Decimal("0")

# A deliberately conservative, device-blended curve. Positions outside the
# first page retain a small non-zero rate so the model never invents page-one
# traffic for a phrase that is currently far from the top.
CTR_CURVE: dict[int, Decimal] = {
    1: Decimal("0.275"),
    2: Decimal("0.153"),
    3: Decimal("0.107"),
    4: Decimal("0.078"),
    5: Decimal("0.060"),
    6: Decimal("0.046"),
    7: Decimal("0.035"),
    8: Decimal("0.027"),
    9: Decimal("0.021"),
    10: Decimal("0.016"),
}


def build_search_value(
    db: Session,
    *,
    campaign_id: str,
    tenant_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a customer-auditable estimate from immutable research runs.

    This function performs no provider calls. It intentionally reuses the
    snapshots already purchased by keyword research and can therefore be
    recomputed without consuming additional Insight Credits.
    """

    resolved_now = _as_utc(now or datetime.now(UTC))
    runs = (
        db.query(KeywordResearchRun)
        .filter(
            KeywordResearchRun.tenant_id == tenant_id,
            KeywordResearchRun.campaign_id == campaign_id,
            KeywordResearchRun.status.in_(("complete", "partial")),
        )
        .order_by(KeywordResearchRun.created_at.desc(), KeywordResearchRun.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    if not runs:
        return _empty_payload(campaign_id)

    summaries = [
        _summarize_run(db, run=run, now=resolved_now, include_keywords=index == 0)
        for index, run in enumerate(runs)
    ]
    current = summaries[0]
    previous = summaries[1] if len(summaries) > 1 else None
    history = [
        {
            "run_id": summary["run_id"],
            "saved_at": summary["saved_at"],
            "status": summary["estimate"]["status"],
            "central": summary["estimate"]["central"],
            "lower": summary["estimate"]["lower"],
            "upper": summary["estimate"]["upper"],
            "coverage_percent": summary["coverage"]["percent"],
            "measured_share_percent": summary["source_split"]["measured_share_percent"],
            "confidence": summary["confidence"]["level"],
            "formula_version": FORMULA_VERSION,
        }
        for summary in reversed(summaries)
    ]

    comparison = _comparison(current, previous) if previous else None
    estimate = dict(current["estimate"])
    estimate["change_from_previous"] = comparison["change"] if comparison else None
    estimate["change_percent"] = comparison["change_percent"] if comparison else None

    return {
        "campaign_id": campaign_id,
        "status": estimate["status"],
        "formula_version": FORMULA_VERSION,
        "ctr_model_version": CTR_MODEL_VERSION,
        "currency": CURRENCY,
        "scope": current["scope"],
        "research": current["research"],
        "estimate": estimate,
        "coverage": current["coverage"],
        "confidence": current["confidence"],
        "source_split": current["source_split"],
        "comparison": comparison,
        "history": history,
        "keywords": current["keywords"],
        "input_hash": current["input_hash"],
        "explanation": (
            "This estimates what similar visibility could cost in paid search. "
            "It is not revenue, profit, leads, or a promise of results."
        ),
        "caveats": [
            "Search Console clicks are normalized from the saved 90-day query window to a 30-day month.",
            "Where measured clicks are unavailable, a versioned position-based click model fills the gap and is labeled modeled.",
            "Only confirmed useful phrases with saved ad-cost research are counted.",
            "Saved research is reused; opening this page does not purchase another market-data check.",
        ],
    }


def _summarize_run(
    db: Session,
    *,
    run: KeywordResearchRun,
    now: datetime,
    include_keywords: bool,
) -> dict[str, Any]:
    rows = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.tenant_id == run.tenant_id,
            KeywordResearchSuggestion.campaign_id == run.campaign_id,
            KeywordResearchSuggestion.run_id == run.id,
            KeywordResearchSuggestion.dismissed_at.is_(None),
            KeywordResearchSuggestion.relevance_status == "relevant",
        )
        .order_by(
            KeywordResearchSuggestion.opportunity_score.desc(),
            KeywordResearchSuggestion.normalized_keyword.asc(),
        )
        .all()
    )

    # The database already enforces one normalized phrase per run. Keeping the
    # explicit map here makes the aggregation rule auditable and protects
    # historical imports that may predate that constraint.
    deduped: dict[str, KeywordResearchSuggestion] = {}
    for row in rows:
        current = deduped.get(row.normalized_keyword)
        if current is None or row.opportunity_score > current.opportunity_score:
            deduped[row.normalized_keyword] = row
    relevant_rows = list(deduped.values())

    contributions = [_keyword_contribution(row, run=run) for row in relevant_rows]
    eligible = [item for item in contributions if item["central_decimal"] is not None]
    saved_at = _as_utc(run.completed_at or run.created_at)
    age_days = max(0, (now.date() - saved_at.date()).days)
    stale = age_days > FRESH_DAYS
    withheld = age_days > WITHHOLD_DAYS

    central = sum((item["central_decimal"] for item in eligible), ZERO)
    lower = sum((item["lower_decimal"] for item in eligible), ZERO)
    upper = sum((item["upper_decimal"] for item in eligible), ZERO)
    possible_central = sum((item["possible_central_decimal"] for item in eligible), ZERO)
    possible_lower = sum((item["possible_lower_decimal"] for item in eligible), ZERO)
    possible_upper = sum((item["possible_upper_decimal"] for item in eligible), ZERO)
    status = "unavailable" if not eligible else "withheld" if withheld else "available"

    measured = [item for item in eligible if item["click_method"] == "measured"]
    modeled = [item for item in eligible if item["click_method"] == "modeled"]
    measured_value = sum((item["central_decimal"] for item in measured), ZERO)
    modeled_value = sum((item["central_decimal"] for item in modeled), ZERO)
    measured_share = _percent(measured_value, central)
    modeled_share = _percent(modeled_value, central)
    coverage_percent = _percent(Decimal(len(eligible)), Decimal(len(relevant_rows)))
    confidence = _confidence(
        eligible_count=len(eligible),
        relevant_count=len(relevant_rows),
        measured_share=measured_share,
        age_days=age_days,
        status=status,
    )

    input_rows = [
        {
            "keyword": row.normalized_keyword,
            "cpc": str(row.cpc) if row.cpc is not None else None,
            "search_volume": row.search_volume,
            "position": row.current_position if row.current_position is not None else row.gsc_position,
            "gsc_clicks": row.gsc_clicks,
            "gsc_impressions": row.gsc_impressions,
            "source_updated_at": row.source_updated_at.isoformat() if row.source_updated_at else None,
        }
        for row in sorted(relevant_rows, key=lambda item: item.normalized_keyword)
    ]
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "formula_version": FORMULA_VERSION,
                "ctr_model_version": CTR_MODEL_VERSION,
                "run_id": run.id,
                "inputs": input_rows,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "run_id": run.id,
        "saved_at": saved_at.isoformat(),
        "scope": {
            "business_location_id": run.business_location_id,
            "location_name": run.location_name,
            "language_code": run.language_code,
            "device": "all devices",
        },
        "research": {
            "run_id": run.id,
            "saved_at": saved_at.isoformat(),
            "age_days": age_days,
            "freshness": "current" if age_days <= FRESH_DAYS else "old",
            "source": "Saved market research and Search Console",
            "new_paid_check_required": False,
        },
        "estimate": {
            "status": status,
            "central": _money_string(central) if status == "available" else None,
            "lower": _money_string(lower) if status == "available" else None,
            "upper": _money_string(upper) if status == "available" else None,
            "possible_central": _money_string(possible_central) if status == "available" else None,
            "possible_lower": _money_string(possible_lower) if status == "available" else None,
            "possible_upper": _money_string(possible_upper) if status == "available" else None,
            "upside": _money_string(max(ZERO, possible_central - central)) if status == "available" else None,
        },
        "coverage": {
            "confirmed_phrases": len(relevant_rows),
            "valued_phrases": len(eligible),
            "percent": coverage_percent,
            "missing_market_data": max(0, len(relevant_rows) - len(eligible)),
        },
        "confidence": confidence,
        "source_split": {
            "measured_value": _money_string(measured_value) if status == "available" else None,
            "modeled_value": _money_string(modeled_value) if status == "available" else None,
            "measured_share_percent": measured_share,
            "modeled_share_percent": modeled_share,
            "measured_phrase_count": len(measured),
            "modeled_phrase_count": len(modeled),
        },
        "keywords": [_public_keyword(item, withheld=withheld) for item in eligible]
        if include_keywords
        else [],
        "inputs": {item["normalized_keyword"]: item for item in eligible},
        "input_hash": input_hash,
        "stale": stale,
    }


def _keyword_contribution(
    row: KeywordResearchSuggestion,
    *,
    run: KeywordResearchRun,
) -> dict[str, Any]:
    cpc = Decimal(str(row.cpc)) if row.cpc is not None else None
    position_value = row.current_position if row.current_position is not None else row.gsc_position
    position = float(position_value) if position_value is not None else None
    source_types = set(row.source_types if isinstance(row.source_types, list) else [])
    has_measured_query = (
        "google_search_console" in source_types
        and row.gsc_clicks is not None
        and int(row.gsc_impressions or 0) >= MIN_GSC_IMPRESSIONS
    )

    clicks: Decimal | None = None
    click_method: str | None = None
    if cpc is not None and cpc > ZERO and has_measured_query:
        clicks = max(ZERO, Decimal(str(row.gsc_clicks or 0))) * MONTH_DAYS / GSC_OBSERVATION_DAYS
        click_method = "measured"
    elif (
        cpc is not None
        and cpc > ZERO
        and row.search_volume is not None
        and row.search_volume >= 0
        and position is not None
    ):
        clicks = Decimal(row.search_volume) * _ctr(position)
        click_method = "modeled"

    central = clicks * cpc if clicks is not None and cpc is not None else None
    uncertainty = Decimal("0.10") if click_method == "measured" else Decimal("0.30")
    lower = central * (Decimal("1") - uncertainty) if central is not None else None
    upper = central * (Decimal("1") + uncertainty) if central is not None else None

    target_position = _target_position(position)
    target_clicks = (
        Decimal(row.search_volume or 0) * _ctr(target_position)
        if target_position is not None and row.search_volume is not None
        else None
    )
    target_value = target_clicks * cpc if target_clicks is not None and cpc is not None else None
    possible_central = max(central or ZERO, target_value or ZERO) if central is not None else None
    possible_lower = (
        max(lower or ZERO, (target_value or ZERO) * Decimal("0.70"))
        if possible_central is not None
        else None
    )
    possible_upper = (
        max(upper or ZERO, (target_value or ZERO) * Decimal("1.30"))
        if possible_central is not None
        else None
    )
    source_date = row.source_updated_at or run.completed_at or run.created_at

    return {
        "id": row.id,
        "normalized_keyword": row.normalized_keyword,
        "keyword": row.keyword,
        "position": round(position, 1) if position is not None else None,
        "target_position": target_position,
        "search_volume": row.search_volume,
        "clicks": float(clicks.quantize(Decimal("0.01"))) if clicks is not None else None,
        "click_method": click_method,
        "cpc": _money_string(cpc) if cpc is not None else None,
        "central_decimal": central,
        "lower_decimal": lower,
        "upper_decimal": upper,
        "possible_central_decimal": possible_central,
        "possible_lower_decimal": possible_lower,
        "possible_upper_decimal": possible_upper,
        "source_date": _as_utc(source_date).isoformat(),
        "service": row.matched_service_name,
        "location": row.matched_service_area_name or run.location_name,
    }


def _public_keyword(item: dict[str, Any], *, withheld: bool) -> dict[str, Any]:
    return {
        "id": item["id"],
        "keyword": item["keyword"],
        "position": item["position"],
        "target_position": item["target_position"],
        "search_volume": item["search_volume"],
        "clicks": item["clicks"],
        "click_method": item["click_method"],
        "cpc": item["cpc"],
        "contribution": None if withheld else _money_string(item["central_decimal"]),
        "contribution_lower": None if withheld else _money_string(item["lower_decimal"]),
        "contribution_upper": None if withheld else _money_string(item["upper_decimal"]),
        "possible_contribution": (
            None if withheld else _money_string(item["possible_central_decimal"])
        ),
        "source": (
            "Search Console clicks + saved market research"
            if item["click_method"] == "measured"
            else "Position model + saved market research"
        ),
        "source_date": item["source_date"],
        "service": item["service"],
        "location": item["location"],
    }


def _comparison(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    current_value = _optional_decimal(current["estimate"]["central"])
    previous_value = _optional_decimal(previous["estimate"]["central"])
    change = current_value - previous_value if current_value is not None and previous_value is not None else None
    change_percent = (
        (change / previous_value * Decimal("100"))
        if change is not None and previous_value is not None and previous_value > ZERO
        else None
    )
    return {
        "previous_run_id": previous["run_id"],
        "previous_saved_at": previous["saved_at"],
        "previous_value": _money_string(previous_value) if previous_value is not None else None,
        "change": _signed_money_string(change) if change is not None else None,
        "change_percent": round(float(change_percent), 1) if change_percent is not None else None,
        "signals": _change_signals(current, previous),
        "formula_changed": False,
    }


def _change_signals(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, Any]]:
    current_inputs = current["inputs"]
    previous_inputs = previous["inputs"]
    shared = sorted(set(current_inputs) & set(previous_inputs))

    current_positions = [current_inputs[key]["position"] for key in shared if current_inputs[key]["position"] is not None]
    previous_positions = [previous_inputs[key]["position"] for key in shared if previous_inputs[key]["position"] is not None]
    position_delta = None
    if current_positions and previous_positions and len(current_positions) == len(previous_positions):
        position_delta = round(
            sum(previous_positions) / len(previous_positions)
            - sum(current_positions) / len(current_positions),
            1,
        )

    demand_delta = sum(int(current_inputs[key]["search_volume"] or 0) for key in shared) - sum(
        int(previous_inputs[key]["search_volume"] or 0) for key in shared
    )
    current_cpcs = [Decimal(str(current_inputs[key]["cpc"])) for key in shared if current_inputs[key]["cpc"]]
    previous_cpcs = [Decimal(str(previous_inputs[key]["cpc"])) for key in shared if previous_inputs[key]["cpc"]]
    cpc_delta = None
    if current_cpcs and previous_cpcs:
        cpc_delta = sum(current_cpcs, ZERO) / len(current_cpcs) - sum(previous_cpcs, ZERO) / len(previous_cpcs)

    coverage_delta = current["coverage"]["valued_phrases"] - previous["coverage"]["valued_phrases"]
    return [
        {
            "key": "rankings",
            "label": "Search positions",
            "direction": _direction(position_delta),
            "detail": (
                "Average position improved by " + str(abs(position_delta))
                if position_delta and position_delta > 0
                else "Average position slipped by " + str(abs(position_delta))
                if position_delta and position_delta < 0
                else "No clear position change in matching phrases"
            ),
        },
        {
            "key": "demand",
            "label": "Search demand",
            "direction": _direction(demand_delta),
            "detail": f"{abs(demand_delta):,} more monthly searches" if demand_delta > 0 else f"{abs(demand_delta):,} fewer monthly searches" if demand_delta < 0 else "No clear demand change",
        },
        {
            "key": "cpc",
            "label": "Typical ad cost",
            "direction": _direction(cpc_delta),
            "detail": f"Average researched ad cost changed by {_signed_money_string(cpc_delta)}" if cpc_delta else "No clear ad-cost change",
        },
        {
            "key": "coverage",
            "label": "Data coverage",
            "direction": _direction(coverage_delta),
            "detail": f"{abs(coverage_delta)} more valued phrases" if coverage_delta > 0 else f"{abs(coverage_delta)} fewer valued phrases" if coverage_delta < 0 else "The same number of phrases had enough data",
        },
        {
            "key": "model",
            "label": "Calculation method",
            "direction": "same",
            "detail": f"Formula stayed on {FORMULA_VERSION}",
        },
    ]


def _confidence(
    *,
    eligible_count: int,
    relevant_count: int,
    measured_share: float,
    age_days: int,
    status: str,
) -> dict[str, Any]:
    if status == "unavailable":
        return {
            "level": "low",
            "score": 0,
            "reasons": ["No confirmed phrase has both saved ad-cost research and usable click or position data."],
        }
    if status == "withheld":
        return {
            "level": "low",
            "score": 10,
            "reasons": [f"The latest saved research is {age_days} days old, so the dollar estimate is withheld."],
        }
    coverage = eligible_count / max(1, relevant_count)
    freshness = max(0.0, 1.0 - age_days / FRESH_DAYS)
    row_depth = min(1.0, eligible_count / 10.0)
    score = round((coverage * 0.50 + freshness * 0.20 + row_depth * 0.15 + measured_share / 100 * 0.15) * 100)
    level = "high" if score >= 75 else "medium" if score >= 50 else "low"
    reasons = [
        f"{eligible_count} of {relevant_count} confirmed phrases have enough saved information.",
        f"{round(measured_share, 1)}% of the central estimate comes from measured Search Console clicks.",
        f"The saved research is {age_days} day{'s' if age_days != 1 else ''} old.",
    ]
    return {"level": level, "score": score, "reasons": reasons}


def _empty_payload(campaign_id: str) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "status": "unavailable",
        "formula_version": FORMULA_VERSION,
        "ctr_model_version": CTR_MODEL_VERSION,
        "currency": CURRENCY,
        "scope": {"business_location_id": None, "location_name": None, "language_code": "en", "device": "all devices"},
        "research": {"run_id": None, "saved_at": None, "age_days": None, "freshness": "missing", "source": "Saved market research and Search Console", "new_paid_check_required": False},
        "estimate": {"status": "unavailable", "central": None, "lower": None, "upper": None, "possible_central": None, "possible_lower": None, "possible_upper": None, "upside": None, "change_from_previous": None, "change_percent": None},
        "coverage": {"confirmed_phrases": 0, "valued_phrases": 0, "percent": 0.0, "missing_market_data": 0},
        "confidence": {"level": "low", "score": 0, "reasons": ["Run customer search research for this location before estimating search value."]},
        "source_split": {"measured_value": None, "modeled_value": None, "measured_share_percent": 0.0, "modeled_share_percent": 0.0, "measured_phrase_count": 0, "modeled_phrase_count": 0},
        "comparison": None,
        "history": [],
        "keywords": [],
        "input_hash": None,
        "explanation": "No estimate is shown until this location has confirmed phrases and saved market research.",
        "caveats": ["Search Value never substitutes an unsourced manual dollar estimate."],
    }


def _ctr(position: float) -> Decimal:
    rank = max(1, int(math.ceil(position)))
    if rank <= 10:
        return CTR_CURVE[rank]
    if rank <= 20:
        return Decimal("0.008")
    if rank <= 50:
        return Decimal("0.003")
    if rank <= 100:
        return Decimal("0.001")
    return ZERO


def _target_position(position: float | None) -> float | None:
    if position is None:
        return None
    return float(max(1, math.ceil(position) - 2))


def _money_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), "f")


def _signed_money_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.quantize(MONEY, rounding=ROUND_HALF_UP)
    return f"{normalized:+.2f}"


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _percent(numerator: Decimal, denominator: Decimal) -> float:
    if denominator <= ZERO:
        return 0.0
    return round(float(numerator / denominator * Decimal("100")), 1)


def _direction(value: Decimal | float | int | None) -> str:
    if value is None or value == 0:
        return "same"
    return "up" if value > 0 else "down"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
