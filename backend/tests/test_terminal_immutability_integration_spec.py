from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from app.core.passwords import hash_password
from app.models.campaign import Campaign
from app.enums import StrategyRecommendationStatus
from app.utils.enum_guard import ensure_enum
from app.models.intelligence import StrategyRecommendation
from app.models.tenant import Tenant
from app.models.user import User


def _seed_strategy_dependencies(db_session) -> None:
    tenant = Tenant(id="tenant-1", name="Terminal Immutability Tenant")
    db_session.add(tenant)
    db_session.flush()

    actor = User(
        id="actor-1",
        tenant_id=tenant.id,
        email="terminal-immutability@example.com",
        hashed_password=hash_password("pass"),
        is_active=True,
        is_platform_user=False,
        platform_role=None,
    )
    campaign = Campaign(
        id="campaign-1",
        tenant_id=tenant.id,
        name="Test Campaign",
        domain="example.com",
    )
    db_session.add_all([actor, campaign])
    db_session.flush()


def test_terminal_record_update_blocked_by_trigger(db_session) -> None:
    _seed_strategy_dependencies(db_session)
    row = StrategyRecommendation(
        tenant_id="tenant-1",
        campaign_id="campaign-1",
        recommendation_type="hardening-spec",
        rationale="initial",
        confidence=1.0,
        confidence_score=1.0,
        evidence_json='["evidence"]',
        risk_tier=0,
        rollback_plan_json='{"steps":["noop"]}',
        status=ensure_enum(StrategyRecommendationStatus.ARCHIVED, StrategyRecommendationStatus),
        idempotency_key="immutability-test-1",
    )
    db_session.add(row)
    db_session.commit()

    row.rationale = "mutated"
    with pytest.raises(DatabaseError):
        db_session.commit()
    db_session.rollback()


def test_governed_override_requires_reason_and_writes_audit(db_session) -> None:
    dialect = db_session.bind.dialect.name.lower() if db_session.bind is not None else ""
    if dialect != "postgresql":
        pytest.skip("SECURITY DEFINER override is PostgreSQL-only")

    _seed_strategy_dependencies(db_session)
    row = StrategyRecommendation(
        tenant_id="tenant-1",
        campaign_id="campaign-1",
        recommendation_type="hardening-spec",
        rationale="initial",
        confidence=1.0,
        confidence_score=1.0,
        evidence_json='["evidence"]',
        risk_tier=0,
        rollback_plan_json='{"steps":["noop"]}',
        status=ensure_enum(StrategyRecommendationStatus.ARCHIVED, StrategyRecommendationStatus),
        idempotency_key="immutability-test-2",
    )
    db_session.add(row)
    db_session.commit()

    with pytest.raises(DatabaseError):
        db_session.execute(
            text(
                """
                SELECT governed_override_strategy_recommendation(
                    :recommendation_id,
                    :actor_user_id,
                    :reason,
                    :new_status,
                    :new_rationale
                )
                """
            ),
            {
                "recommendation_id": row.id,
                "actor_user_id": "actor-1",
                "reason": "",
                "new_status": "ARCHIVED",
                "new_rationale": "override",
            },
        )
        db_session.commit()

    db_session.rollback()

    db_session.execute(
        text(
            """
            SELECT governed_override_strategy_recommendation(
                :recommendation_id,
                :actor_user_id,
                :reason,
                :new_status,
                :new_rationale
            )
            """
        ),
        {
            "recommendation_id": row.id,
            "actor_user_id": "actor-1",
            "reason": "operational correction",
            "new_status": "ARCHIVED",
            "new_rationale": "override",
        },
    )
    db_session.commit()

    audit_count = db_session.execute(
        text("SELECT count(*) FROM audit_logs WHERE event_type = 'strategy.override' AND tenant_id = :tenant_id"),
        {"tenant_id": "tenant-1"},
    ).scalar_one()
    assert int(audit_count) >= 1








