from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import json
from typing import Any

from app.core.settings import get_settings


def recommendation_engine_source(recommendation: object) -> str:
    if isinstance(recommendation, Mapping):
        explicit_source = recommendation.get("engine_source")
        recommendation_type = recommendation.get("recommendation_type")
        evidence_json = recommendation.get("evidence_json")
    else:
        explicit_source = getattr(recommendation, "engine_source", None)
        recommendation_type = getattr(recommendation, "recommendation_type", None)
        evidence_json = getattr(recommendation, "evidence_json", None)

    if explicit_source:
        return str(explicit_source)
    if str(recommendation_type or "").startswith(("policy::", "transfer::")):
        return "orchestrator_v1"

    try:
        evidence = json.loads(str(evidence_json or "[]"))
    except json.JSONDecodeError:
        evidence = []
    if isinstance(evidence, dict) and evidence.get("policy_id"):
        return "orchestrator_v1"
    return "heuristic_threshold_v1"


def build_intelligence_engine_state(
    recommendations: Iterable[object],
    *,
    fallback_source: str = "awaiting_recommendations",
) -> dict[str, Any]:
    rows = list(recommendations)
    source_counts = {
        "orchestrator_v1": 0,
        "heuristic_threshold_v1": 0,
    }
    created_at_values: list[datetime] = []
    for row in rows:
        source = recommendation_engine_source(row)
        source_counts[source] = source_counts.get(source, 0) + 1
        created_at = (
            row.get("created_at")
            if isinstance(row, Mapping)
            else getattr(row, "created_at", None)
        )
        if isinstance(created_at, datetime):
            created_at_values.append(created_at)

    orchestrator_count = source_counts.get("orchestrator_v1", 0)
    heuristic_count = source_counts.get("heuristic_threshold_v1", 0)
    if orchestrator_count and heuristic_count:
        guidance_source = "mixed_v1"
    elif orchestrator_count:
        guidance_source = "orchestrator_v1"
    elif heuristic_count:
        guidance_source = "heuristic_threshold_v1"
    else:
        guidance_source = fallback_source

    activation_mode = get_settings().intelligence_activation_mode
    last_generated_at = max(created_at_values).isoformat() if created_at_values else None
    return {
        "activation_mode": activation_mode,
        "guidance_source": guidance_source,
        "orchestrator_recommendation_count": orchestrator_count,
        "heuristic_recommendation_count": heuristic_count,
        "data_scope": "stored_campaign_data",
        "provider_checks_allowed": False,
        "mutation_scheduling_enabled": activation_mode == "autonomous",
        "mutation_execution_enabled": activation_mode == "autonomous",
        "operator_review_required": True,
        "learning_state": "inactive_noop",
        "cycle_schedule": "daily_vercel_cron",
        "last_generated_at": last_generated_at,
    }
