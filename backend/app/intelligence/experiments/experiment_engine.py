from __future__ import annotations

from sqlalchemy.orm import Session

from app.events import EventType
from app.intelligence.experiments.experiment_analysis import analyze_experiment_for_outcome
from app.intelligence.experiments.experiment_assignment import assign_campaign_to_experiment, assignment_result
from app.intelligence.experiments.experiment_registry import ensure_experiment_for_policy
from app.intelligence.portfolio.portfolio_models import PolicyAllocation
from app.intelligence.portfolio.policy_performance import derive_policy_id
from app.models.experiment import Experiment, ExperimentAssignment, ExperimentOutcome
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome


def apply_experiment_assignments(
    db: Session,
    *,
    campaign_id: str,
    industry: str,
    allocations: list[PolicyAllocation],
) -> tuple[list[PolicyAllocation], list[dict[str, str]]]:
    baseline = [item for item in allocations if item.mode == 'exploit']
    experimental = [item for item in allocations if item.mode == 'explore']
    assignment_rows: list[dict[str, str]] = []

    for allocation in experimental:
        experiment = ensure_experiment_for_policy(
            db,
            policy_id=allocation.policy_id,
            industry=industry,
            hypothesis=f'Experimental allocation for {allocation.policy_id} improves outcomes.',
        )
        assignment = assign_campaign_to_experiment(db, campaign_id=campaign_id, experiment=experiment)
        assignment_rows.append(assignment_result(experiment, assignment).model_dump(mode='json'))
        if assignment.cohort == 'treatment':
            baseline.append(allocation)

    return baseline, assignment_rows


def record_experiment_outcome(db: Session, *, outcome: RecommendationOutcome) -> tuple[ExperimentOutcome | None, dict[str, object] | None]:
    recommendation = db.get(StrategyRecommendation, outcome.recommendation_id)
    if recommendation is None:
        return None, None
    policy_id = derive_policy_id(recommendation)
    assignment = (
        db.query(ExperimentAssignment)
        .filter(
            ExperimentAssignment.campaign_id == outcome.campaign_id,
            ExperimentAssignment.assigned_policy_id.in_([policy_id, f'baseline::{policy_id}']),
        )
        .order_by(ExperimentAssignment.created_at.desc())
        .first()
    )
    if assignment is None:
        return None, None

    existing = (
        db.query(ExperimentOutcome)
        .filter(ExperimentOutcome.outcome_id == outcome.id)
        .first()
    )
    if existing is not None:
        return existing, None

    row = ExperimentOutcome(
        experiment_id=assignment.experiment_id,
        assignment_id=assignment.id,
        outcome_id=outcome.id,
        campaign_id=outcome.campaign_id,
        metric_before=outcome.metric_before,
        metric_after=outcome.metric_after,
        delta=outcome.delta,
        success_flag=1.0 if outcome.delta > 0 else 0.0,
        measured_at=outcome.measured_at,
    )
    db.add(row)
    db.flush()

    analysis = analyze_experiment_for_outcome(db, experiment_id=assignment.experiment_id)
    if analysis is None:
        return row, None

    experiment = db.get(Experiment, assignment.experiment_id)
    event_payload = {
        'event_type': EventType.EXPERIMENT_COMPLETED.value,
        'payload': {
            'policy_id': analysis.policy_id,
            'effect_size': analysis.effect_size,
            'confidence': analysis.confidence,
            'industry': analysis.industry,
            'sample_size': analysis.sample_size,
            'source_node': f'industry::{analysis.industry}',
            'target_node': 'outcome::success',
            'experiment_id': assignment.experiment_id,
            'campaign_id': outcome.campaign_id,
            'outcome_id': outcome.id,
            'measured_at': outcome.measured_at.isoformat(),
            'outcome_name': 'outcome::success',
        },
    }
    if experiment is not None and analysis.confidence >= 1.0:
        experiment.status = 'completed'
        db.flush()
    return row, event_payload
