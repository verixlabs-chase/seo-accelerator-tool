from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.intelligence.experiments.experiment_models import ExperimentResult
from app.models.experiment import Experiment, ExperimentAssignment, ExperimentOutcome


def analyze_experiment(db: Session, *, experiment_id: str) -> ExperimentResult | None:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        return None

    treatment = _cohort_stats(db, experiment_id=experiment_id, cohort='treatment')
    control = _cohort_stats(db, experiment_id=experiment_id, cohort='control')
    effect_size = round(treatment['success_rate'] - control['success_rate'], 6)
    sample_total = treatment['count'] + control['count']
    confidence = round(min(1.0, sample_total / max(float(experiment.cohort_size), 1.0)), 6)

    return ExperimentResult(
        experiment_id=experiment.experiment_id,
        policy_id=experiment.policy_id,
        industry=experiment.industry,
        treatment_success_rate=treatment['success_rate'],
        control_success_rate=control['success_rate'],
        effect_size=effect_size,
        confidence=confidence,
        sample_size=sample_total,
    )


def analyze_experiment_for_outcome(db: Session, *, experiment_id: str) -> ExperimentResult | None:
    result = analyze_experiment(db, experiment_id=experiment_id)
    if result is None:
        return None
    if result.treatment_success_rate == 0.0 and result.control_success_rate == 0.0 and result.confidence == 0.0:
        return None
    return result


def _cohort_stats(db: Session, *, experiment_id: str, cohort: str) -> dict[str, float]:
    rows = (
        db.query(func.count(ExperimentOutcome.outcome_id), func.coalesce(func.avg(ExperimentOutcome.success_flag), 0.0))
        .join(ExperimentAssignment, ExperimentAssignment.id == ExperimentOutcome.assignment_id)
        .filter(
            ExperimentOutcome.experiment_id == experiment_id,
            ExperimentAssignment.cohort == cohort,
        )
        .first()
    )
    count = int(rows[0] or 0)
    return {
        'count': count,
        'success_rate': round(float(rows[1] or 0.0), 6),
    }
