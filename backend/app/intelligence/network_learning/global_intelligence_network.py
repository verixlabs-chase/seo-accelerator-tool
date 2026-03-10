from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.network_learning.causal_outcome_analyzer import analyze_causal_outcomes
from app.intelligence.network_learning.experiment_network_engine import sync_experiment_network
from app.intelligence.network_learning.industry_similarity_engine import compute_industry_similarity_matrix
from app.models.seo_mutation_outcome import SEOMutationOutcome


def run_global_intelligence_network(db: Session, *, target_industry_id: str | None = None) -> dict[str, Any]:
    similarity = compute_industry_similarity_matrix(db)
    causal = analyze_causal_outcomes(db, target_industry_id=target_industry_id)
    experiments = sync_experiment_network(db, industry_id=target_industry_id)
    mutation_count = db.query(SEOMutationOutcome).count()
    db.flush()
    return {
        'mutation_outcomes': int(mutation_count),
        'industry_similarity_updates': len(similarity),
        'causal_findings': causal,
        'experiment_results_synced': len(experiments),
    }
