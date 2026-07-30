from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.intelligence.lexicon.schema import IntelligenceLexicon, MetricDefinition


CWV_METRIC_IDS = ("cwv.lcp", "cwv.inp", "cwv.cls")


def evaluate_metric(metric: MetricDefinition, value: float) -> dict[str, Any]:
    thresholds = metric.thresholds
    if thresholds is None:
        return {
            "metric_id": metric.metric_id,
            "value": value,
            "unit": metric.unit,
            "status": "observed",
            "thresholds": None,
        }

    if thresholds.direction == "lower_is_better":
        if value <= thresholds.good_boundary:
            status = "good"
        elif value > thresholds.poor_boundary:
            status = "poor"
        else:
            status = "needs_improvement"
    else:
        if value >= thresholds.good_boundary:
            status = "good"
        elif value < thresholds.poor_boundary:
            status = "poor"
        else:
            status = "needs_improvement"

    return {
        "metric_id": metric.metric_id,
        "display_name": metric.display_name,
        "plain_language": metric.plain_language,
        "value": value,
        "unit": metric.unit,
        "status": status,
        "aggregation": metric.aggregation,
        "thresholds": {
            "direction": thresholds.direction,
            "good_boundary": thresholds.good_boundary,
            "poor_boundary": thresholds.poor_boundary,
            "percentile": thresholds.percentile,
        },
        "source_ids": list(metric.source_ids),
        "caveat": metric.caveat,
    }


def evaluate_core_web_vitals(
    lexicon: IntelligenceLexicon,
    measurements: dict[str, float | int | str | None],
    *,
    form_factor: str = "ALL",
    collection_period_days: int = 28,
    measured_at: datetime | None = None,
    source: str = "crux",
) -> dict[str, Any]:
    aliases = {
        "lcp": "cwv.lcp",
        "largest_contentful_paint": "cwv.lcp",
        "cwv.lcp": "cwv.lcp",
        "inp": "cwv.inp",
        "interaction_to_next_paint": "cwv.inp",
        "cwv.inp": "cwv.inp",
        "cls": "cwv.cls",
        "cumulative_layout_shift": "cwv.cls",
        "cwv.cls": "cwv.cls",
        "ttfb": "web_vital.ttfb",
        "experimental_time_to_first_byte": "web_vital.ttfb",
        "web_vital.ttfb": "web_vital.ttfb",
    }
    normalized: dict[str, float] = {}
    for key, raw_value in measurements.items():
        metric_id = aliases.get(str(key).strip().lower())
        if metric_id is None or raw_value is None:
            continue
        try:
            normalized[metric_id] = float(raw_value)
        except (TypeError, ValueError):
            continue

    results: list[dict[str, Any]] = []
    missing: list[str] = []
    for metric_id in CWV_METRIC_IDS:
        metric = lexicon.metric_index[metric_id]
        value = normalized.get(metric_id)
        if value is None:
            missing.append(metric_id)
            results.append(
                {
                    "metric_id": metric_id,
                    "display_name": metric.display_name,
                    "plain_language": metric.plain_language,
                    "status": "insufficient_data",
                    "value": None,
                    "unit": metric.unit,
                    "aggregation": metric.aggregation,
                    "thresholds": (
                        {
                            "direction": metric.thresholds.direction,
                            "good_boundary": metric.thresholds.good_boundary,
                            "poor_boundary": metric.thresholds.poor_boundary,
                            "percentile": metric.thresholds.percentile,
                        }
                        if metric.thresholds is not None
                        else None
                    ),
                    "source_ids": list(metric.source_ids),
                    "caveat": metric.caveat,
                }
            )
        else:
            results.append(evaluate_metric(metric, value))

    supporting: list[dict[str, Any]] = []
    ttfb = normalized.get("web_vital.ttfb")
    if ttfb is not None and "web_vital.ttfb" in lexicon.metric_index:
        supporting.append(evaluate_metric(lexicon.metric_index["web_vital.ttfb"], ttfb))

    if missing:
        overall_status = "insufficient_data"
        passes = None
    elif any(item["status"] == "poor" for item in results):
        overall_status = "poor"
        passes = False
    elif any(item["status"] == "needs_improvement" for item in results):
        overall_status = "needs_improvement"
        passes = False
    else:
        overall_status = "good"
        passes = True

    failing_metric_ids = [
        item["metric_id"] for item in results if item["status"] in {"needs_improvement", "poor"}
    ]
    action_ids = _cwv_action_ids(lexicon, failing_metric_ids)
    actions = [
        _action_payload(lexicon.action_index[action_id])
        for action_id in action_ids
        if action_id in lexicon.action_index
    ]

    return {
        "lexicon": {
            "id": lexicon.meta.lexicon_id,
            "version": lexicon.meta.version,
            "schema_version": lexicon.meta.schema_version,
            "standards_reviewed_at": lexicon.meta.standards_reviewed_at.isoformat(),
        },
        "assessment": {
            "status": overall_status,
            "passes_core_web_vitals": passes,
            "method": "all_three_core_web_vitals_good_at_p75",
            "percentile": 75,
            "form_factor": form_factor.upper(),
            "collection_period_days": collection_period_days,
            "source": source,
            "measured_at": (measured_at or datetime.now(UTC)).isoformat(),
            "missing_metric_ids": missing,
        },
        "metrics": results,
        "supporting_metrics": supporting,
        "recommended_actions": actions,
        "search_caveat": (
            "Core Web Vitals contribute to page experience, but Google does not "
            "define a single page-experience ranking signal and good scores do "
            "not guarantee higher rankings."
        ),
    }


def _cwv_action_ids(
    lexicon: IntelligenceLexicon,
    failing_metric_ids: list[str],
) -> list[str]:
    mapping = {
        "cwv.lcp": [
            "technical.reduce_render_blocking",
            "technical.optimize_server_response",
            "technical.optimize_lcp_resource",
        ],
        "cwv.inp": [
            "technical.reduce_main_thread_work",
            "technical.optimize_interaction_handlers",
        ],
        "cwv.cls": [
            "technical.reserve_layout_space",
            "technical.stabilize_dynamic_content",
        ],
    }
    ordered: list[str] = []
    for metric_id in failing_metric_ids:
        for action_id in mapping.get(metric_id, []):
            if action_id in lexicon.action_index and action_id not in ordered:
                ordered.append(action_id)
    return ordered


def _action_payload(action: Any) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "display_name": action.display_name,
        "why_it_matters": action.why_it_matters,
        "steps": list(action.steps),
        "risk_tier": action.risk_tier,
        "effort": action.effort,
        "owner_role": action.owner_role,
        "success_metric_ids": list(action.success_metric_ids),
        "observation_window_days": action.observation_window_days,
        "requires_approval": action.risk_tier >= 2,
    }
