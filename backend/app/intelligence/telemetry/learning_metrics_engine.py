from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.experiment import Experiment, ExperimentAssignment, ExperimentOutcome
from app.models.knowledge_graph import KnowledgeEdge
from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.policy_performance import PolicyPerformance
from app.models.strategy_evolution_log import StrategyEvolutionLog


def snapshot_learning_metrics(db: Session) -> LearningMetricSnapshot:
    parent_child_pairs = _parent_child_pairs(db)
    mutation_count = len(parent_child_pairs)
    successful_mutations = 0
    improvement_values: list[float] = []

    for parent_policy, child_policy in parent_child_pairs:
        parent_score = _policy_mean_score(db, parent_policy)
        child_score = _policy_mean_score(db, child_policy)
        if parent_score is None or child_score is None:
            continue
        delta = round(child_score - parent_score, 6)
        improvement_values.append(delta)
        if delta > 0:
            successful_mutations += 1

    mutation_success_rate = round(successful_mutations / mutation_count, 6) if mutation_count else 0.0
    policy_improvement_velocity = round(sum(improvement_values) / len(improvement_values), 6) if improvement_values else 0.0

    experiment_rows = db.query(Experiment).all()
    experiment_count = len(experiment_rows)
    winning_experiments = 0
    for experiment in experiment_rows:
        effect_size = _experiment_effect_size(db, experiment.experiment_id)
        if effect_size is not None and effect_size > 0:
            winning_experiments += 1
    experiment_win_rate = round(winning_experiments / experiment_count, 6) if experiment_count else 0.0

    causal_confidence_mean = round(
        float(
            db.query(func.coalesce(func.avg(KnowledgeEdge.confidence), 0.0))
            .filter(KnowledgeEdge.edge_type == 'policy_outcome')
            .scalar()
            or 0.0
        ),
        6,
    )

    now = datetime.now(UTC)
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start.replace(hour=23, minute=59, second=59, microsecond=999999)
    snapshot = (
        db.query(LearningMetricSnapshot)
        .filter(LearningMetricSnapshot.timestamp >= window_start, LearningMetricSnapshot.timestamp <= window_end)
        .order_by(LearningMetricSnapshot.timestamp.desc(), LearningMetricSnapshot.id.desc())
        .first()
    )
    if snapshot is None:
        snapshot = LearningMetricSnapshot(timestamp=now)
        db.add(snapshot)
    else:
        snapshot.timestamp = now
    snapshot.mutation_success_rate = mutation_success_rate
    snapshot.experiment_win_rate = experiment_win_rate
    snapshot.causal_confidence_mean = causal_confidence_mean
    snapshot.policy_improvement_velocity = policy_improvement_velocity
    snapshot.mutation_count = mutation_count
    snapshot.experiment_count = experiment_count
    db.flush()
    return snapshot


def snapshot_learning_metrics_payload(db: Session) -> dict[str, Any]:
    row = snapshot_learning_metrics(db)
    return {
        'timestamp': row.timestamp.isoformat(),
        'mutation_success_rate': float(row.mutation_success_rate),
        'experiment_win_rate': float(row.experiment_win_rate),
        'causal_confidence_mean': float(row.causal_confidence_mean),
        'policy_improvement_velocity': float(row.policy_improvement_velocity),
        'mutation_count': int(row.mutation_count),
        'experiment_count': int(row.experiment_count),
    }


def _parent_child_pairs(db: Session) -> list[tuple[str, str]]:
    rows = (
        db.query(StrategyEvolutionLog.parent_policy, StrategyEvolutionLog.new_policy)
        .order_by(StrategyEvolutionLog.created_at.asc(), StrategyEvolutionLog.id.asc())
        .all()
    )
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for parent_policy, new_policy in rows:
        key = (str(parent_policy), str(new_policy))
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs


def _policy_mean_score(db: Session, policy_id: str) -> float | None:
    value = (
        db.query(func.avg(PolicyPerformance.success_score))
        .filter(PolicyPerformance.policy_id == policy_id)
        .scalar()
    )
    return None if value is None else float(value)


def _experiment_effect_size(db: Session, experiment_id: str) -> float | None:
    treatment = _cohort_success_rate(db, experiment_id, 'treatment')
    control = _cohort_success_rate(db, experiment_id, 'control')
    if treatment is None and control is None:
        return None
    return round((treatment or 0.0) - (control or 0.0), 6)


def _cohort_success_rate(db: Session, experiment_id: str, cohort: str) -> float | None:
    row = (
        db.query(func.avg(ExperimentOutcome.success_flag))
        .join(ExperimentAssignment, ExperimentAssignment.id == ExperimentOutcome.assignment_id)
        .filter(
            ExperimentOutcome.experiment_id == experiment_id,
            ExperimentAssignment.cohort == cohort,
        )
        .scalar()
    )
    return None if row is None else float(row)
