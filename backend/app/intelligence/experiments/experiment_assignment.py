from __future__ import annotations

from hashlib import sha256

from sqlalchemy.orm import Session

from app.intelligence.experiments.experiment_models import ExperimentAssignmentResult
from app.models.experiment import Experiment, ExperimentAssignment


def deterministic_bucket(campaign_id: str, experiment_id: str) -> int:
    digest = sha256(f'{campaign_id}:{experiment_id}'.encode('utf-8')).hexdigest()
    return int(digest[:8], 16) % 100


def assign_campaign_to_experiment(
    db: Session,
    *,
    campaign_id: str,
    experiment: Experiment,
) -> ExperimentAssignment:
    existing = (
        db.query(ExperimentAssignment)
        .filter(
            ExperimentAssignment.campaign_id == campaign_id,
            ExperimentAssignment.experiment_id == experiment.experiment_id,
        )
        .first()
    )
    if existing is not None:
        return existing

    bucket = deterministic_bucket(campaign_id, experiment.experiment_id)
    cohort = 'control' if bucket < 70 else 'treatment'
    row = ExperimentAssignment(
        experiment_id=experiment.experiment_id,
        campaign_id=campaign_id,
        cohort=cohort,
        bucket=bucket,
        assigned_policy_id=experiment.policy_id if cohort == 'treatment' else f'baseline::{experiment.policy_id}',
    )
    db.add(row)
    db.flush()
    return row


def assignment_result(experiment: Experiment, assignment: ExperimentAssignment) -> ExperimentAssignmentResult:
    return ExperimentAssignmentResult(
        experiment_id=experiment.experiment_id,
        campaign_id=assignment.campaign_id,
        cohort=assignment.cohort,
        policy_id=experiment.policy_id,
        assigned_policy_id=assignment.assigned_policy_id,
    )
