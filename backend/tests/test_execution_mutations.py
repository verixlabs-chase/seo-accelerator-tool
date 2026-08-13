from __future__ import annotations

from app.intelligence import recommendation_execution_engine as execution_engine
from app.enums import StrategyRecommendationStatus
from app.intelligence.recommendation_execution_engine import approve_execution, execute_recommendation, rollback_execution, schedule_execution
from app.models.execution_mutation import ExecutionMutation
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def _recommendation(db_session, *, tenant_id: str, campaign_id: str, recommendation_type: str) -> StrategyRecommendation:
    row = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        recommendation_type=recommendation_type,
        rationale='mutation execution test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _preview_and_approve(db_session, execution: RecommendationExecution) -> None:
    planned = execute_recommendation(execution.id, db=db_session, dry_run=True)
    assert isinstance(planned, dict)
    approve_execution(
        execution.id,
        approved_by="test-owner",
        preview_hash=planned["preview"]["preview_hash"],
        db=db_session,
    )


def test_execution_persists_mutation_audit_rows(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Mutation Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Mutation Org')
    org.plan_type = 'multi_location'
    db_session.commit()
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Mutation Campaign', domain='mutation.example')
    recommendation = _recommendation(db_session, tenant_id=tenant.id, campaign_id=campaign.id, recommendation_type='fix_missing_title')
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    _preview_and_approve(db_session, execution)
    completed = execute_recommendation(execution.id, db=db_session)
    assert isinstance(completed, RecommendationExecution)
    assert completed.status == 'completed'
    rows = db_session.query(ExecutionMutation).filter(ExecutionMutation.execution_id == execution.id).all()
    assert len(rows) == 2
    assert {row.mutation_type for row in rows} == {'update_meta_title', 'update_meta_description'}
    for row in rows:
        assert row.before_state is not None
        assert row.after_state is not None
        assert row.rollback_payload is not None
        assert row.status == 'applied'


def test_execution_helpers_do_not_commit_the_shared_action_transaction(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name='Atomic Execution Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Atomic Execution Org')
    org.plan_type = 'multi_location'
    db_session.commit()
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Atomic Execution Campaign',
        domain='atomic-execution.example',
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
    )
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    _preview_and_approve(db_session, execution)

    def unexpected_commit() -> None:
        raise AssertionError('execution helper committed the request transaction')

    monkeypatch.setattr(db_session, 'commit', unexpected_commit)

    completed = execute_recommendation(execution.id, db=db_session)

    assert isinstance(completed, RecommendationExecution)
    assert completed.status == 'completed'
    assert db_session.query(ExecutionMutation).filter(
        ExecutionMutation.execution_id == execution.id,
    ).count() == 1


def test_outcome_bookkeeping_failure_does_not_undo_a_delivered_action(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name='Outcome Isolation Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Outcome Isolation Org')
    org.plan_type = 'multi_location'
    db_session.commit()
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Outcome Isolation Campaign',
        domain='outcome-isolation.example',
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='create_content_brief',
    )
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    _preview_and_approve(db_session, execution)

    def fail_outcome_bookkeeping(*_args, **_kwargs):
        raise RuntimeError('simulated derived-bookkeeping failure')

    monkeypatch.setattr(execution_engine, 'record_execution_outcome', fail_outcome_bookkeeping)

    completed = execute_recommendation(execution.id, db=db_session)

    assert isinstance(completed, RecommendationExecution)
    assert completed.status == 'completed'
    assert completed.last_error is None
    assert db_session.query(ExecutionMutation).filter(
        ExecutionMutation.execution_id == execution.id,
    ).count() == 1


def test_execution_can_be_rolled_back(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Rollback Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Rollback Org')
    org.plan_type = 'multi_location'
    db_session.commit()
    campaign = create_test_campaign(db_session, org.id, tenant_id=tenant.id, name='Rollback Campaign', domain='rollback.example')
    recommendation = _recommendation(db_session, tenant_id=tenant.id, campaign_id=campaign.id, recommendation_type='publish_schema_markup')
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    _preview_and_approve(db_session, execution)
    completed = execute_recommendation(execution.id, db=db_session)
    assert isinstance(completed, RecommendationExecution)
    assert completed.status == 'completed'
    rolled_back = rollback_execution(execution.id, requested_by='tester', db=db_session)
    assert isinstance(rolled_back, RecommendationExecution)
    assert rolled_back.status == 'rolled_back'
    assert rolled_back.rolled_back_at is not None
    rows = db_session.query(ExecutionMutation).filter(ExecutionMutation.execution_id == execution.id).all()
    assert rows
    assert all(row.status == 'rolled_back' for row in rows)
    assert all(row.rolled_back_at is not None for row in rows)


def test_failed_public_verification_preserves_and_can_rollback_applied_changes(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    tenant = create_test_tenant(name="Verification Rollback Tenant")
    org = create_test_org(tenant_id=tenant.id, name="Verification Rollback Org")
    org.plan_type = "multi_location"
    db_session.commit()
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name="Verification Rollback Campaign",
        domain="verification-rollback.example",
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type="fix_missing_title",
    )
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    _preview_and_approve(db_session, execution)

    def fake_apply_mutations(db, *, execution, mutations):  # noqa: ANN001
        results = [
            {
                "mutation_id": mutation["mutation_id"],
                "status": "applied",
                "mutation_type": mutation["action"],
                "target_url": mutation["target_url"],
                "before_state": {"value": "before"},
                "after_state": {"value": "after"},
                "rollback_payload": {"restore": "before"},
            }
            for mutation in mutations
        ]
        return {
            "provider_name": "wordpress_plugin",
            "delivery_mode": "wordpress_plugin",
            "results": results,
            "public_verification": {
                "passed": False,
                "checks_total": len(results),
                "checks_passed": 0,
                "checks_failed": len(results),
                "pages_checked": 1,
                "rollback_available": True,
                "results": [
                    {
                        "mutation_id": result["mutation_id"],
                        "passed": False,
                        "status": "failed",
                        "message": "The approved value is not public yet.",
                    }
                    for result in results
                ],
            },
        }

    monkeypatch.setattr(execution_engine, "apply_mutations", fake_apply_mutations)
    failed = execute_recommendation(execution.id, db=db_session)
    assert isinstance(failed, RecommendationExecution)
    assert failed.status == "failed"
    assert failed.result_summary is not None
    assert "wordpress_public_verification_failed" in failed.result_summary
    rows = db_session.query(ExecutionMutation).filter(
        ExecutionMutation.execution_id == execution.id
    ).all()
    assert rows
    assert all(row.status == "applied" for row in rows)

    rolled_back = rollback_execution(execution.id, requested_by="test-owner", db=db_session)
    assert isinstance(rolled_back, RecommendationExecution)
    assert rolled_back.status == "rolled_back"
    assert all(row.status == "rolled_back" for row in rows)


def test_solo_plan_cannot_deliver_wordpress_mutations(
    db_session,
    create_test_tenant,
    create_test_org,
) -> None:
    tenant = create_test_tenant(name='Solo Mutation Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Solo Mutation Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Solo Mutation Campaign',
        domain='solo-mutation.example',
    )
    recommendation = _recommendation(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='fix_missing_title',
    )
    execution = schedule_execution(recommendation.id, db=db_session)
    assert isinstance(execution, RecommendationExecution)
    _preview_and_approve(db_session, execution)

    blocked = execute_recommendation(execution.id, db=db_session)

    assert isinstance(blocked, RecommendationExecution)
    assert blocked.status == 'failed'
    assert blocked.result_summary is not None
    assert 'wordpress_execution_upgrade_required' in blocked.result_summary
    assert db_session.query(ExecutionMutation).filter(
        ExecutionMutation.execution_id == execution.id,
    ).count() == 0
