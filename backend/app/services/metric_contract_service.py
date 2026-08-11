from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.provider_metric_contract import ProviderMetricContractVersion
from app.services import standards_source_service


CONTRACT_VERSION = "1.0"
CONTRACT_EFFECTIVE_AT = datetime(2026, 8, 9, tzinfo=UTC)


@dataclass(frozen=True)
class MetricContractDefinition:
    contract_id: str
    provider_name: str
    metric_family: str
    metric_id: str
    display_name: str
    definition: str
    unit: str
    aggregation: str
    direction: str
    collection_status: str
    authoritative_source_id: str | None
    required_scope_fields: tuple[str, ...]
    optional_scope_fields: tuple[str, ...]
    comparison_keys: tuple[str, ...]
    freshness_days: int
    version: str = CONTRACT_VERSION


def _contract(
    contract_id: str,
    *,
    provider: str,
    family: str,
    metric_id: str,
    name: str,
    definition: str,
    unit: str,
    aggregation: str,
    direction: str,
    status: str,
    source: str | None,
    required: tuple[str, ...],
    comparison: tuple[str, ...],
    optional: tuple[str, ...] = (),
    freshness_days: int = 7,
) -> MetricContractDefinition:
    return MetricContractDefinition(
        contract_id=contract_id,
        provider_name=provider,
        metric_family=family,
        metric_id=metric_id,
        display_name=name,
        definition=definition,
        unit=unit,
        aggregation=aggregation,
        direction=direction,
        collection_status=status,
        authoritative_source_id=source,
        required_scope_fields=required,
        optional_scope_fields=optional,
        comparison_keys=comparison,
        freshness_days=freshness_days,
    )


_WEB_SCOPE = (
    "organization_id",
    "campaign_id",
    "measured_url",
    "scope",
    "form_factor",
)
_GSC_SCOPE = (
    "organization_id",
    "campaign_id",
    "property_uri",
    "search_type",
    "dimensions",
    "filters",
)
_GBP_SCOPE = (
    "organization_id",
    "campaign_id",
    "business_location_id",
    "connection_id",
    "external_resource_id",
    "source_account_id",
)
_GRID_SCOPE = (
    "organization_id",
    "campaign_id",
    "business_location_id",
    "keyword_id",
    "grid_definition_hash",
    "language_code",
    "device_class",
    "provider_method",
)


def _default_contracts() -> tuple[MetricContractDefinition, ...]:
    rows: list[MetricContractDefinition] = []
    crux_metrics = (
        ("lcp", "Largest Contentful Paint", "milliseconds", "p75", "lower_is_better"),
        ("inp", "Interaction to Next Paint", "milliseconds", "p75", "lower_is_better"),
        ("cls", "Cumulative Layout Shift", "score", "p75", "lower_is_better"),
        ("ttfb", "Time to First Byte", "milliseconds", "p75", "lower_is_better"),
    )
    for metric_id, name, unit, aggregation, direction in crux_metrics:
        rows.append(
            _contract(
                f"web.crux.{metric_id}",
                provider="chrome_ux_report",
                family="real_user_page_experience",
                metric_id=metric_id,
                name=name,
                definition=(
                    f"Chrome UX Report {aggregation} {name} for the saved URL or origin and form factor."
                    + (" This is supporting evidence, not a Core Web Vital." if metric_id == "ttfb" else "")
                ),
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="collected",
                source="google.search.core_web_vitals",
                required=_WEB_SCOPE + ("collection_start", "collection_end"),
                comparison=_WEB_SCOPE,
                optional=("fallback_to_origin",),
                freshness_days=35,
            )
        )

    lab_metrics = (
        ("lcp", "Lab Largest Contentful Paint", "milliseconds", "single_run", "lower_is_better"),
        ("cls", "Lab Cumulative Layout Shift", "score", "single_run", "lower_is_better"),
        ("ttfb", "Lab server response time", "milliseconds", "single_run", "lower_is_better"),
        ("fcp", "First Contentful Paint", "milliseconds", "single_run", "lower_is_better"),
        ("tbt", "Total Blocking Time", "milliseconds", "single_run", "lower_is_better"),
        ("performance_score", "Lighthouse performance score", "score_0_100", "single_run", "higher_is_better"),
    )
    for metric_id, name, unit, aggregation, direction in lab_metrics:
        rows.append(
            _contract(
                f"web.pagespeed.{metric_id}",
                provider="pagespeed_insights",
                family="lab_page_diagnostics",
                metric_id=metric_id,
                name=name,
                definition=f"A single PageSpeed Insights/Lighthouse diagnostic run for {name}.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="collected",
                source=None,
                required=(
                    "organization_id",
                    "campaign_id",
                    "measured_url",
                    "form_factor",
                    "source_version",
                    "captured_at",
                ),
                comparison=("organization_id", "campaign_id", "measured_url", "form_factor"),
                optional=("run_environment",),
                freshness_days=7,
            )
        )

    gsc_metrics = (
        ("clicks", "Google search visits", "count", "sum", "higher_is_better"),
        ("impressions", "Google search appearances", "count", "sum", "higher_is_better"),
        ("ctr", "Search click-through rate", "ratio", "clicks_divided_by_impressions", "higher_is_better"),
        ("position", "Average Google position", "position", "impression_weighted_mean", "lower_is_better"),
    )
    for metric_id, name, unit, aggregation, direction in gsc_metrics:
        rows.append(
            _contract(
                f"search_console.{metric_id}",
                provider="google_search_console",
                family="search_performance",
                metric_id=metric_id,
                name=name,
                definition=f"Search Console {name.lower()} for one exact property, search type, dimension set, filter set, and date window.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="collected",
                source="google.search_console.metrics",
                required=_GSC_SCOPE + ("window_start", "window_end"),
                comparison=_GSC_SCOPE,
                optional=("page", "query", "device", "country", "search_appearance"),
                freshness_days=4,
            )
        )

    unavailable_website = (
        ("search.indexing_state", "Indexing state", "state", "latest", "neutral", "indexing"),
        ("search.selected_canonical", "Google-selected canonical", "url", "latest", "neutral", "indexing"),
        ("search.robots_eligibility", "Robots eligibility", "state", "latest", "neutral", "indexing"),
        ("search.sitemap_coverage", "Sitemap coverage", "ratio", "latest", "higher_is_better", "indexing"),
        ("search.structured_data_eligibility", "Structured-data eligibility", "state", "latest", "neutral", "structured_data"),
        ("search.structured_data_errors", "Structured-data errors", "count", "sum", "lower_is_better", "structured_data"),
    )
    for contract_id, name, unit, aggregation, direction, family in unavailable_website:
        source = "google.search.structured_data" if family == "structured_data" else None
        rows.append(
            _contract(
                contract_id,
                provider="google_search_console",
                family=family,
                metric_id=contract_id.rsplit(".", 1)[-1],
                name=name,
                definition=f"Direct provider evidence for {name.lower()} at one inspected page or property scope.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="not_collected",
                source=source,
                required=("organization_id", "campaign_id", "property_uri", "page_url", "checked_at"),
                comparison=("organization_id", "campaign_id", "property_uri", "page_url"),
                freshness_days=7,
            )
        )

    crawl_metrics = (
        ("indexable_page_count", "Indexable pages", "count", "sum", "higher_is_better"),
        ("broken_link_count", "Broken links", "count", "sum", "lower_is_better"),
        ("redirect_defect_count", "Redirect problems", "count", "sum", "lower_is_better"),
        ("missing_title_count", "Pages missing titles", "count", "sum", "lower_is_better"),
        ("duplicate_title_count", "Duplicate page titles", "count", "sum", "lower_is_better"),
        ("missing_description_count", "Pages missing descriptions", "count", "sum", "lower_is_better"),
        ("duplicate_description_count", "Duplicate descriptions", "count", "sum", "lower_is_better"),
        ("internal_link_coverage", "Internal-link coverage", "ratio", "ratio", "higher_is_better"),
        ("affected_page_ratio", "Pages affected by technical problems", "ratio", "ratio", "lower_is_better"),
    )
    for metric_id, name, unit, aggregation, direction in crawl_metrics:
        rows.append(
            _contract(
                f"crawl.{metric_id}",
                provider="website_crawl",
                family="site_integrity",
                metric_id=metric_id,
                name=name,
                definition=f"Deterministic {name.lower()} from one completed, campaign-scoped crawl.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="collected" if metric_id in {"indexable_page_count", "affected_page_ratio"} else "derived",
                source=None,
                required=("organization_id", "campaign_id", "crawl_run_id", "crawl_scope", "captured_at"),
                comparison=("organization_id", "campaign_id", "crawl_scope"),
                optional=("pages_checked",),
                freshness_days=14,
            )
        )

    gbp_metrics = (
        ("BUSINESS_IMPRESSIONS_DESKTOP_MAPS", "Map appearances on computers", "count", "sum", "higher_is_better"),
        ("BUSINESS_IMPRESSIONS_DESKTOP_SEARCH", "Search appearances on computers", "count", "sum", "higher_is_better"),
        ("BUSINESS_IMPRESSIONS_MOBILE_MAPS", "Map appearances on phones", "count", "sum", "higher_is_better"),
        ("BUSINESS_IMPRESSIONS_MOBILE_SEARCH", "Search appearances on phones", "count", "sum", "higher_is_better"),
        ("BUSINESS_DIRECTION_REQUESTS", "Direction requests", "count", "sum", "higher_is_better"),
        ("CALL_CLICKS", "Call button clicks", "count", "sum", "higher_is_better"),
        ("WEBSITE_CLICKS", "Website clicks", "count", "sum", "higher_is_better"),
        ("BUSINESS_BOOKINGS", "Bookings", "count", "sum", "higher_is_better"),
    )
    for metric_id, name, unit, aggregation, direction in gbp_metrics:
        rows.append(
            _contract(
                f"gbp.performance.{metric_id.lower()}",
                provider="google_business_profile",
                family="business_profile_performance",
                metric_id=metric_id,
                name=name,
                definition=f"Business Profile Performance API {name.lower()} for one mapped location and date window.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="collected",
                source="google.business.performance_reference",
                required=_GBP_SCOPE + ("window_start", "window_end"),
                comparison=_GBP_SCOPE,
                freshness_days=7,
            )
        )
    rows.append(
        _contract(
            "gbp.performance.total_appearances",
            provider="google_business_profile",
            family="business_profile_performance",
            metric_id="total_appearances",
            name="Total Search and Maps appearances",
            definition="The sum of the four supported Search and Maps appearance metrics for one mapped location and date window.",
            unit="count",
            aggregation="derived_sum",
            direction="higher_is_better",
            status="derived",
            source="google.business.performance_reference",
            required=_GBP_SCOPE + ("window_start", "window_end"),
            comparison=_GBP_SCOPE,
            freshness_days=7,
        )
    )
    rows.append(
        _contract(
            "gbp.search_terms.monthly_impressions",
            provider="google_business_profile",
            family="business_profile_search_terms",
            metric_id="monthly_search_term_impressions",
            name="Monthly customer search-term impressions",
            definition="Provider-reported exact or thresholded monthly impressions for one customer search term and mapped profile.",
            unit="count_or_threshold",
            aggregation="monthly",
            direction="neutral",
            status="collected",
            source="google.business.performance_reference",
            required=_GBP_SCOPE + ("metric_month", "keyword", "measurement_kind"),
            comparison=_GBP_SCOPE + ("keyword", "measurement_kind"),
            freshness_days=40,
        )
    )

    grid_metrics = (
        ("position", "Map position by point", "position", "point", "lower_is_better"),
        ("top_3_share", "Grid points in the top 3", "ratio", "share", "higher_is_better"),
        ("top_10_share", "Grid points in the top 10", "ratio", "share", "higher_is_better"),
        ("median_position", "Median map position", "position", "median", "lower_is_better"),
        ("unranked_share", "Unranked grid points", "ratio", "share", "lower_is_better"),
        ("ranking_radius", "Useful ranking radius", "miles", "derived_radius", "higher_is_better"),
    )
    for metric_id, name, unit, aggregation, direction in grid_metrics:
        rows.append(
            _contract(
                f"local_grid.{metric_id}",
                provider="google_maps_results",
                family="local_visibility_grid",
                metric_id=metric_id,
                name=name,
                definition=f"{name} for one keyword and an immutable grid definition.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status="collected" if metric_id == "position" else "derived",
                source="google.business.local_ranking",
                required=_GRID_SCOPE + ("run_timestamp",),
                comparison=_GRID_SCOPE,
                optional=("grid_size", "radius_miles", "center_latitude", "center_longitude", "spacing_miles"),
                freshness_days=14,
            )
        )

    reputation_metrics = (
        ("review_count_30d", "New reviews in 30 days", "count", "rolling_30_day_sum", "higher_is_better", "collected"),
        ("review_pace", "Review pace", "reviews_per_30_days", "rolling_30_day_rate", "higher_is_better", "derived"),
        ("average_rating_30d", "Average rating in 30 days", "rating_1_5", "rolling_30_day_mean", "higher_is_better", "collected"),
        ("response_coverage", "Review response coverage", "ratio", "rolling_window_ratio", "higher_is_better", "not_collected"),
        ("response_time", "Review response time", "hours", "median", "lower_is_better", "not_collected"),
    )
    for metric_id, name, unit, aggregation, direction, status in reputation_metrics:
        rows.append(
            _contract(
                f"reputation.{metric_id}",
                provider="google_business_profile_reviews",
                family="reputation",
                metric_id=metric_id,
                name=name,
                definition=f"{name} for one saved profile and explicit observation window.",
                unit=unit,
                aggregation=aggregation,
                direction=direction,
                status=status,
                source=None,
                required=("tenant_id", "campaign_id", "business_location_id", "profile_id", "window_start", "window_end"),
                comparison=("tenant_id", "campaign_id", "business_location_id", "profile_id"),
                freshness_days=14,
            )
        )

    rows.append(
        _contract(
            "gbp.profile.configuration",
            provider="google_business_profile",
            family="business_profile_configuration",
            metric_id="profile_configuration",
            name="Business listing information",
            definition="A point-in-time record of provider-returned profile fields. This is an upkeep check, not a ranking score.",
            unit="configuration",
            aggregation="snapshot",
            direction="configuration",
            status="collected",
            source="google.business.information_change_log",
            required=_GBP_SCOPE + ("captured_at",),
            comparison=_GBP_SCOPE,
            optional=("available_fields", "unavailable_fields"),
            freshness_days=14,
        )
    )
    return tuple(rows)


DEFAULT_METRIC_CONTRACTS = _default_contracts()
CONTRACT_INDEX = {row.contract_id: row for row in DEFAULT_METRIC_CONTRACTS}

LEXICON_METRIC_CONTRACTS = {
    "cwv.lcp": "web.crux.lcp",
    "cwv.inp": "web.crux.inp",
    "cwv.cls": "web.crux.cls",
    "web_vital.ttfb": "web.crux.ttfb",
    "organic.ctr": "search_console.ctr",
    "organic.impressions": "search_console.impressions",
    "organic.avg_position": "search_console.position",
    "local.review_velocity_30d": "reputation.review_count_30d",
    "local.avg_rating": "reputation.average_rating_30d",
    "local.gbp.total_appearances": "gbp.performance.total_appearances",
    "local.gbp.website_clicks": "gbp.performance.website_clicks",
    "local.gbp.call_clicks": "gbp.performance.call_clicks",
    "local.gbp.direction_requests": "gbp.performance.business_direction_requests",
    "local.gbp.bookings": "gbp.performance.business_bookings",
    "technical.issue_density": "crawl.affected_page_ratio",
}


class MetricContractScopeError(ValueError):
    def __init__(self, contract_id: str, missing_fields: list[str]) -> None:
        super().__init__(
            f"Measurement scope for {contract_id} is missing: {', '.join(missing_fields)}."
        )
        self.contract_id = contract_id
        self.missing_fields = missing_fields


def contract_definition(
    contract_id: str,
    *,
    db: Session | None = None,
) -> MetricContractDefinition:
    if db is not None:
        row = (
            db.query(ProviderMetricContractVersion)
            .filter(
                ProviderMetricContractVersion.contract_id == contract_id,
                ProviderMetricContractVersion.is_active.is_(True),
                ProviderMetricContractVersion.lifecycle_status == "active",
            )
            .order_by(ProviderMetricContractVersion.effective_at.desc())
            .first()
        )
        if row is not None:
            return _definition_from_row(row)
    try:
        return CONTRACT_INDEX[contract_id]
    except KeyError as exc:
        raise ValueError(f"Unknown metric contract: {contract_id}") from exc


def contract_for_lexicon_metric(metric_id: str) -> MetricContractDefinition | None:
    contract_id = LEXICON_METRIC_CONTRACTS.get(metric_id)
    return CONTRACT_INDEX.get(contract_id) if contract_id else None


def business_profile_contract_id(metric_name: str) -> str:
    return f"gbp.performance.{str(metric_name).strip().lower()}"


def contract_payload(definition: MetricContractDefinition) -> dict[str, Any]:
    return {
        **asdict(definition),
        "required_scope_fields": list(definition.required_scope_fields),
        "optional_scope_fields": list(definition.optional_scope_fields),
        "comparison_keys": list(definition.comparison_keys),
        "automatic_activation_allowed": False,
        "content_hash": _content_hash(definition),
    }


def scope_evidence(
    contract_id: str,
    scope: dict[str, Any],
    *,
    require_complete: bool = True,
    db: Session | None = None,
) -> dict[str, Any]:
    definition = contract_definition(contract_id, db=db)
    normalized = _normalize_scope(scope)
    missing = [
        field
        for field in definition.required_scope_fields
        if field not in normalized or normalized[field] in (None, "", (), [])
    ]
    if missing and require_complete:
        raise MetricContractScopeError(contract_id, missing)
    comparable = {
        field: normalized.get(field)
        for field in definition.comparison_keys
        if field in normalized
    }
    return {
        "metric_contract_id": definition.contract_id,
        "metric_contract_version": definition.version,
        "metric_contract_status": definition.collection_status,
        "freshness_days": definition.freshness_days,
        "scope": normalized,
        "scope_key": _stable_hash(comparable),
        "scope_complete": not missing,
        "missing_scope_fields": missing,
        "comparison_keys": list(definition.comparison_keys),
    }


def ensure_default_contracts(db: Session, *, commit: bool = True) -> list[ProviderMetricContractVersion]:
    standards_source_service.ensure_default_sources(db, commit=False)
    rows: list[ProviderMetricContractVersion] = []
    for definition in DEFAULT_METRIC_CONTRACTS:
        expected_hash = _content_hash(definition)
        row = (
            db.query(ProviderMetricContractVersion)
            .filter(
                ProviderMetricContractVersion.contract_id == definition.contract_id,
                ProviderMetricContractVersion.version == definition.version,
            )
            .one_or_none()
        )
        if row is None:
            row = ProviderMetricContractVersion(
                contract_id=definition.contract_id,
                version=definition.version,
                provider_name=definition.provider_name,
                metric_family=definition.metric_family,
                metric_id=definition.metric_id,
                display_name=definition.display_name,
                definition=definition.definition,
                unit=definition.unit,
                aggregation=definition.aggregation,
                direction=definition.direction,
                collection_status=definition.collection_status,
                authoritative_source_id=definition.authoritative_source_id,
                required_scope_fields=list(definition.required_scope_fields),
                optional_scope_fields=list(definition.optional_scope_fields),
                comparison_keys=list(definition.comparison_keys),
                freshness_days=definition.freshness_days,
                content_hash=expected_hash,
                is_active=True,
                lifecycle_status="active",
                automatic_activation_allowed=False,
                effective_at=CONTRACT_EFFECTIVE_AT,
                created_at=datetime.now(UTC),
            )
            db.add(row)
            db.flush()
        elif row.content_hash != expected_hash:
            raise RuntimeError(
                f"Metric contract {definition.contract_id} version {definition.version} changed in place. Create a new version."
            )
        rows.append(row)
    if commit:
        db.commit()
    return rows


def list_active_contracts(
    db: Session,
    *,
    provider_name: str | None = None,
    metric_family: str | None = None,
) -> dict[str, Any]:
    ensure_default_contracts(db)
    query = db.query(ProviderMetricContractVersion).filter(
        ProviderMetricContractVersion.is_active.is_(True)
    )
    if provider_name:
        query = query.filter(ProviderMetricContractVersion.provider_name == provider_name.strip())
    if metric_family:
        query = query.filter(ProviderMetricContractVersion.metric_family == metric_family.strip())
    rows = query.order_by(
        ProviderMetricContractVersion.metric_family,
        ProviderMetricContractVersion.display_name,
    ).all()
    items = [_row_payload(row) for row in rows]
    return {
        "status": "current",
        "items": items,
        "counts": {
            status: sum(item["collection_status"] == status for item in items)
            for status in ("collected", "derived", "not_collected")
        },
        "automatic_activation_allowed": False,
    }


def list_contract_versions(
    db: Session,
    *,
    contract_id: str | None = None,
    lifecycle_status: str | None = None,
) -> dict[str, Any]:
    ensure_default_contracts(db)
    query = db.query(ProviderMetricContractVersion)
    if contract_id:
        query = query.filter(ProviderMetricContractVersion.contract_id == contract_id.strip())
    if lifecycle_status:
        resolved_status = lifecycle_status.strip()
        if resolved_status not in {"active", "candidate", "retired"}:
            raise ValueError("Choose an active, candidate, or retired contract lifecycle.")
        query = query.filter(ProviderMetricContractVersion.lifecycle_status == resolved_status)
    rows = query.order_by(
        ProviderMetricContractVersion.contract_id,
        ProviderMetricContractVersion.effective_at.desc(),
        ProviderMetricContractVersion.created_at.desc(),
    ).all()
    return {
        "items": [_row_payload(row) for row in rows],
        "returned": len(rows),
        "automatic_activation_allowed": False,
    }


def contract_versions(
    contract_ids: Iterable[str],
    *,
    db: Session | None = None,
) -> dict[str, str]:
    return {
        contract_id: contract_definition(contract_id, db=db).version
        for contract_id in sorted(set(contract_ids))
    }


def _definition_from_row(row: ProviderMetricContractVersion) -> MetricContractDefinition:
    return MetricContractDefinition(
        contract_id=row.contract_id,
        provider_name=row.provider_name,
        metric_family=row.metric_family,
        metric_id=row.metric_id,
        display_name=row.display_name,
        definition=row.definition,
        unit=row.unit,
        aggregation=row.aggregation,
        direction=row.direction,
        collection_status=row.collection_status,
        authoritative_source_id=row.authoritative_source_id,
        required_scope_fields=tuple(row.required_scope_fields or []),
        optional_scope_fields=tuple(row.optional_scope_fields or []),
        comparison_keys=tuple(row.comparison_keys or []),
        freshness_days=row.freshness_days,
        version=row.version,
    )


def _row_payload(row: ProviderMetricContractVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "contract_id": row.contract_id,
        "version": row.version,
        "provider_name": row.provider_name,
        "metric_family": row.metric_family,
        "metric_id": row.metric_id,
        "display_name": row.display_name,
        "definition": row.definition,
        "unit": row.unit,
        "aggregation": row.aggregation,
        "direction": row.direction,
        "collection_status": row.collection_status,
        "authoritative_source_id": row.authoritative_source_id,
        "required_scope_fields": list(row.required_scope_fields or []),
        "optional_scope_fields": list(row.optional_scope_fields or []),
        "comparison_keys": list(row.comparison_keys or []),
        "freshness_days": row.freshness_days,
        "content_hash": row.content_hash,
        "is_active": row.is_active,
        "lifecycle_status": row.lifecycle_status,
        "supersedes_version_id": row.supersedes_version_id,
        "standards_change_candidate_id": row.standards_change_candidate_id,
        "proposed_by_user_id": row.proposed_by_user_id,
        "proposed_at": row.proposed_at,
        "automatic_activation_allowed": False,
        "effective_at": row.effective_at,
    }


def _content_hash(definition: MetricContractDefinition) -> str:
    return _stable_hash(asdict(definition))


def _normalize_scope(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_scope(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_scope(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        _normalize_scope(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()
