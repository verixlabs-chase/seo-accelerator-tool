from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.seo_experiment_result import SEOExperimentResult
from app.models.strategy_experiment import StrategyExperiment


def sync_experiment_network(db: Session, *, industry_id: str | None = None) -> list[dict[str, Any]]:
    rows = db.query(StrategyExperiment).order_by(StrategyExperiment.created_at.desc()).all()
    synced: list[dict[str, Any]] = []
    for row in rows:
        existing = (
            db.query(SEOExperimentResult)
            .filter(SEOExperimentResult.experiment_id == row.id)
            .first()
        )
        if existing is None:
            existing = SEOExperimentResult(experiment_id=row.id)
            db.add(existing)
        existing.strategy_id = row.strategy_id
        existing.variant_strategy_id = row.variant_strategy_id
        existing.industry_id = str(industry_id or (row.metadata_json or {}).get('industry') or 'unknown').strip().lower().replace(' ', '_') or 'unknown'
        existing.campaign_id = row.campaign_id
        existing.hypothesis = row.hypothesis
        existing.predicted_effect = float(row.expected_value or 0.0)
        existing.actual_effect = row.result_delta
        existing.confidence = float(row.confidence or 0.0)
        existing.status = row.status
        existing.metadata_json = dict(row.metadata_json or {})
        synced.append({'experiment_id': existing.experiment_id, 'variant_strategy_id': existing.variant_strategy_id, 'status': existing.status})
    db.flush()
    return synced
