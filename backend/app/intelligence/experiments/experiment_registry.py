from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.experiment import Experiment


def ensure_experiment_for_policy(
    db: Session,
    *,
    policy_id: str,
    industry: str,
    hypothesis: str | None = None,
    experiment_type: str = 'portfolio_policy',
    cohort_size: int = 100,
) -> Experiment:
    row = (
        db.query(Experiment)
        .filter(
            Experiment.policy_id == policy_id,
            Experiment.industry == industry,
            Experiment.status.in_(['active', 'running']),
        )
        .order_by(Experiment.created_at.desc())
        .first()
    )
    if row is not None:
        return row

    row = Experiment(
        policy_id=policy_id,
        hypothesis=hypothesis or f'Policy {policy_id} improves portfolio outcomes for {industry}.',
        experiment_type=experiment_type,
        cohort_size=cohort_size,
        status='active',
        industry=industry,
    )
    db.add(row)
    db.flush()
    return row
