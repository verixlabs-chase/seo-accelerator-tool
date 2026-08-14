from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.session import set_session_security_context
from app.models.ai_visibility import (
    AISearchCollectionRun,
    AISearchEngineRegistry,
    AISearchObservation,
    AISearchProviderContractRegistry,
    AISearchQuestionSet,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.cost_economics import CostLedgerEntry
from app.models.user import User
from app.services import ai_visibility_service


pytestmark = pytest.mark.postgres_required


def _question_set(db: Session, *, user: User, suffix: str) -> AISearchQuestionSet:
    organization_id = str(user.tenant_id)
    location = BusinessLocation(
        organization_id=organization_id,
        name=f"AIV location {suffix}",
        domain=f"aiv-{suffix}.example",
        city="Reno",
        region="Nevada",
        country_code="US",
        status="active",
    )
    db.add(location)
    db.flush()
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location.id,
        name=f"AIV campaign {suffix}",
        domain=f"aiv-{suffix}.example",
    )
    db.add(campaign)
    db.flush()
    row = AISearchQuestionSet(
        tenant_id=organization_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        version=1,
        generator_version="security-fixture-v1",
        questions=[],
        context_snapshot={},
        context_hash=uuid.uuid4().hex * 2,
        question_set_hash=uuid.uuid4().hex * 2,
        status="frozen",
        created_by_user_id=user.id,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def _registries(db: Session, *, suffix: str):
    engine = AISearchEngineRegistry(
        engine_code=f"security-{suffix}",
        public_name=f"Security engine {suffix}",
        registry_version="1",
        collection_method="fixture",
        status="candidate",
        customer_visible=False,
        automatic_activation_allowed=False,
        evidence_qa_passed=False,
        cost_qa_passed=False,
        comparison_qa_passed=False,
        supported_geographies=[],
        supported_languages=[],
        supported_devices=[],
        supported_personalization_policies=[],
        supported_evidence_facts=[],
        limitations=[],
        content_hash=uuid.uuid4().hex * 2,
    )
    contract = AISearchProviderContractRegistry(
        provider_key=f"security-{suffix}",
        contract_code="security-fixture",
        contract_version="1",
        collection_mode="fixture",
        request_schema_version="1",
        response_schema_version="1",
        parser_version="parser-v1",
        normalizer_version="normalizer-v1",
        engine_mappings=[],
        required_inputs=[],
        guaranteed_evidence_facts=[],
        optional_evidence_facts=[],
        unsupported_evidence_facts=[],
        raw_response_retention_days=0,
        billable_unit="fixture",
        status="candidate",
        production_qa_passed=False,
        pricing_qa_passed=False,
        automatic_activation_allowed=False,
        content_hash=uuid.uuid4().hex * 2,
    )
    db.add_all([engine, contract])
    db.flush()
    return engine, contract


def _run(
    question_set: AISearchQuestionSet,
    engine: AISearchEngineRegistry,
    contract: AISearchProviderContractRegistry,
    *,
    suffix: str,
) -> AISearchCollectionRun:
    now = datetime.now(UTC)
    return AISearchCollectionRun(
        tenant_id=question_set.tenant_id,
        organization_id=question_set.organization_id,
        campaign_id=question_set.campaign_id,
        business_location_id=question_set.business_location_id,
        question_set_id=question_set.id,
        engine_registry_id=engine.id,
        provider_contract_id=contract.id,
        comparison_version="comparison-v1",
        collection_contract_version="1",
        parser_version="parser-v1",
        normalizer_version="normalizer-v1",
        personalization_policy="none",
        comparison_scope_hash=uuid.uuid4().hex * 2,
        location_snapshot={},
        language_code="en",
        device="desktop",
        status="partial",
        request_hash=uuid.uuid4().hex * 2,
        idempotency_key=f"security-{suffix}",
        requested_observation_count=1,
        collected_observation_count=1,
        coverage_summary={},
        requested_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def _observation(run: AISearchCollectionRun, *, suffix: str) -> AISearchObservation:
    now = datetime.now(UTC)
    return AISearchObservation(
        tenant_id=run.tenant_id,
        organization_id=run.organization_id,
        campaign_id=run.campaign_id,
        business_location_id=run.business_location_id,
        run_id=run.id,
        question_set_id=run.question_set_id,
        engine_registry_id=run.engine_registry_id,
        provider_contract_id=run.provider_contract_id,
        question_id=f"question-{suffix}",
        question_text_hash=uuid.uuid4().hex * 2,
        collection_contract_version=run.collection_contract_version,
        parser_version=run.parser_version,
        normalizer_version=run.normalizer_version,
        personalization_policy=run.personalization_policy,
        location_snapshot={},
        language_code=run.language_code,
        device=run.device,
        mention_state="not_observed",
        recommendation_state="not_measured",
        citation_state="not_measured",
        link_state="not_measured",
        cited_sources=[],
        competitor_entities=[],
        limitations=[],
        raw_response_hash=uuid.uuid4().hex * 2,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=now,
        created_at=now,
    )


def _seed_collection_artifacts(db: Session):
    user_a = db.query(User).filter(User.email == "a@example.com").one()
    user_b = db.query(User).filter(User.email == "b@example.com").one()
    question_a = _question_set(db, user=user_a, suffix="run-a")
    question_b = _question_set(db, user=user_b, suffix="run-b")
    engine, contract = _registries(db, suffix=uuid.uuid4().hex[:8])
    run_a = _run(question_a, engine, contract, suffix="a")
    run_b = _run(question_b, engine, contract, suffix="b")
    db.execute(
        text(
            "ALTER TABLE public.ai_search_collection_runs DISABLE TRIGGER "
            "trg_ai_search_collection_runs_preflight"
        )
    )
    try:
        db.add_all([run_a, run_b])
        db.flush()
    finally:
        db.execute(
            text(
                "ALTER TABLE public.ai_search_collection_runs ENABLE TRIGGER "
                "trg_ai_search_collection_runs_preflight"
            )
        )
    observation_a = _observation(run_a, suffix="a")
    observation_b = _observation(run_b, suffix="b")
    db.add_all([observation_a, observation_b])
    db.commit()
    return user_a, user_b, question_a, question_b, run_a, run_b, observation_a, observation_b


def test_ai_visibility_question_sets_are_rls_scoped_and_immutable(
    db_session: Session,
) -> None:
    user_a = db_session.query(User).filter(User.email == "a@example.com").one()
    user_b = db_session.query(User).filter(User.email == "b@example.com").one()
    row_a = _question_set(db_session, user=user_a, suffix="a")
    row_b = _question_set(db_session, user=user_b, suffix="b")
    db_session.commit()

    db_session.add(
        AISearchQuestionSet(
            tenant_id=row_a.tenant_id,
            organization_id=row_a.organization_id,
            campaign_id=row_b.campaign_id,
            business_location_id=row_b.business_location_id,
            version=2,
            generator_version="security-fixture-v1",
            questions=[],
            context_snapshot={},
            context_hash=uuid.uuid4().hex * 2,
            question_set_hash=uuid.uuid4().hex * 2,
            status="frozen",
            created_by_user_id=user_a.id,
            created_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        visible = set(
            isolated.execute(
                select(AISearchQuestionSet.id).where(
                    AISearchQuestionSet.id.in_([row_a.id, row_b.id])
                )
            ).scalars()
        )
        assert visible == {row_a.id}

        with pytest.raises(DBAPIError):
            isolated.execute(
                update(AISearchQuestionSet)
                .where(AISearchQuestionSet.id == row_a.id)
                .values(generator_version="mutated")
            )
            isolated.flush()
    finally:
        isolated.rollback()
        isolated.close()


def test_ai_visibility_runs_and_observations_are_rls_scoped_and_immutable(
    db_session: Session,
) -> None:
    (
        user_a,
        _user_b,
        _question_a,
        _question_b,
        run_a,
        run_b,
        observation_a,
        observation_b,
    ) = _seed_collection_artifacts(db_session)

    isolated = Session(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    try:
        set_session_security_context(
            isolated,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        visible_runs = set(
            isolated.execute(
                select(AISearchCollectionRun.id).where(
                    AISearchCollectionRun.id.in_([run_a.id, run_b.id])
                )
            ).scalars()
        )
        visible_observations = set(
            isolated.execute(
                select(AISearchObservation.id).where(
                    AISearchObservation.id.in_([observation_a.id, observation_b.id])
                )
            ).scalars()
        )
        assert visible_runs == {run_a.id}
        assert visible_observations == {observation_a.id}
        cross_run_update = isolated.execute(
            update(AISearchCollectionRun)
            .where(AISearchCollectionRun.id == run_b.id)
            .values(safe_error_message="must not update")
        )
        assert cross_run_update.rowcount == 0
    finally:
        isolated.rollback()
        isolated.close()

    run_identity_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            run_identity_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            run_identity_session.execute(
                update(AISearchCollectionRun)
                .where(AISearchCollectionRun.id == run_a.id)
                .values(comparison_version="mutated")
            )
            run_identity_session.flush()
    finally:
        run_identity_session.rollback()
        run_identity_session.close()

    observation_session = Session(
        bind=db_session.get_bind(), autoflush=False, autocommit=False
    )
    try:
        set_session_security_context(
            observation_session,
            tenant_id=str(user_a.tenant_id),
            organization_id=str(user_a.tenant_id),
            user_id=user_a.id,
            platform_access=False,
        )
        with pytest.raises(DBAPIError):
            observation_session.execute(
                update(AISearchObservation)
                .where(AISearchObservation.id == observation_a.id)
                .values(mention_state="observed")
            )
            observation_session.flush()
    finally:
        observation_session.rollback()
        observation_session.close()


def test_ai_visibility_preview_is_side_effect_free_and_run_preflight_blocks(
    db_session: Session,
) -> None:
    (
        user_a,
        _user_b,
        question_a,
        _question_b,
        run_a,
        _run_b,
        _observation_a,
        _observation_b,
    ) = _seed_collection_artifacts(db_session)
    before = {
        "runs": db_session.query(AISearchCollectionRun).count(),
        "ledger": db_session.query(CostLedgerEntry).count(),
        "questions": db_session.query(AISearchQuestionSet).count(),
    }
    preview = ai_visibility_service.preview_collection(
        db_session,
        tenant_id=str(user_a.tenant_id),
        organization_id=str(user_a.tenant_id),
        campaign_id=question_a.campaign_id,
    )
    after = {
        "runs": db_session.query(AISearchCollectionRun).count(),
        "ledger": db_session.query(CostLedgerEntry).count(),
        "questions": db_session.query(AISearchQuestionSet).count(),
    }
    assert preview["ready"] is False
    assert preview["side_effects"] == {
        "external_request_sent": False,
        "reservation_created": False,
        "charge_created": False,
        "run_created": False,
    }
    assert after == before

    blocked = _run(
        question_a,
        db_session.get(AISearchEngineRegistry, run_a.engine_registry_id),
        db_session.get(AISearchProviderContractRegistry, run_a.provider_contract_id),
        suffix="preflight-blocked",
    )
    db_session.add(blocked)
    with pytest.raises(DBAPIError, match="AI search collection is not configured"):
        db_session.flush()
    db_session.rollback()
