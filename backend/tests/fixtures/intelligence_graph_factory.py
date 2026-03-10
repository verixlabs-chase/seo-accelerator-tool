from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.models.campaign import Campaign
from app.models.experiment import Experiment, ExperimentAssignment
from app.models.intelligence import StrategyRecommendation
from app.models.policy_performance import PolicyPerformance
from app.models.strategy_evolution_log import StrategyEvolutionLog
from app.models.tenant import Tenant
from app.utils.enum_guard import ensure_enum


def create_intelligence_graph(session, *, campaigns: int = 4, experiments: int = 2):
    campaign_count = max(1, int(campaigns))
    experiment_count = max(1, int(experiments))
    total_slots = max(campaign_count, experiment_count * 2)

    tenant = Tenant(id='tenant-intelligence-graph', name='Intelligence Graph Tenant', status='Active')
    session.add(tenant)
    session.flush()

    campaign_rows = []
    for idx in range(1, total_slots + 1):
        campaign = Campaign(
            id=f'camp-{idx}',
            tenant_id=tenant.id,
            name=f'Campaign {idx}',
            domain=f'camp-{idx}.example',
        )
        session.add(campaign)
        campaign_rows.append(campaign)
    session.flush()

    recommendation_rows = []
    policy_rows = []
    for idx, campaign in enumerate(campaign_rows, start=1):
        policy_id = _policy_id_for_slot(idx)
        recommendation = StrategyRecommendation(
            id=f'r{idx}',
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_type=f'policy::{policy_id}',
            rationale=f'recommendation for {policy_id}',
            confidence=0.5,
            confidence_score=0.5,
            evidence_json='{}',
            rollback_plan_json='{}',
            status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
        )
        session.add(recommendation)
        recommendation_rows.append(recommendation)
        policy_rows.append(
            PolicyPerformance(
                policy_id=policy_id,
                campaign_id=campaign.id,
                industry='local',
                success_score=_success_score_for_slot(idx),
                execution_count=3,
                confidence=0.3,
            )
        )
    session.add_all(policy_rows)
    session.flush()

    experiment_rows = []
    assignment_rows = []
    evolution_logs = []
    for exp_idx in range(1, experiment_count + 1):
        child_policy = f'child-{chr(96 + exp_idx)}'
        experiment = Experiment(
            policy_id=child_policy,
            hypothesis=f'hypothesis for {child_policy}',
            experiment_type='strategy_evolution',
            cohort_size=10,
            status='completed',
            industry='local',
        )
        session.add(experiment)
        session.flush()
        experiment_rows.append(experiment)

        control_slot = ((exp_idx - 1) * 2) + 1
        treatment_slot = control_slot + 1
        assignment_rows.extend(
            [
                ExperimentAssignment(
                    experiment_id=experiment.experiment_id,
                    campaign_id=f'camp-{control_slot}',
                    cohort='control',
                    bucket=10,
                    assigned_policy_id=f'baseline::{child_policy}',
                ),
                ExperimentAssignment(
                    experiment_id=experiment.experiment_id,
                    campaign_id=f'camp-{treatment_slot}',
                    cohort='treatment',
                    bucket=80,
                    assigned_policy_id=child_policy,
                ),
            ]
        )
        evolution_logs.append(
            StrategyEvolutionLog(
                parent_policy=f'parent-{chr(96 + exp_idx)}',
                new_policy=child_policy,
                mutation_type='extend_policy_variant',
            )
        )

    session.add_all(assignment_rows)
    session.add_all(evolution_logs)
    session.flush()

    return {
        'tenant': tenant,
        'campaigns': campaign_rows[:campaign_count],
        'recommendations': recommendation_rows[:campaign_count],
        'experiments': experiment_rows,
        'assignments': assignment_rows,
        'policy_performance': policy_rows[:campaign_count],
        'evolution_logs': evolution_logs,
    }


def _policy_id_for_slot(slot: int) -> str:
    pair_index = ((slot - 1) // 2) + 1
    suffix = chr(96 + pair_index)
    if slot % 2 == 1:
        return f'parent-{suffix}'
    return f'child-{suffix}'


def _success_score_for_slot(slot: int) -> float:
    base = {1: 0.2, 2: 0.5, 3: 0.6, 4: 0.3}
    if slot in base:
        return base[slot]
    return 0.25 if slot % 2 == 1 else 0.45
