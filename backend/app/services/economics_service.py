from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.keyword_daily_economics import KeywordDailyEconomics
from app.models.rank import CampaignKeyword, Ranking
from app.services import market_snapshot_service

CTR_MODEL_VERSION = "ctr-v1"
DEFAULT_DEVICE_CLASS = "desktop"
DEFAULT_GEO_SCOPE = "US"
DECIMAL_ZERO = Decimal("0.00")
CONFIDENCE_WEIGHT = Decimal("0.80")
_MONEY_QUANTIZER = Decimal("0.01")
_CTR_CURVES: dict[str, dict[str, dict[int, Decimal]]] = {
    CTR_MODEL_VERSION: {
        "desktop": {
            1: Decimal("0.285000"),
            2: Decimal("0.157000"),
            3: Decimal("0.110000"),
            4: Decimal("0.080000"),
            5: Decimal("0.061000"),
            6: Decimal("0.047000"),
            7: Decimal("0.036000"),
            8: Decimal("0.028000"),
            9: Decimal("0.022000"),
            10: Decimal("0.017000"),
        },
        "mobile": {
            1: Decimal("0.265000"),
            2: Decimal("0.149000"),
            3: Decimal("0.104000"),
            4: Decimal("0.076000"),
            5: Decimal("0.058000"),
            6: Decimal("0.044000"),
            7: Decimal("0.034000"),
            8: Decimal("0.026000"),
            9: Decimal("0.020000"),
            10: Decimal("0.015000"),
        },
    }
}


@dataclass(frozen=True)
class KeywordEconomicsInput:
    campaign_id: str
    keyword_id: str
    metric_date: date
    search_volume: int
    cpc: Decimal
    rank: float
    device_class: str = DEFAULT_DEVICE_CLASS
    ctr_model_version: str = CTR_MODEL_VERSION

class Scenario(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    DOMINANT = "DOMINANT"

@dataclass(frozen=True)
class KeywordEconomicsSimulation:
    keyword_id: str
    target_rank: float
    projected_clicks: int
    projected_value: Decimal
    delta_value: Decimal
    opportunity_gap: Decimal
    ctr_model_version: str


def get_ctr_curve(version: str = CTR_MODEL_VERSION, *, device_class: str = DEFAULT_DEVICE_CLASS) -> dict[int, Decimal]:
    version_key = str(version).strip()
    device_key = str(device_class).strip().lower()
    try:
        return _CTR_CURVES[version_key][device_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported CTR configuration: version={version_key}, device_class={device_key}") from exc


def ctr_for_rank(rank: float, *, device_class: str = DEFAULT_DEVICE_CLASS, ctr_model_version: str = CTR_MODEL_VERSION) -> Decimal:
    curve = get_ctr_curve(ctr_model_version, device_class=device_class)
    normalized_rank = _normalize_rank(rank)
    if normalized_rank <= 10:
        return curve[normalized_rank]
    floor_ctr = curve[10]
    decay_steps = normalized_rank - 10
    decayed = floor_ctr * (Decimal("0.85") ** decay_steps)
    return max(Decimal("0.001000"), decayed.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def calculate_estimated_clicks(search_volume: int, rank: float, *, device_class: str = DEFAULT_DEVICE_CLASS, ctr_model_version: str = CTR_MODEL_VERSION) -> int:
    ctr = ctr_for_rank(rank, device_class=device_class, ctr_model_version=ctr_model_version)
    estimated = Decimal(max(0, int(search_volume))) * ctr
    return int(estimated.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_paid_equivalent_value(estimated_clicks: int, cpc: Decimal) -> Decimal:
    safe_clicks = max(0, int(estimated_clicks))
    safe_cpc = _quantize_money(cpc)
    return (Decimal(safe_clicks) * safe_cpc).quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def normalize_keyword_daily_economics(metric_input: KeywordEconomicsInput) -> dict[str, object]:
    search_volume = max(0, int(metric_input.search_volume))
    cpc = _quantize_money(metric_input.cpc)
    ctr = ctr_for_rank(
        metric_input.rank,
        device_class=metric_input.device_class,
        ctr_model_version=metric_input.ctr_model_version,
    )
    estimated_clicks = int((Decimal(search_volume) * ctr).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    paid_equivalent_value = calculate_paid_equivalent_value(estimated_clicks, cpc)
    ctr_model_label = _ctr_model_label(metric_input.ctr_model_version, metric_input.device_class)
    payload = {
        "campaign_id": metric_input.campaign_id,
        "keyword_id": metric_input.keyword_id,
        "metric_date": metric_input.metric_date.isoformat(),
        "search_volume": search_volume,
        "cpc": _decimal_to_str(cpc),
        "estimated_clicks": estimated_clicks,
        "paid_equivalent_value": _decimal_to_str(paid_equivalent_value),
        "ctr_model_version": ctr_model_label,
    }
    return {
        **payload,
        "deterministic_hash": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }


def build_keyword_economics_input_from_ranking(
    db: Session,
    *,
    keyword_id: str,
    metric_date: date,
    geo_scope: str = DEFAULT_GEO_SCOPE,
    device_class: str = DEFAULT_DEVICE_CLASS,
    ctr_model_version: str = CTR_MODEL_VERSION,
) -> KeywordEconomicsInput:
    row = (
        db.query(Ranking, CampaignKeyword)
        .join(CampaignKeyword, CampaignKeyword.id == Ranking.keyword_id)
        .filter(Ranking.keyword_id == keyword_id)
        .first()
    )
    if row is None:
        raise ValueError("Ranking not found for keyword_id")

    snapshot = market_snapshot_service.get_latest_keyword_market_snapshot(
        db,
        keyword_id=keyword_id,
        geo_scope=geo_scope,
        device_class=device_class,
        on_or_before=metric_date,
    )
    if snapshot is None:
        raise ValueError("Keyword market snapshot not found for keyword_id")

    ranking, keyword = row
    return KeywordEconomicsInput(
        campaign_id=keyword.campaign_id,
        keyword_id=keyword.id,
        metric_date=metric_date,
        search_volume=int(snapshot.search_volume),
        cpc=_quantize_money(snapshot.avg_cpc),
        rank=float(ranking.current_position),
        device_class=str(snapshot.device_class).lower(),
        ctr_model_version=ctr_model_version,
    )


def upsert_keyword_daily_economics(db: Session, metric_input: KeywordEconomicsInput) -> KeywordDailyEconomics:
    normalized = normalize_keyword_daily_economics(metric_input)
    row = (
        db.query(KeywordDailyEconomics)
        .filter(
            KeywordDailyEconomics.keyword_id == metric_input.keyword_id,
            KeywordDailyEconomics.metric_date == metric_input.metric_date,
        )
        .first()
    )
    if row is None:
        row = KeywordDailyEconomics(
            campaign_id=metric_input.campaign_id,
            keyword_id=metric_input.keyword_id,
            metric_date=metric_input.metric_date,
            search_volume=int(normalized["search_volume"]),
            cpc=Decimal(str(normalized["cpc"])),
            estimated_clicks=int(normalized["estimated_clicks"]),
            paid_equivalent_value=Decimal(str(normalized["paid_equivalent_value"])),
            ctr_model_version=str(normalized["ctr_model_version"]),
            deterministic_hash=str(normalized["deterministic_hash"]),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    if row.deterministic_hash == normalized["deterministic_hash"]:
        return row

    row.campaign_id = metric_input.campaign_id
    row.search_volume = int(normalized["search_volume"])
    row.cpc = Decimal(str(normalized["cpc"]))
    row.estimated_clicks = int(normalized["estimated_clicks"])
    row.paid_equivalent_value = Decimal(str(normalized["paid_equivalent_value"]))
    row.ctr_model_version = str(normalized["ctr_model_version"])
    row.deterministic_hash = str(normalized["deterministic_hash"])
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


def simulate_rank(
    db: Session,
    keyword_id: str,
    target_rank: float,
    *,
    geo_scope: str = DEFAULT_GEO_SCOPE,
    device_class: str = DEFAULT_DEVICE_CLASS,
) -> dict[str, object]:
    ranking = db.query(Ranking).filter(Ranking.keyword_id == keyword_id).first()
    if ranking is None:
        raise ValueError("Ranking not found for keyword_id")

    snapshot = market_snapshot_service.get_latest_keyword_market_snapshot(
        db,
        keyword_id=keyword_id,
        geo_scope=geo_scope,
        device_class=device_class,
        on_or_before=date.max,
    )
    if snapshot is None:
        raise ValueError("Keyword market snapshot not found for keyword_id")

    current_clicks = calculate_estimated_clicks(
        snapshot.search_volume,
        float(ranking.current_position),
        device_class=str(snapshot.device_class).lower(),
        ctr_model_version=CTR_MODEL_VERSION,
    )
    current_value = calculate_paid_equivalent_value(current_clicks, snapshot.avg_cpc)
    projected_clicks = calculate_estimated_clicks(
        snapshot.search_volume,
        target_rank,
        device_class=str(snapshot.device_class).lower(),
        ctr_model_version=CTR_MODEL_VERSION,
    )
    projected_value = calculate_paid_equivalent_value(projected_clicks, snapshot.avg_cpc)
    delta_value = (projected_value - current_value).quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    opportunity_gap = max(DECIMAL_ZERO, delta_value)
    simulation = KeywordEconomicsSimulation(
        keyword_id=keyword_id,
        target_rank=float(target_rank),
        projected_clicks=projected_clicks,
        projected_value=projected_value,
        delta_value=delta_value,
        opportunity_gap=opportunity_gap,
        ctr_model_version=_ctr_model_label(CTR_MODEL_VERSION, snapshot.device_class),
    )
    return {
        "keyword_id": simulation.keyword_id,
        "target_rank": simulation.target_rank,
        "projected_clicks": simulation.projected_clicks,
        "projected_value": simulation.projected_value,
        "delta_value": simulation.delta_value,
        "opportunity_gap": simulation.opportunity_gap,
        "ctr_model_version": simulation.ctr_model_version,
        "current_rank": float(ranking.current_position),
        "snapshot_date": snapshot.snapshot_date.isoformat(),
    }


def current_organic_media_value(db: Session, campaign_id: str) -> dict[str, object]:
    rows = _latest_campaign_keyword_economics_rows(db, campaign_id)
    return {
        "campaign_id": campaign_id,
        "current_value": _sum_paid_values(rows),
        "keyword_count": len(rows),
        "as_of": _latest_metric_date(rows),
    }


def projected_value_if_rank_improves(db: Session, campaign_id: str) -> dict[str, object]:
    rows = _latest_campaign_keyword_economics_rows(db, campaign_id)
    current_value = _sum_paid_values(rows)
    projections = [_project_row_if_rank_improves(row) for row in rows]
    projected_value = sum((projection["projected_value"] for projection in projections), DECIMAL_ZERO)
    value_delta = (projected_value - current_value).quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    return {
        "campaign_id": campaign_id,
        "current_value": current_value,
        "projected_value": projected_value,
        "value_delta": value_delta,
        "keyword_count": len(rows),
        "as_of": _latest_metric_date(rows),
    }



def projected_value_for_scenario(db: Session, campaign_id: str, scenario: Scenario | str) -> dict[str, object]:
    resolved_scenario = scenario if isinstance(scenario, Scenario) else Scenario(str(scenario).strip().upper())
    rows = _latest_campaign_keyword_economics_rows(db, campaign_id)
    current_value = _sum_paid_values(rows)
    projections = [_project_row_for_scenario(row, resolved_scenario) for row in rows]
    projected_value = sum((projection["projected_value"] for projection in projections), DECIMAL_ZERO)
    value_delta = (projected_value - current_value).quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    percentage_lift = _calculate_percentage_lift(current_value, value_delta)
    return {
        "campaign_id": campaign_id,
        "scenario": resolved_scenario.value,
        "current_value": current_value,
        "projected_value": projected_value,
        "delta": value_delta,
        "percentage_lift": percentage_lift,
        "confidence_weight": CONFIDENCE_WEIGHT,
        "keyword_count": len(rows),
        "as_of": _latest_metric_date(rows),
    }

def top_keywords_by_value(db: Session, campaign_id: str, *, limit: int = 5) -> list[dict[str, object]]:
    rows = _latest_campaign_keyword_economics_rows(db, campaign_id)
    bounded_limit = max(0, int(limit))
    payload: list[dict[str, object]] = []
    for row in rows[:bounded_limit]:
        payload.append(
            {
                "keyword_id": row.keyword_id,
                "metric_date": row.metric_date,
                "current_value": row.paid_equivalent_value,
                "estimated_clicks": row.estimated_clicks,
                "search_volume": row.search_volume,
                "cpc": _quantize_money(row.cpc),
                "ctr_model_version": row.ctr_model_version,
            }
        )
    return payload


def highest_opportunity_gap_keywords(db: Session, campaign_id: str, *, limit: int = 5) -> list[dict[str, object]]:
    rows = _latest_campaign_keyword_economics_rows(db, campaign_id)
    bounded_limit = max(0, int(limit))
    projections = [_project_row_if_rank_improves(row) for row in rows]
    ordered = sorted(
        projections,
        key=lambda item: (-item["opportunity_gap"], item["keyword_id"]),
    )
    return ordered[:bounded_limit]


def _latest_campaign_keyword_economics_rows(db: Session, campaign_id: str) -> list[KeywordDailyEconomics]:
    latest_dates = (
        db.query(
            KeywordDailyEconomics.keyword_id.label("keyword_id"),
            func.max(KeywordDailyEconomics.metric_date).label("metric_date"),
        )
        .filter(KeywordDailyEconomics.campaign_id == campaign_id)
        .group_by(KeywordDailyEconomics.keyword_id)
        .subquery()
    )
    return (
        db.query(KeywordDailyEconomics)
        .join(
            latest_dates,
            and_(
                KeywordDailyEconomics.keyword_id == latest_dates.c.keyword_id,
                KeywordDailyEconomics.metric_date == latest_dates.c.metric_date,
            ),
        )
        .filter(KeywordDailyEconomics.campaign_id == campaign_id)
        .order_by(KeywordDailyEconomics.paid_equivalent_value.desc(), KeywordDailyEconomics.keyword_id.asc())
        .all()
    )


def _project_row_if_rank_improves(row: KeywordDailyEconomics) -> dict[str, object]:
    current_rank = _infer_rank_from_economics_row(row)
    projected_rank = max(1, current_rank - 1)
    version, device_class = _parse_ctr_model_label(row.ctr_model_version)
    projected_clicks = calculate_estimated_clicks(
        row.search_volume,
        float(projected_rank),
        device_class=device_class,
        ctr_model_version=version,
    )
    projected_value = calculate_paid_equivalent_value(projected_clicks, row.cpc)
    delta_value = (projected_value - row.paid_equivalent_value).quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    opportunity_gap = max(DECIMAL_ZERO, delta_value)
    return {
        "keyword_id": row.keyword_id,
        "metric_date": row.metric_date,
        "current_rank": current_rank,
        "projected_rank": projected_rank,
        "current_value": row.paid_equivalent_value,
        "projected_value": projected_value,
        "delta_value": delta_value,
        "opportunity_gap": opportunity_gap,
        "ctr_model_version": row.ctr_model_version,
    }



def _project_row_for_scenario(row: KeywordDailyEconomics, scenario: Scenario) -> dict[str, object]:
    current_rank = _infer_rank_from_economics_row(row)
    projected_rank = _scenario_target_rank(current_rank, scenario)
    version, device_class = _parse_ctr_model_label(row.ctr_model_version)
    projected_clicks = calculate_estimated_clicks(
        row.search_volume,
        float(projected_rank),
        device_class=device_class,
        ctr_model_version=version,
    )
    projected_value = calculate_paid_equivalent_value(projected_clicks, row.cpc)
    delta_value = (projected_value - row.paid_equivalent_value).quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
    return {
        "keyword_id": row.keyword_id,
        "metric_date": row.metric_date,
        "current_rank": current_rank,
        "projected_rank": projected_rank,
        "current_value": row.paid_equivalent_value,
        "projected_value": projected_value,
        "delta": delta_value,
        "ctr_model_version": row.ctr_model_version,
    }


def _scenario_target_rank(current_rank: int, scenario: Scenario) -> int:
    if scenario is Scenario.CONSERVATIVE:
        return max(1, current_rank - 1)
    if scenario is Scenario.MODERATE:
        return max(1, current_rank - 2)
    if scenario is Scenario.STRONG:
        return current_rank if current_rank <= 3 else 3
    if scenario is Scenario.DOMINANT:
        return 1 if current_rank > 1 else current_rank
    return current_rank


def _calculate_percentage_lift(current_value: Decimal, value_delta: Decimal) -> Decimal:
    if current_value <= DECIMAL_ZERO:
        return DECIMAL_ZERO
    percentage = (value_delta / current_value) * Decimal("100.00")
    return percentage.quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)

def _sum_paid_values(rows: list[KeywordDailyEconomics]) -> Decimal:
    return sum((row.paid_equivalent_value for row in rows), DECIMAL_ZERO)


def _latest_metric_date(rows: list[KeywordDailyEconomics]) -> date | None:
    if not rows:
        return None
    return max(row.metric_date for row in rows)


def _infer_rank_from_economics_row(row: KeywordDailyEconomics) -> int:
    if row.search_volume <= 0:
        return 10
    version, device_class = _parse_ctr_model_label(row.ctr_model_version)
    actual_ctr = Decimal(row.estimated_clicks) / Decimal(row.search_volume)
    best_rank = 1
    best_delta: Decimal | None = None
    for rank in range(1, 51):
        candidate_ctr = ctr_for_rank(rank, device_class=device_class, ctr_model_version=version)
        delta = abs(candidate_ctr - actual_ctr)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_rank = rank
    return best_rank


def _parse_ctr_model_label(label: str) -> tuple[str, str]:
    parts = str(label).strip().split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1].lower()
    return parts[0], DEFAULT_DEVICE_CLASS

def replay_mode_enabled() -> bool:
    return os.getenv("LSOS_REPLAY_MODE", "").strip() == "1" or os.getenv("REPLAY_MODE", "").strip() == "1"


def _ctr_model_label(version: str, device_class: str) -> str:
    return f"{str(version).strip()}:{str(device_class).strip().lower()}"


def _normalize_rank(rank: float) -> int:
    safe_rank = Decimal(str(rank)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(1, int(safe_rank))


def _quantize_money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _decimal_to_str(value: Decimal) -> str:
    return format(value.quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP), "f")
