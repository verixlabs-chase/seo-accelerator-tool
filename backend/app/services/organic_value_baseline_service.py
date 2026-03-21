from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.rank import CampaignKeyword
from app.models.keyword_market_snapshot import KeywordMarketSnapshot
from app.services import economics_service, market_snapshot_service
from app.services import organic_value_baseline_settings_service

_MONEY = Decimal("0.01")
_RATIO = Decimal("0.01")
_SCORE = Decimal("0.01")
_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class _ScenarioDefinition:
    key: str
    label: str
    source: economics_service.Scenario
    target_rank_rule: str


_SCENARIOS: tuple[_ScenarioDefinition, ...] = (
    _ScenarioDefinition(
        key="conservative",
        label="Conservative",
        source=economics_service.Scenario.CONSERVATIVE,
        target_rank_rule="Assumes roughly a one-position improvement for tracked keywords.",
    ),
    _ScenarioDefinition(
        key="expected",
        label="Expected",
        source=economics_service.Scenario.MODERATE,
        target_rank_rule="Assumes roughly a two-position improvement for tracked keywords.",
    ),
    _ScenarioDefinition(
        key="aggressive",
        label="Aggressive",
        source=economics_service.Scenario.STRONG,
        target_rank_rule="Assumes stronger gains toward top-three positions where feasible.",
    ),
)


def build_baseline(
    db: Session,
    *,
    campaign_id: str,
    monthly_seo_investment: Decimal | None = None,
) -> dict[str, object]:
    normalized_investment = _normalize_optional_money(monthly_seo_investment)
    current_payload = economics_service.current_organic_media_value(db, campaign_id)
    upside_payload = economics_service.projected_value_if_rank_improves(db, campaign_id)
    scenarios = [
        economics_service.projected_value_for_scenario(db, campaign_id, definition.source)
        for definition in _SCENARIOS
    ]
    top_keywords = economics_service.top_keywords_by_value(db, campaign_id)
    opportunity_keywords = economics_service.highest_opportunity_gap_keywords(db, campaign_id)
    rows = economics_service._latest_campaign_keyword_economics_rows(db, campaign_id)
    snapshots = _latest_snapshots_for_rows(db, rows)
    keyword_labels = _keyword_labels(db, campaign_id)

    current_value = _money(current_payload["current_value"])
    upside_value = _money(upside_payload["value_delta"])
    expected_projected = _money(scenarios[1]["projected_value"]) if len(scenarios) > 1 else current_value
    confidence = _build_confidence(
        keyword_count=len(rows),
        snapshots=snapshots,
        has_investment=normalized_investment is not None,
    )

    provider_names = sorted({snapshot.source_provider for snapshot in snapshots if snapshot.source_provider})
    avg_snapshot_confidence = (
        sum(snapshot.confidence_score for snapshot in snapshots) / len(snapshots) if snapshots else 0.0
    )
    ctr_models = sorted({str(row.ctr_model_version) for row in rows if row.ctr_model_version})

    assumptions = [
        _assumption(
            key="valuation_method",
            label="Traffic valuation method",
            value="Paid-equivalent CPC model from stored keyword economics",
            status="available",
            source_type="estimated",
            note="This is an estimate of what the same clicks may cost in paid search, not booked revenue.",
        ),
        _assumption(
            key="monthly_seo_investment",
            label="Monthly SEO investment",
            value=_money_str(normalized_investment) if normalized_investment is not None else None,
            status="available" if normalized_investment is not None else "unavailable",
            source_type="user_provided" if normalized_investment is not None else "unavailable",
            note=(
                "Used only to create a paid-equivalent efficiency baseline. It does not convert this estimate into true profit."
                if normalized_investment is not None
                else "No saved monthly SEO investment exists for this campaign yet."
            ),
        ),
        _assumption(
            key="market_snapshot_inputs",
            label="Search volume and CPC inputs",
            value=_provider_summary(provider_names, avg_snapshot_confidence, len(snapshots)),
            status="available" if snapshots else "unavailable",
            source_type="provider_derived" if snapshots else "unavailable",
            note="Only keywords with stored market snapshots are included in the baseline.",
        ),
        _assumption(
            key="ctr_curve",
            label="CTR model",
            value=", ".join(ctr_models) if ctr_models else None,
            status="available" if ctr_models else "unavailable",
            source_type="estimated" if ctr_models else "unavailable",
            note="CTR curves are deterministic heuristics derived from the stored model version and device class.",
        ),
        _assumption(
            key="revenue_inputs",
            label="Revenue or conversion inputs",
            value=None,
            status="unavailable",
            source_type="unavailable",
            note="This V1 does not ingest actual revenue, lead quality, or conversion data, so projected value is not actual ROI.",
        ),
    ]

    caveats = [
        "Organic value is expressed as paid-search-equivalent media value, not revenue, profit, or booked pipeline.",
        "Scenario outputs are bounded rank-improvement heuristics built from current keyword economics rows, not production-grade forecasts.",
        "Only tracked keywords with stored ranking and market snapshot data are included in the baseline.",
        "If monthly SEO investment is missing, the ROI baseline remains unavailable rather than guessed.",
        f"Confidence is an internal product signal based on coverage and input quality; it is not a statistical confidence interval.",
    ]

    return {
        "campaign_id": campaign_id,
        "feature": "organic_value_roi_baseline_v1",
        "currency": "USD",
        "as_of": current_payload["as_of"].isoformat() if current_payload["as_of"] is not None else None,
        "current_value": _metric_amount(
            label="Estimated current organic media value",
            amount=current_value,
            status="available" if rows else "unavailable",
            source_type="estimated" if rows else "unavailable",
            monthly_investment=normalized_investment,
        ),
        "upside_opportunity": _metric_amount(
            label="Estimated near-term upside",
            amount=upside_value,
            status="available" if rows else "unavailable",
            source_type="estimated" if rows else "unavailable",
            monthly_investment=normalized_investment,
        ),
        "roi_baseline": _metric_ratio(
            label="Paid-equivalent ROI baseline",
            amount=current_value,
            monthly_investment=normalized_investment,
        ),
        "scenarios": [
            {
                "key": definition.key,
                "label": definition.label,
                "projected_value": _money_str(_money(result["projected_value"])),
                "upside_value": _money_str(_money(result["delta"])),
                "percentage_lift": _money_str(_money(result["percentage_lift"])),
                "target_rank_rule": definition.target_rank_rule,
                "roi_baseline": _metric_ratio(
                    label=f"{definition.label} paid-equivalent ROI baseline",
                    amount=_money(result["projected_value"]),
                    monthly_investment=normalized_investment,
                ),
            }
            for definition, result in zip(_SCENARIOS, scenarios, strict=True)
        ],
        "assumptions": assumptions,
        "confidence": confidence,
        "top_keywords_by_value": [
            {
                "keyword_id": str(row["keyword_id"]),
                "keyword": keyword_labels.get(str(row["keyword_id"])),
                "current_value": _money_str(_money(row["current_value"])),
                "projected_value": None,
                "upside_value": None,
                "current_rank": None,
                "projected_rank": None,
                "ctr_model_version": str(row["ctr_model_version"]),
            }
            for row in top_keywords
        ],
        "opportunity_drivers": [
            {
                "keyword_id": str(row["keyword_id"]),
                "keyword": keyword_labels.get(str(row["keyword_id"])),
                "current_value": _money_str(_money(row["current_value"])),
                "projected_value": _money_str(_money(row["projected_value"])),
                "upside_value": _money_str(_money(row["opportunity_gap"])),
                "current_rank": int(row["current_rank"]),
                "projected_rank": int(row["projected_rank"]),
                "ctr_model_version": str(row["ctr_model_version"]),
            }
            for row in opportunity_keywords
        ],
        "caveats": caveats,
    }


def resolve_monthly_seo_investment(
    db: Session,
    *,
    campaign_id: str,
    request_monthly_seo_investment: Decimal | None,
    persist_assumptions: bool,
    clear_monthly_seo_investment: bool,
    updated_by_user_id: str | None,
) -> Decimal | None:
    if clear_monthly_seo_investment:
        organic_value_baseline_settings_service.clear_monthly_seo_investment(
            db,
            campaign_id=campaign_id,
            updated_by_user_id=updated_by_user_id,
        )
        return None

    normalized = _normalize_optional_money(request_monthly_seo_investment)
    if normalized is not None:
        if persist_assumptions:
            organic_value_baseline_settings_service.upsert_monthly_seo_investment(
                db,
                campaign_id=campaign_id,
                monthly_seo_investment=normalized,
                updated_by_user_id=updated_by_user_id,
            )
        return normalized

    persisted = organic_value_baseline_settings_service.get_settings(db, campaign_id=campaign_id)
    if persisted is None or persisted.monthly_seo_investment is None:
        return None
    return _normalize_optional_money(Decimal(str(persisted.monthly_seo_investment)))


def _latest_snapshots_for_rows(
    db: Session,
    rows: list,
) -> list[KeywordMarketSnapshot]:
    snapshots: list[KeywordMarketSnapshot] = []
    for row in rows:
        snapshot = market_snapshot_service.get_latest_keyword_market_snapshot(
            db,
            keyword_id=row.keyword_id,
            geo_scope=economics_service.DEFAULT_GEO_SCOPE,
            device_class=economics_service.DEFAULT_DEVICE_CLASS,
            on_or_before=row.metric_date,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def _keyword_labels(db: Session, campaign_id: str) -> dict[str, str]:
    rows = (
        db.query(CampaignKeyword.id, CampaignKeyword.keyword)
        .filter(CampaignKeyword.campaign_id == campaign_id)
        .all()
    )
    return {str(keyword_id): str(keyword) for keyword_id, keyword in rows}


def _build_confidence(*, keyword_count: int, snapshots: list[KeywordMarketSnapshot], has_investment: bool) -> dict[str, object]:
    if keyword_count == 0:
        return {
            "level": "low",
            "score": _score_str(Decimal("0.10")),
            "reasons": [
                "No keyword economics rows are available for this campaign yet.",
                "Run ranking collection and store market snapshots before treating any estimate as meaningful.",
            ],
        }

    avg_snapshot_confidence = (
        sum(snapshot.confidence_score for snapshot in snapshots) / len(snapshots) if snapshots else 0.0
    )
    coverage_ratio = min(1.0, keyword_count / 5.0)
    score = Decimal("0.15")
    score += Decimal(str(round(coverage_ratio * 0.35, 6)))
    score += Decimal(str(round(avg_snapshot_confidence * 0.40, 6)))
    if has_investment:
        score += Decimal("0.10")
    score = min(score, Decimal("0.95"))

    level = "high" if score >= Decimal("0.75") else "medium" if score >= Decimal("0.50") else "low"
    reasons = [
        f"Baseline uses {keyword_count} tracked keyword economics row{'s' if keyword_count != 1 else ''}.",
        (
            f"Average market-snapshot confidence is {round(avg_snapshot_confidence, 2):.2f}."
            if snapshots
            else "No current market snapshot confidence was available, so confidence is capped."
        ),
        (
            "Monthly SEO investment was supplied, so the paid-equivalent ROI baseline can be shown."
            if has_investment
            else "Monthly SEO investment was not supplied, so ROI-style ratio outputs stay unavailable."
        ),
    ]
    return {"level": level, "score": _score_str(score), "reasons": reasons}


def _metric_amount(
    *,
    label: str,
    amount: Decimal,
    status: str,
    source_type: str,
    monthly_investment: Decimal | None,
) -> dict[str, object]:
    payload = {
        "label": label,
        "amount": _money_str(amount) if status == "available" else None,
        "ratio": None,
        "net_amount": None,
        "currency": "USD",
        "status": status,
        "source_type": source_type,
    }
    if monthly_investment is not None and monthly_investment > _ZERO and status == "available":
        payload["ratio"] = _ratio_str(amount / monthly_investment)
        payload["net_amount"] = _money_str(amount - monthly_investment)
    return payload


def _metric_ratio(*, label: str, amount: Decimal, monthly_investment: Decimal | None) -> dict[str, object]:
    if monthly_investment is None:
        return {
            "label": label,
            "amount": None,
            "ratio": None,
            "net_amount": None,
            "currency": "USD",
            "status": "unavailable",
            "source_type": "unavailable",
        }
    if monthly_investment <= _ZERO:
        return {
            "label": label,
            "amount": _money_str(amount),
            "ratio": None,
            "net_amount": _money_str(amount),
            "currency": "USD",
            "status": "available",
            "source_type": "user_provided",
        }
    return {
        "label": label,
        "amount": _money_str(amount),
        "ratio": _ratio_str(amount / monthly_investment),
        "net_amount": _money_str(amount - monthly_investment),
        "currency": "USD",
        "status": "available",
        "source_type": "user_provided",
    }


def _assumption(
    *,
    key: str,
    label: str,
    value: str | None,
    status: str,
    source_type: str,
    note: str | None = None,
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "status": status,
        "source_type": source_type,
        "note": note,
    }


def _provider_summary(provider_names: list[str], avg_confidence: float, snapshot_count: int) -> str | None:
    if snapshot_count == 0:
        return None
    provider_label = ", ".join(provider_names) if provider_names else "unknown"
    return f"{provider_label} across {snapshot_count} keyword snapshot{'s' if snapshot_count != 1 else ''}; avg confidence {avg_confidence:.2f}"


def _normalize_optional_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _money(value: Decimal | object) -> Decimal:
    return Decimal(str(value)).quantize(_MONEY, rounding=ROUND_HALF_UP)


def _money_str(value: Decimal) -> str:
    return format(value.quantize(_MONEY, rounding=ROUND_HALF_UP), "f")


def _ratio_str(value: Decimal) -> str:
    return format(value.quantize(_RATIO, rounding=ROUND_HALF_UP), "f")


def _score_str(value: Decimal) -> str:
    return format(value.quantize(_SCORE, rounding=ROUND_HALF_UP), "f")
