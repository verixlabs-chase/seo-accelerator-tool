from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import (
    Column,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    text,
)
from sqlalchemy.exc import IntegrityError

from app.models.ai_visibility import (
    AISearchCollectionRun,
    AISearchEngineRegistry,
    AISearchObservation,
    AISearchProviderContractRegistry,
    AISearchQuestionSet,
)
from app.models.business_location import BusinessLocation
from app.models.business_service import BusinessService
from app.models.business_service_area import BusinessServiceArea
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.user import User
from app.services import ai_visibility_service


def _workspace(db_session) -> tuple[User, Campaign]:
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization_id = str(user.tenant_id)
    location = BusinessLocation(
        organization_id=organization_id,
        name=f"Reno-{uuid.uuid4().hex[:8]}",
        domain="example.test",
        city="Reno",
        region="Nevada",
        country_code="US",
        status="active",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location.id,
        name=f"Campaign-{uuid.uuid4().hex[:8]}",
        domain="example.test",
    )
    db_session.add(campaign)
    db_session.flush()
    return user, campaign


def _service(
    db_session,
    campaign: Campaign,
    *,
    name: str,
    status: str,
) -> BusinessService:
    row = BusinessService(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        business_location_id=campaign.business_location_id,
        scope_type="location",
        scope_key=str(campaign.business_location_id),
        name=name,
        normalized_name=name.casefold(),
        aliases=[],
        status=status,
        source="manual" if status == "confirmed" else "website",
        confidence=1.0,
        evidence=[],
    )
    db_session.add(row)
    db_session.flush()
    return row


def _area(
    db_session,
    campaign: Campaign,
    *,
    name: str,
    status: str = "confirmed",
    relationship: str = "included",
    area_type: str = "city",
    region: str | None = "Nevada",
) -> BusinessServiceArea:
    row = BusinessServiceArea(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        business_location_id=str(campaign.business_location_id),
        area_type=area_type,
        name=name,
        normalized_name=name.casefold(),
        region=region,
        country_code="US",
        relationship=relationship,
        status=status,
        source="manual",
        confidence=1.0,
        evidence=[],
    )
    db_session.add(row)
    db_session.flush()
    return row


def _candidate_contract(db_session, *, provider_key: str = "internal-fixture"):
    row = AISearchProviderContractRegistry(
        provider_key=provider_key,
        contract_code=f"fixture-{uuid.uuid4().hex[:8]}",
        contract_version="1",
        collection_mode="fixture",
        request_schema_version="1",
        response_schema_version="1",
        parser_version="parser-v1",
        normalizer_version="normalizer-v1",
        engine_mappings=[],
        required_inputs=[],
        guaranteed_evidence_facts=["mention"],
        optional_evidence_facts=[],
        unsupported_evidence_facts=["recommendation", "citation", "link"],
        raw_response_retention_days=0,
        billable_unit="fixture",
        status="candidate",
        production_qa_passed=False,
        pricing_qa_passed=False,
        automatic_activation_allowed=False,
        content_hash=uuid.uuid4().hex * 2,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_frozen_questions_use_only_confirmed_services_and_named_included_areas(
    db_session,
) -> None:
    user, campaign = _workspace(db_session)
    confirmed = _service(
        db_session,
        campaign,
        name="Junk removal",
        status="confirmed",
    )
    _service(db_session, campaign, name="Roof repair", status="suggested")
    _service(db_session, campaign, name="Moving", status="rejected")
    area = _area(db_session, campaign, name="Reno")
    _area(db_session, campaign, name="Sparks", status="suggested")
    _area(db_session, campaign, name="Carson City", relationship="excluded")
    _area(
        db_session,
        campaign,
        name="Within 25 miles",
        area_type="radius",
        region=None,
    )
    db_session.commit()

    first = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )
    repeated = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )

    assert first["created"] is True
    assert repeated["created"] is False
    assert repeated["question_set"]["id"] == first["question_set"]["id"]
    assert repeated["question_set"]["question_set_hash"] == first["question_set"][
        "question_set_hash"
    ]
    assert first["question_set"]["version"] == 1
    assert first["question_set"]["questions"] == [
        {
            "id": first["question_set"]["questions"][0]["id"],
            "text": "Which businesses provide Junk removal in Reno, Nevada?",
            "service_id": confirmed.id,
            "service_name": "Junk removal",
            "service_area_id": area.id,
            "service_area_name": "Reno, Nevada",
        }
    ]


def test_changed_confirmed_context_marks_old_set_stale_and_creates_next_version(
    db_session,
) -> None:
    user, campaign = _workspace(db_session)
    _service(db_session, campaign, name="Junk removal", status="confirmed")
    _area(db_session, campaign, name="Reno")
    db_session.commit()
    first = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )

    _service(db_session, campaign, name="Appliance removal", status="confirmed")
    db_session.commit()
    stale = ai_visibility_service.get_summary(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    assert stale["setup"]["question_set_ready"] is False
    assert stale["questions"]["current_context"] is False
    assert stale["next_action"]["code"] == "update_questions"

    second = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )
    assert second["created"] is True
    assert second["question_set"]["version"] == 2
    assert second["question_set"]["question_set_hash"] != first["question_set"][
        "question_set_hash"
    ]
    assert second["current_context"] is True


def test_old_generator_marks_questions_stale_and_regenerates_next_version(
    db_session,
) -> None:
    user, campaign = _workspace(db_session)
    _service(db_session, campaign, name="Junk removal", status="confirmed")
    _area(db_session, campaign, name="Reno")
    context = ai_visibility_service._confirmed_context(db_session, campaign=campaign)
    questions = ai_visibility_service._build_questions(context)
    context_snapshot = ai_visibility_service._context_snapshot(
        context,
        question_count=len(questions),
    )
    context_hash = ai_visibility_service._hash(context_snapshot)
    legacy_generator = "ai-search-questions-v0"
    legacy = AISearchQuestionSet(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=str(campaign.business_location_id),
        version=1,
        generator_version=legacy_generator,
        questions=questions,
        context_snapshot=context_snapshot,
        context_hash=context_hash,
        question_set_hash=ai_visibility_service._hash(
            {
                "generator_version": legacy_generator,
                "context_hash": context_hash,
                "questions": questions,
            }
        ),
        status="frozen",
        created_by_user_id=user.id,
    )
    db_session.add(legacy)
    db_session.commit()

    current = ai_visibility_service.get_current_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    preview = ai_visibility_service.preview_collection(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    summary = ai_visibility_service.get_summary(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    assert current["current_context"] is False
    assert current["next_action"]["code"] == "update_questions"
    assert preview["checks"]["question_set_current"] is False
    assert "questions_outdated" in {item["code"] for item in preview["blockers"]}
    assert summary["setup"]["question_set_ready"] is False
    assert summary["questions"]["current_context"] is False

    regenerated = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )
    assert regenerated["created"] is True
    assert regenerated["current_context"] is True
    assert regenerated["question_set"]["version"] == 2
    assert regenerated["question_set"]["generator_version"] == (
        ai_visibility_service.QUESTION_GENERATOR_VERSION
    )


def test_question_context_freezes_target_and_confirmed_competitor_identity(
    db_session,
) -> None:
    user, campaign = _workspace(db_session)
    _service(db_session, campaign, name="Junk removal", status="confirmed")
    _area(db_session, campaign, name="Reno")
    confirmed = Competitor(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        domain="confirmed.example",
        label="Confirmed Competitor",
        review_status="confirmed",
    )
    db_session.add_all(
        [
            confirmed,
            Competitor(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                domain="suggested.example",
                label="Suggested Competitor",
                review_status="suggested",
            ),
        ]
    )
    db_session.commit()
    created = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )
    row = db_session.get(AISearchQuestionSet, created["question_set"]["id"])
    assert row is not None
    snapshot = row.context_snapshot
    assert snapshot["target_entity"]["business_name"].startswith("Reno-")
    assert snapshot["target_entity"]["domains"] == ["example.test"]
    assert len(snapshot["target_entity_hash"]) == 64
    assert snapshot["competitors"] == [
        {
            "id": confirmed.id,
            "name": "Confirmed Competitor",
            "domain": "confirmed.example",
            "review_status": "confirmed",
        }
    ]
    assert len(snapshot["competitor_set_hash"]) == 64


def test_unavailable_observation_is_excluded_from_measured_denominator(
    db_session,
) -> None:
    user, campaign = _workspace(db_session)
    _service(db_session, campaign, name="Junk removal", status="confirmed")
    _area(db_session, campaign, name="Reno")
    db_session.commit()
    question_set_payload = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )["question_set"]
    engine = AISearchEngineRegistry(
        engine_code="fixture_engine",
        public_name="Fixture Engine",
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
        content_hash="a" * 64,
    )
    db_session.add(engine)
    db_session.flush()
    contract = _candidate_contract(db_session)
    run = AISearchCollectionRun(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=str(campaign.business_location_id),
        question_set_id=question_set_payload["id"],
        engine_registry_id=engine.id,
        provider_contract_id=contract.id,
        comparison_version="comparison-v1",
        collection_contract_version="collection-contract-v1",
        parser_version="parser-v1",
        normalizer_version="normalizer-v1",
        personalization_policy="no_personalization",
        comparison_scope_hash="c" * 64,
        location_snapshot={"name": "Reno, Nevada"},
        language_code="en",
        device="unspecified",
        status="partial",
        request_hash="b" * 64,
        idempotency_key="fixture-run",
        requested_observation_count=3,
        collected_observation_count=3,
        coverage_summary={"requested": 3, "collected": 3},
    )
    db_session.add(run)
    db_session.flush()
    now = datetime.now(UTC)
    states = ("unavailable", "not_observed", "observed")
    for index, mention_state in enumerate(states):
        question_id = f"question-{index}"
        db_session.add(
            AISearchObservation(
                tenant_id=campaign.tenant_id,
                organization_id=str(campaign.organization_id),
                campaign_id=campaign.id,
                business_location_id=str(campaign.business_location_id),
                run_id=run.id,
                question_set_id=question_set_payload["id"],
                engine_registry_id=engine.id,
                provider_contract_id=contract.id,
                question_id=question_id,
                question_text_hash=hashlib.sha256(question_id.encode()).hexdigest(),
                collection_contract_version="collection-contract-v1",
                parser_version="parser-v1",
                normalizer_version="normalizer-v1",
                personalization_policy="no_personalization",
                location_snapshot={"name": "Reno, Nevada"},
                language_code="en",
                device="unspecified",
                mention_state=mention_state,
                recommendation_state="not_measured",
                citation_state="observed" if mention_state == "observed" else mention_state,
                link_state="not_measured",
                cited_sources=[],
                competitor_entities=[],
                limitations=[],
                raw_response_hash=str(index) * 64,
                evidence_hash=str(index + 3) * 64,
                observed_at=now,
            )
        )
    db_session.commit()

    observations = db_session.query(AISearchObservation).all()
    evidence = ai_visibility_service._evidence_summary(observations)
    assert evidence == {
        "checked": 2,
        "mentioned": 1,
        "recommended": 0,
        "cited": 1,
        "linked": 0,
        "unavailable": 1,
        "sample_size": 2,
        "coverage": {
            "mentioned": {
                "observed": 1,
                "measured": 2,
                "not_measured": 0,
                "unavailable": 1,
            },
            "recommended": {
                "observed": 0,
                "measured": 0,
                "not_measured": 3,
                "unavailable": 0,
            },
            "cited": {
                "observed": 1,
                "measured": 2,
                "not_measured": 0,
                "unavailable": 1,
            },
            "linked": {
                "observed": 0,
                "measured": 0,
                "not_measured": 3,
                "unavailable": 0,
            },
        },
    }

    summary = ai_visibility_service.get_summary(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    assert summary["summary"] == {
        "checked": 0,
        "mentioned": 0,
        "recommended": 0,
        "cited": 0,
        "linked": 0,
        "unavailable": 0,
        "sample_size": 0,
        "coverage": {
            fact: {
                "observed": 0,
                "measured": 0,
                "not_measured": 0,
                "unavailable": 0,
            }
            for fact in ("mentioned", "recommended", "cited", "linked")
        },
    }
    assert summary["competitors"] == {
        "items": [],
        "mentioned_count": 0,
        "status": "not_measured",
    }
    assert summary["history"]["items"] == []


def test_independent_citation_evidence_counts_when_mention_is_not_measured() -> None:
    observation = SimpleNamespace(
        mention_state="not_measured",
        recommendation_state="not_measured",
        citation_state="observed",
        link_state="not_measured",
    )
    evidence = ai_visibility_service._evidence_summary([observation])
    assert evidence["checked"] == 1
    assert evidence["sample_size"] == 1
    assert evidence["mentioned"] == 0
    assert evidence["cited"] == 1
    assert evidence["unavailable"] == 0
    assert evidence["coverage"]["mentioned"]["measured"] == 0
    assert evidence["coverage"]["cited"]["measured"] == 1


def test_all_unavailable_saved_observation_has_honest_truth_and_history(
    db_session,
) -> None:
    user, campaign = _workspace(db_session)
    _service(db_session, campaign, name="Junk removal", status="confirmed")
    _area(db_session, campaign, name="Reno")
    db_session.commit()
    question_set = ai_visibility_service.create_question_set(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        actor_user_id=user.id,
    )["question_set"]

    # AIV1-A intentionally forbids activating registries. This fixture bypasses only
    # those activation CHECKs so the customer summary for a future approved adapter
    # can be exercised without weakening the production migration.
    db_session.execute(text("PRAGMA ignore_check_constraints = ON"))
    try:
        engine = AISearchEngineRegistry(
            engine_code=f"approved-fixture-{uuid.uuid4().hex[:8]}",
            public_name="Approved fixture",
            registry_version="1",
            collection_method="fixture",
            status="active",
            customer_visible=True,
            automatic_activation_allowed=True,
            evidence_qa_passed=True,
            cost_qa_passed=True,
            comparison_qa_passed=True,
            supported_geographies=[],
            supported_languages=[],
            supported_devices=[],
            supported_personalization_policies=[],
            supported_evidence_facts=[
                "mention",
                "recommendation",
                "citation",
                "link",
            ],
            limitations=[],
            content_hash=uuid.uuid4().hex * 2,
        )
        contract = AISearchProviderContractRegistry(
            provider_key=f"approved-fixture-{uuid.uuid4().hex[:8]}",
            contract_code="approved-fixture",
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
            status="approved",
            production_qa_passed=True,
            pricing_qa_passed=True,
            automatic_activation_allowed=True,
            content_hash=uuid.uuid4().hex * 2,
        )
        db_session.add_all([engine, contract])
        db_session.flush()
    finally:
        db_session.execute(text("PRAGMA ignore_check_constraints = OFF"))

    now = datetime.now(UTC)
    run = AISearchCollectionRun(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=str(campaign.business_location_id),
        question_set_id=question_set["id"],
        engine_registry_id=engine.id,
        provider_contract_id=contract.id,
        comparison_version="comparison-v1",
        collection_contract_version="1",
        parser_version="parser-v1",
        normalizer_version="normalizer-v1",
        personalization_policy="none",
        comparison_scope_hash=uuid.uuid4().hex * 2,
        location_snapshot={"name": "Reno, Nevada"},
        language_code="en",
        device="desktop",
        status="partial",
        request_hash=uuid.uuid4().hex * 2,
        idempotency_key=f"unavailable-{uuid.uuid4().hex}",
        requested_observation_count=2,
        collected_observation_count=1,
        coverage_summary={},
        requested_at=now,
        completed_at=now,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        AISearchObservation(
            tenant_id=campaign.tenant_id,
            organization_id=str(campaign.organization_id),
            campaign_id=campaign.id,
            business_location_id=str(campaign.business_location_id),
            run_id=run.id,
            question_set_id=question_set["id"],
            engine_registry_id=engine.id,
            provider_contract_id=contract.id,
            question_id="question-unavailable",
            question_text_hash=uuid.uuid4().hex * 2,
            collection_contract_version="1",
            parser_version="parser-v1",
            normalizer_version="normalizer-v1",
            personalization_policy="none",
            location_snapshot={"name": "Reno, Nevada"},
            language_code="en",
            device="desktop",
            mention_state="unavailable",
            recommendation_state="unavailable",
            citation_state="unavailable",
            link_state="unavailable",
            cited_sources=[],
            competitor_entities=[],
            limitations=["The check did not return measurable evidence."],
            raw_response_hash=uuid.uuid4().hex * 2,
            evidence_hash=uuid.uuid4().hex * 2,
            observed_at=now,
        )
    )
    db_session.commit()

    summary = ai_visibility_service.get_summary(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    assert summary["truth"]["state"] == "unavailable"
    assert summary["truth"]["label"] == "The saved check could not measure visibility"
    assert "not counted as a measured result" in summary["truth"]["detail"]
    assert summary["summary"]["checked"] == 0
    assert summary["summary"]["sample_size"] == 0
    assert summary["summary"]["unavailable"] == 1
    assert all(
        coverage["measured"] == 0 and coverage["unavailable"] == 1
        for coverage in summary["summary"]["coverage"].values()
    )
    assert summary["history"]["total_runs"] == 1
    assert summary["history"]["items"] == [
        {
            "id": run.id,
            "status": "partial",
            "comparison_version": "comparison-v1",
            "requested_at": run.requested_at,
            "completed_at": run.completed_at,
        }
    ]
    assert summary["history"]["status"] == "unavailable"
    assert summary["competitors"]["status"] == "unavailable"

    run.collected_observation_count = 2
    db_session.add(
        AISearchObservation(
            tenant_id=campaign.tenant_id,
            organization_id=str(campaign.organization_id),
            campaign_id=campaign.id,
            business_location_id=str(campaign.business_location_id),
            run_id=run.id,
            question_set_id=question_set["id"],
            engine_registry_id=engine.id,
            provider_contract_id=contract.id,
            question_id="question-mixed",
            question_text_hash=uuid.uuid4().hex * 2,
            collection_contract_version="1",
            parser_version="parser-v1",
            normalizer_version="normalizer-v1",
            personalization_policy="none",
            location_snapshot={"name": "Reno, Nevada"},
            language_code="en",
            device="desktop",
            mention_state="observed",
            recommendation_state="not_observed",
            citation_state="unavailable",
            link_state="not_measured",
            cited_sources=[],
            competitor_entities=[],
            limitations=["Citation evidence was unavailable."],
            raw_response_hash=uuid.uuid4().hex * 2,
            evidence_hash=uuid.uuid4().hex * 2,
            observed_at=now + timedelta(seconds=1),
        )
    )
    db_session.commit()
    mixed = ai_visibility_service.get_summary(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    assert mixed["truth"]["state"] == "partial"
    assert "Unavailable results are not counted as measured" in mixed["truth"][
        "detail"
    ]
    assert mixed["summary"]["checked"] == 1
    assert mixed["summary"]["sample_size"] == 1
    assert mixed["summary"]["unavailable"] == 1
    assert mixed["summary"]["coverage"]["cited"] == {
        "observed": 0,
        "measured": 0,
        "not_measured": 0,
        "unavailable": 2,
    }
    assert mixed["history"]["status"] == "partial"
    assert mixed["competitors"]["status"] == "partial"


@pytest.mark.parametrize(
    ("customer_visible", "automatic_activation_allowed"),
    ((True, False), (False, True)),
)
def test_engine_visibility_and_automatic_activation_are_database_disabled(
    db_session,
    customer_visible: bool,
    automatic_activation_allowed: bool,
) -> None:
    db_session.add(
        AISearchEngineRegistry(
            engine_code=f"blocked_{uuid.uuid4().hex[:8]}",
            public_name="Blocked Engine",
            registry_version="1",
            collection_method="fixture",
            status="active",
            customer_visible=customer_visible,
            automatic_activation_allowed=automatic_activation_allowed,
            evidence_qa_passed=True,
            cost_qa_passed=True,
            comparison_qa_passed=True,
            supported_geographies=[],
            supported_languages=[],
            supported_devices=[],
            supported_personalization_policies=[],
            supported_evidence_facts=[],
            limitations=[],
            content_hash=uuid.uuid4().hex * 2,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize(
    ("status_value", "production_qa", "pricing_qa", "automatic_activation"),
    (
        ("approved", False, False, False),
        ("candidate", True, False, False),
        ("candidate", False, True, False),
        ("candidate", False, False, True),
    ),
)
def test_provider_contract_registry_is_candidate_only_and_cannot_activate(
    db_session,
    status_value: str,
    production_qa: bool,
    pricing_qa: bool,
    automatic_activation: bool,
) -> None:
    db_session.add(
        AISearchProviderContractRegistry(
            provider_key=f"blocked-{uuid.uuid4().hex[:8]}",
            contract_code="blocked",
            contract_version="1",
            collection_mode="fixture",
            request_schema_version="1",
            response_schema_version="1",
            parser_version="1",
            normalizer_version="1",
            engine_mappings=[],
            required_inputs=[],
            guaranteed_evidence_facts=[],
            optional_evidence_facts=[],
            unsupported_evidence_facts=[],
            billable_unit="fixture",
            status=status_value,
            production_qa_passed=production_qa,
            pricing_qa_passed=pricing_qa,
            automatic_activation_allowed=automatic_activation,
            content_hash=uuid.uuid4().hex * 2,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_ai_visibility_service_has_no_explainer_or_chat_runtime_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "ai_visibility_service.py"
    ).read_text(encoding="utf-8").casefold()
    forbidden = ["mistral", "governed_ai", "llm_explainer"]
    assert all(item not in source for item in forbidden)


def test_short_region_code_is_not_mistaken_for_city_name_text() -> None:
    assert ai_visibility_service._area_label("Berlin", "IN") == "Berlin, IN"
    assert ai_visibility_service._area_label("Reno, Nevada", "Nevada") == "Reno, Nevada"


def test_comparison_readiness_requires_identical_complete_frozen_scope() -> None:
    baseline = {
        "status": "complete",
        "requested_observation_count": 2,
        "collected_observation_count": 2,
        "comparison_version": "comparison-v1",
        "comparison_scope_hash": "a" * 64,
        "engine_registry_id": "engine-v1",
        "provider_contract_id": "contract-v1",
        "question_set_id": "questions-v1",
        "collection_contract_version": "contract-v1",
        "parser_version": "parser-v1",
        "normalizer_version": "normalizer-v1",
        "personalization_policy": "no_personalization",
        "language_code": "en",
        "device": "unspecified",
    }
    first = SimpleNamespace(**baseline)
    second = SimpleNamespace(**baseline)
    assert ai_visibility_service._comparison_ready([first, second]) is True

    changed_scope = SimpleNamespace(**{**baseline, "comparison_scope_hash": "b" * 64})
    assert ai_visibility_service._comparison_ready([first, changed_scope]) is False
    partial = SimpleNamespace(**{**baseline, "status": "partial"})
    assert ai_visibility_service._comparison_ready([first, partial]) is False


def test_latest_saved_run_per_engine_does_not_double_historical_counts() -> None:
    now = datetime.now(UTC)
    base = {
        "question_set_id": "questions-current",
        "engine_registry_id": "engine-a",
        "status": "complete",
        "requested_observation_count": 1,
        "collected_observation_count": 1,
        "completed_at": now,
        "requested_at": now,
    }
    older = SimpleNamespace(
        **{
            **base,
            "id": "run-old",
            "completed_at": now - timedelta(days=1),
            "requested_at": now - timedelta(days=1),
        }
    )
    newer = SimpleNamespace(**{**base, "id": "run-new"})
    selected = set(
        ai_visibility_service._latest_evidence_run_ids(
            [older, newer],
            current_question_set_id="questions-current",
        )
    )
    assert selected == {"run-new"}

    observations = [
        SimpleNamespace(
            run_id=run_id,
            mention_state="observed",
            recommendation_state="not_measured",
            citation_state="not_measured",
            link_state="not_measured",
        )
        for run_id in ("run-old", "run-new")
    ]
    evidence = ai_visibility_service._evidence_summary(
        [row for row in observations if row.run_id in selected]
    )
    assert evidence["checked"] == 1
    assert evidence["mentioned"] == 1


def test_scoped_foreign_keys_reject_cross_tenant_question_set_and_run_artifacts() -> None:
    metadata = MetaData()
    Table("tenants", metadata, Column("id", String(36), primary_key=True))
    Table("organizations", metadata, Column("id", String(36), primary_key=True))
    Table(
        "campaigns",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("tenant_id", String(36), nullable=False),
        Column("organization_id", String(36), nullable=False),
        Column("business_location_id", String(36), nullable=False),
        UniqueConstraint(
            "id", "tenant_id", "organization_id", "business_location_id"
        ),
    )
    Table(
        "business_locations",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), nullable=False),
        UniqueConstraint("id", "organization_id"),
    )
    Table(
        "users",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("tenant_id", String(36), nullable=False),
        UniqueConstraint("id", "tenant_id"),
    )
    Table("provider_price_cards", metadata, Column("id", String(36), primary_key=True))
    Table("cost_ledger_entries", metadata, Column("id", String(36), primary_key=True))
    for model in (
        AISearchEngineRegistry,
        AISearchProviderContractRegistry,
        AISearchQuestionSet,
        AISearchCollectionRun,
        AISearchObservation,
    ):
        model.__table__.to_metadata(metadata)

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    metadata.create_all(engine)
    now = datetime.now(UTC)
    tables = metadata.tables
    engine_values = {
        "id": "engine-a",
        "engine_code": "fixture-a",
        "public_name": "Internal fixture",
        "registry_version": "1",
        "collection_method": "fixture",
        "status": "candidate",
        "customer_visible": False,
        "automatic_activation_allowed": False,
        "evidence_qa_passed": False,
        "cost_qa_passed": False,
        "comparison_qa_passed": False,
        "supported_geographies": [],
        "supported_languages": [],
        "supported_devices": [],
        "supported_personalization_policies": [],
        "supported_evidence_facts": [],
        "limitations": [],
        "content_hash": "a" * 64,
        "created_at": now,
    }
    contract_values = {
        "id": "contract-a",
        "provider_key": "private-fixture",
        "contract_code": "fixture",
        "contract_version": "1",
        "collection_mode": "fixture",
        "request_schema_version": "1",
        "response_schema_version": "1",
        "parser_version": "parser-v1",
        "normalizer_version": "normalizer-v1",
        "engine_mappings": [],
        "required_inputs": [],
        "guaranteed_evidence_facts": [],
        "optional_evidence_facts": [],
        "unsupported_evidence_facts": [],
        "billable_unit": "fixture",
        "status": "candidate",
        "production_qa_passed": False,
        "pricing_qa_passed": False,
        "automatic_activation_allowed": False,
        "content_hash": "b" * 64,
        "created_at": now,
    }
    question_set_values = {
        "id": "questions-a",
        "tenant_id": "tenant-a",
        "organization_id": "org-a",
        "campaign_id": "campaign-a",
        "business_location_id": "location-a",
        "version": 1,
        "generator_version": "fixture-v1",
        "questions": [],
        "context_snapshot": {},
        "context_hash": "c" * 64,
        "question_set_hash": "d" * 64,
        "status": "frozen",
        "created_by_user_id": "user-a",
        "created_at": now,
    }
    run_values = {
        "id": "run-a",
        "tenant_id": "tenant-a",
        "organization_id": "org-a",
        "campaign_id": "campaign-a",
        "business_location_id": "location-a",
        "question_set_id": "questions-a",
        "engine_registry_id": "engine-a",
        "provider_contract_id": "contract-a",
        "comparison_version": "comparison-v1",
        "collection_contract_version": "1",
        "parser_version": "parser-v1",
        "normalizer_version": "normalizer-v1",
        "personalization_policy": "none",
        "comparison_scope_hash": "e" * 64,
        "location_snapshot": {},
        "language_code": "en",
        "device": "desktop",
        "status": "partial",
        "request_hash": "f" * 64,
        "idempotency_key": "run-a",
        "requested_observation_count": 1,
        "collected_observation_count": 1,
        "coverage_summary": {},
        "requested_at": now,
        "created_at": now,
        "updated_at": now,
    }
    with engine.begin() as connection:
        connection.execute(
            insert(tables["tenants"]), [{"id": "tenant-a"}, {"id": "tenant-b"}]
        )
        connection.execute(
            insert(tables["organizations"]), [{"id": "org-a"}, {"id": "org-b"}]
        )
        connection.execute(
            insert(tables["business_locations"]),
            [
                {"id": "location-a", "organization_id": "org-a"},
                {"id": "location-b", "organization_id": "org-b"},
            ],
        )
        connection.execute(
            insert(tables["campaigns"]),
            [
                {
                    "id": "campaign-a",
                    "tenant_id": "tenant-a",
                    "organization_id": "org-a",
                    "business_location_id": "location-a",
                },
                {
                    "id": "campaign-b",
                    "tenant_id": "tenant-b",
                    "organization_id": "org-b",
                    "business_location_id": "location-b",
                },
            ],
        )
        connection.execute(
            insert(tables["users"]),
            [
                {"id": "user-a", "tenant_id": "tenant-a"},
                {"id": "user-b", "tenant_id": "tenant-b"},
            ],
        )
        connection.execute(insert(tables["ai_search_engine_registry"]), engine_values)
        connection.execute(
            insert(tables["ai_search_provider_contract_registry"]), contract_values
        )
        connection.execute(
            insert(tables["ai_search_question_sets"]), question_set_values
        )
        question_set_b = {
            **question_set_values,
            "id": "questions-b",
            "tenant_id": "tenant-b",
            "organization_id": "org-b",
            "campaign_id": "campaign-b",
            "business_location_id": "location-b",
            "created_by_user_id": "user-b",
            "context_hash": "7" * 64,
            "question_set_hash": "8" * 64,
        }
        connection.execute(
            insert(tables["ai_search_question_sets"]), question_set_b
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(tables["ai_search_question_sets"]),
                {
                    **question_set_values,
                    "id": "questions-cross-campaign",
                    "campaign_id": "campaign-b",
                    "version": 2,
                    "question_set_hash": "5" * 64,
                },
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(tables["ai_search_question_sets"]),
                {
                    **question_set_values,
                    "id": "questions-cross-creator",
                    "created_by_user_id": "user-b",
                    "version": 3,
                    "question_set_hash": "6" * 64,
                },
            )

        cross_tenant_run = {
            **run_values,
            "id": "run-cross-tenant",
            "tenant_id": "tenant-b",
            "organization_id": "org-b",
            "campaign_id": "campaign-b",
            "business_location_id": "location-b",
            "idempotency_key": "run-cross-tenant",
        }
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(tables["ai_search_collection_runs"]), cross_tenant_run
            )

        connection.execute(insert(tables["ai_search_collection_runs"]), run_values)
        run_b = {
            **run_values,
            "id": "run-b",
            "tenant_id": "tenant-b",
            "organization_id": "org-b",
            "campaign_id": "campaign-b",
            "business_location_id": "location-b",
            "question_set_id": "questions-b",
            "idempotency_key": "run-b",
        }
        connection.execute(insert(tables["ai_search_collection_runs"]), run_b)
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(tables["ai_search_collection_runs"]),
                {
                    **run_values,
                    "id": "run-cross-prior",
                    "idempotency_key": "run-cross-prior",
                    "prior_comparable_run_id": "run-b",
                },
            )
        connection.execute(
            insert(tables["ai_search_engine_registry"]),
            {
                **engine_values,
                "id": "engine-b",
                "engine_code": "fixture-b",
                "content_hash": "1" * 64,
            },
        )
        mismatched_observation = {
            "id": "observation-mismatch",
            "tenant_id": "tenant-a",
            "organization_id": "org-a",
            "campaign_id": "campaign-a",
            "business_location_id": "location-a",
            "run_id": "run-a",
            "question_set_id": "questions-a",
            "engine_registry_id": "engine-b",
            "provider_contract_id": "contract-a",
            "question_id": "question-a",
            "question_text_hash": "2" * 64,
            "collection_contract_version": "1",
            "parser_version": "parser-v1",
            "normalizer_version": "normalizer-v1",
            "personalization_policy": "none",
            "location_snapshot": {},
            "language_code": "en",
            "device": "desktop",
            "mention_state": "not_observed",
            "recommendation_state": "not_measured",
            "citation_state": "not_measured",
            "link_state": "not_measured",
            "cited_sources": [],
            "competitor_entities": [],
            "limitations": [],
            "raw_response_hash": "3" * 64,
            "evidence_hash": "4" * 64,
            "observed_at": now,
            "created_at": now,
        }
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(tables["ai_search_observations"]), mismatched_observation
            )
    engine.dispose()
