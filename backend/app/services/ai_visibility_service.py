from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ai_visibility import (
    AISearchCollectionRun,
    AISearchEngineRegistry,
    AISearchObservation,
    AISearchProviderContractRegistry,
    AISearchQuestionSet,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.services.business_service_area_service import confirmed_areas_for_campaign
from app.services.business_service_service import confirmed_services_for_campaign


QUESTION_GENERATOR_VERSION = "ai-search-questions-v1"
MAX_QUESTIONS_PER_SET = 50
_COLLECTION_LIMITATION = (
    "AI search evidence collection is not available until an engine passes production checks."
)
_VOLATILITY_LIMITATION = (
    "AI search answers can vary by date, location, language, and the engine version used."
)


def list_public_engines(db: Session) -> dict[str, Any]:
    rows = (
        db.query(AISearchEngineRegistry)
        .filter(
            AISearchEngineRegistry.status == "active",
            AISearchEngineRegistry.customer_visible.is_(True),
            AISearchEngineRegistry.evidence_qa_passed.is_(True),
            AISearchEngineRegistry.cost_qa_passed.is_(True),
            AISearchEngineRegistry.comparison_qa_passed.is_(True),
        )
        .order_by(
            AISearchEngineRegistry.public_name.asc(),
            AISearchEngineRegistry.registry_version.asc(),
        )
        .all()
    )
    items = [_serialize_engine(row) for row in rows]
    return {
        "truth_state": "not_measured" if items else "unavailable",
        "items": items,
        "approved_count": len(items),
        "unavailable_reason": None if items else _COLLECTION_LIMITATION,
        "limitations": [_VOLATILITY_LIMITATION],
    }


def preview_collection(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    """Describe every fail-closed gate without creating work or spending credits."""

    campaign = _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    context = _confirmed_context(db, campaign=campaign)
    missing = _missing_context(context)
    question_set = _latest_question_set(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
    )
    context_ready = not missing
    question_set_current = bool(
        context_ready
        and question_set is not None
        and _is_current_question_set(question_set, context)
    )
    approved_engines = list_public_engines(db)
    approved_contract_exists = (
        db.query(AISearchProviderContractRegistry.id)
        .filter(
            AISearchProviderContractRegistry.status == "approved",
            AISearchProviderContractRegistry.production_qa_passed.is_(True),
            AISearchProviderContractRegistry.pricing_qa_passed.is_(True),
            AISearchProviderContractRegistry.automatic_activation_allowed.is_(True),
        )
        .first()
        is not None
    )

    blockers: list[dict[str, str]] = []
    if not context_ready:
        blockers.append(
            {
                "code": "business_details_incomplete",
                "message": "Confirm at least one service and one service area first.",
                "href": "/keyword-research",
            }
        )
    elif question_set is None:
        blockers.append(
            {
                "code": "questions_not_saved",
                "message": "Save the customer questions that future checks will use.",
                "href": "/ai-visibility",
            }
        )
    elif not question_set_current:
        blockers.append(
            {
                "code": "questions_outdated",
                "message": "Update the saved questions to match current business details.",
                "href": "/ai-visibility",
            }
        )
    if int(approved_engines["approved_count"]) == 0:
        blockers.append(
            {
                "code": "engine_checks_incomplete",
                "message": "AI search checks are still completing production validation.",
                "href": "/ai-visibility",
            }
        )
    if not approved_contract_exists:
        blockers.append(
            {
                "code": "evidence_collection_not_ready",
                "message": "Evidence collection is not approved for production yet.",
                "href": "/ai-visibility",
            }
        )
    blockers.extend(
        [
            {
                "code": "cost_rules_not_ready",
                "message": "Verified cost rules have not been configured for these checks.",
                "href": "/settings",
            },
            {
                "code": "usage_allowance_not_ready",
                "message": "A plan allowance has not been configured for these checks.",
                "href": "/settings",
            },
        ]
    )
    return {
        "campaign_id": campaign.id,
        "business_location_id": campaign.business_location_id,
        "state": "unavailable",
        "ready": False,
        "question_set_id": question_set.id if question_set is not None else None,
        "question_count": len(list(question_set.questions or [])) if question_set else 0,
        "estimated_credits": None,
        "checks": {
            "business_context_ready": context_ready,
            "question_set_current": question_set_current,
            "approved_engine_available": int(approved_engines["approved_count"]) > 0,
            "evidence_collection_ready": approved_contract_exists,
            "cost_rules_configured": False,
            "usage_allowance_configured": False,
        },
        "blockers": blockers,
        "side_effects": {
            "external_request_sent": False,
            "reservation_created": False,
            "charge_created": False,
            "run_created": False,
        },
        "limitations": [_COLLECTION_LIMITATION, _VOLATILITY_LIMITATION],
    }


def create_question_set(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    context = _confirmed_context(db, campaign=campaign)
    missing = _missing_context(context)
    if missing:
        labels = {
            "confirmed_services": "at least one confirmed service",
            "confirmed_service_areas": "at least one confirmed service area",
            "business_location": "a business location",
        }
        requirements = ", ".join(labels[item] for item in missing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Add {requirements} before saving AI search questions.",
                "reason_code": "ai_search_context_incomplete",
                "missing": missing,
            },
        )

    questions = _build_questions(context)
    context_snapshot = _context_snapshot(context, question_count=len(questions))
    context_hash = _hash(context_snapshot)
    question_set_hash = _hash(
        {
            "generator_version": QUESTION_GENERATOR_VERSION,
            "context_hash": context_hash,
            "questions": questions,
        }
    )
    existing = (
        db.query(AISearchQuestionSet)
        .filter(
            AISearchQuestionSet.tenant_id == tenant_id,
            AISearchQuestionSet.organization_id == organization_id,
            AISearchQuestionSet.campaign_id == campaign.id,
            AISearchQuestionSet.question_set_hash == question_set_hash,
            AISearchQuestionSet.generator_version == QUESTION_GENERATOR_VERSION,
        )
        .first()
    )
    if existing is not None:
        return _question_set_envelope(existing, created=False, current_context=True)

    latest = _latest_question_set(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
    )
    row = AISearchQuestionSet(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=str(campaign.business_location_id),
        version=(latest.version + 1) if latest is not None else 1,
        generator_version=QUESTION_GENERATOR_VERSION,
        questions=questions,
        context_snapshot=context_snapshot,
        context_hash=context_hash,
        question_set_hash=question_set_hash,
        status="frozen",
        created_by_user_id=actor_user_id,
        created_at=now or datetime.now(UTC),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(AISearchQuestionSet)
            .filter(
                AISearchQuestionSet.tenant_id == tenant_id,
                AISearchQuestionSet.organization_id == organization_id,
                AISearchQuestionSet.campaign_id == campaign.id,
                AISearchQuestionSet.question_set_hash == question_set_hash,
                AISearchQuestionSet.generator_version == QUESTION_GENERATOR_VERSION,
            )
            .first()
        )
        if existing is None:
            raise
        return _question_set_envelope(existing, created=False, current_context=True)
    db.refresh(row)
    return _question_set_envelope(row, created=True, current_context=True)


def get_current_question_set(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    context = _confirmed_context(db, campaign=campaign)
    missing = _missing_context(context)
    context_ready = not missing
    row = _latest_question_set(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    if row is None:
        return {
            "created": False,
            "question_set": None,
            "current_context": False,
            "collection_state": "unavailable",
            "next_action": _next_action(
                question_set=None,
                context_ready=context_ready,
            ),
            "limitations": [_COLLECTION_LIMITATION, _VOLATILITY_LIMITATION],
        }
    current_context = context_ready and _is_current_question_set(row, context)
    return _question_set_envelope(
        row,
        created=False,
        current_context=current_context,
    )


def get_summary(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    context = _confirmed_context(db, campaign=campaign)
    missing = _missing_context(context)
    current = _latest_question_set(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
    )
    engines = list_public_engines(db)
    context_ready = not missing
    current_context = (
        context_ready
        and current is not None
        and _is_current_question_set(current, context)
    )
    all_runs = (
        db.query(AISearchCollectionRun)
        .join(
            AISearchEngineRegistry,
            AISearchEngineRegistry.id == AISearchCollectionRun.engine_registry_id,
        )
        .join(
            AISearchProviderContractRegistry,
            AISearchProviderContractRegistry.id
            == AISearchCollectionRun.provider_contract_id,
        )
        .filter(
            AISearchCollectionRun.tenant_id == tenant_id,
            AISearchCollectionRun.organization_id == organization_id,
            AISearchCollectionRun.campaign_id == campaign.id,
            AISearchEngineRegistry.status == "active",
            AISearchEngineRegistry.customer_visible.is_(True),
            AISearchEngineRegistry.evidence_qa_passed.is_(True),
            AISearchEngineRegistry.cost_qa_passed.is_(True),
            AISearchEngineRegistry.comparison_qa_passed.is_(True),
            AISearchProviderContractRegistry.status == "approved",
            AISearchProviderContractRegistry.production_qa_passed.is_(True),
            AISearchProviderContractRegistry.pricing_qa_passed.is_(True),
            AISearchProviderContractRegistry.automatic_activation_allowed.is_(True),
        )
        .order_by(AISearchCollectionRun.requested_at.desc())
        .all()
    )
    runs = all_runs[:12]
    evidence_run_ids = _latest_evidence_run_ids(
        all_runs,
        current_question_set_id=current.id if current_context and current is not None else None,
    )
    observations = []
    if evidence_run_ids:
        observations = (
            db.query(AISearchObservation)
            .filter(
                AISearchObservation.tenant_id == tenant_id,
                AISearchObservation.organization_id == organization_id,
                AISearchObservation.campaign_id == campaign.id,
                AISearchObservation.question_set_id == current.id,
                AISearchObservation.run_id.in_(evidence_run_ids),
            )
            .order_by(AISearchObservation.observed_at.desc())
            .all()
        )
    evidence = _evidence_summary(observations)
    has_evidence = evidence["checked"] > 0
    has_unavailable_evidence = any(
        int(fact["unavailable"]) > 0 for fact in evidence["coverage"].values()
    )
    has_partial_evidence = has_evidence and has_unavailable_evidence
    if has_partial_evidence:
        truth_state = "partial"
        truth_label = "Some visibility evidence could not be measured"
        truth_detail = (
            "The saved check measured some facts, but at least one result was unavailable. "
            "Unavailable results are not counted as measured."
        )
    elif has_evidence:
        truth_state = "observed"
        truth_label = "Saved AI search evidence"
        truth_detail = "These counts come from saved question-level observations."
    elif has_unavailable_evidence:
        truth_state = "unavailable"
        truth_label = "The saved check could not measure visibility"
        truth_detail = (
            "A check was saved, but it could not confirm mentions, recommendations, "
            "citations, or links. It is not counted as a measured result."
        )
    elif not context_ready:
        truth_state = "unavailable"
        truth_label = "Business details are not ready"
        truth_detail = "Confirm services and service areas before saving questions."
    elif engines["approved_count"] == 0:
        truth_state = "unavailable"
        truth_label = "AI search checks are not available yet"
        truth_detail = _COLLECTION_LIMITATION
    else:
        truth_state = "not_measured"
        truth_label = "No AI search checks have been saved"
        truth_detail = "Zero means no observations have been collected, not no visibility."

    last_observed_at = observations[0].observed_at if observations else None
    limitations = [_VOLATILITY_LIMITATION]
    if engines["approved_count"] == 0:
        limitations.insert(0, _COLLECTION_LIMITATION)
    if current is not None and bool((current.context_snapshot or {}).get("truncated")):
        limitations.append(
            f"This frozen set contains the first {MAX_QUESTIONS_PER_SET} deterministic questions."
        )
    next_action = _next_action(
        question_set=current,
        context_ready=context_ready,
        approved_engine_count=int(engines["approved_count"]),
        current_context=current_context,
    )
    competitor_items = _competitor_items(observations)
    return {
        "campaign_id": campaign.id,
        "business_location_id": campaign.business_location_id,
        "truth": {
            "state": truth_state,
            "label": truth_label,
            "detail": truth_detail,
            "last_observed_at": last_observed_at,
            "comparison_ready": _comparison_ready(runs),
        },
        "setup": {
            "ready": context_ready,
            "confirmed_services": len(context["services"]),
            "confirmed_service_areas": len(context["areas"]),
            "missing": missing,
            "question_set_ready": bool(current is not None and current_context),
        },
        "summary": evidence,
        "engines": {
            "approved_count": engines["approved_count"],
            "items": engines["items"],
            "unavailable_reason": engines["unavailable_reason"],
        },
        "questions": {
            "current": _serialize_question_set(current) if current is not None else None,
            "count": len(list(current.questions or [])) if current is not None else 0,
            "frozen": current is not None,
            "current_context": current_context,
            "generator_version": current.generator_version if current is not None else None,
        },
        "history": {
            "items": [_serialize_run(row) for row in runs],
            "total_runs": len(all_runs),
            "comparable_runs": sum(_is_complete_run(row) for row in all_runs),
            "status": (
                "partial"
                if has_partial_evidence
                else "unavailable"
                if has_unavailable_evidence
                else _history_state(runs)
            ),
        },
        "competitors": {
            "items": competitor_items,
            "mentioned_count": len(competitor_items),
            "status": (
                "partial"
                if has_partial_evidence
                else "observed"
                if has_evidence
                else "unavailable"
                if has_unavailable_evidence
                else "not_measured"
            ),
        },
        "next_action": next_action,
        "limitations": limitations,
    }


def _confirmed_context(db: Session, *, campaign: Campaign) -> dict[str, Any]:
    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == campaign.business_location_id,
            BusinessLocation.organization_id == campaign.organization_id,
        )
        .first()
        if campaign.business_location_id
        else None
    )
    services = confirmed_services_for_campaign(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    included_areas, _excluded_areas = confirmed_areas_for_campaign(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    services = [
        row
        for row in services
        if row.organization_id == campaign.organization_id and row.status == "confirmed"
    ]
    areas = [
        row
        for row in included_areas
        if row.organization_id == campaign.organization_id
        and row.business_location_id == campaign.business_location_id
        and row.status == "confirmed"
        and row.relationship == "included"
        and row.area_type in {"city", "county", "postal_code"}
    ]
    services.sort(key=lambda row: (row.normalized_name, row.id))
    areas.sort(key=lambda row: (row.normalized_name, row.id))
    competitors = (
        db.query(Competitor)
        .filter(
            Competitor.tenant_id == campaign.tenant_id,
            Competitor.campaign_id == campaign.id,
            Competitor.review_status == "confirmed",
        )
        .order_by(Competitor.domain.asc(), Competitor.id.asc())
        .all()
    )
    return {
        "campaign": campaign,
        "location": location,
        "services": services,
        "areas": areas,
        "competitors": competitors,
    }


def _missing_context(context: dict[str, Any]) -> list[str]:
    campaign: Campaign = context["campaign"]
    missing: list[str] = []
    if not campaign.business_location_id:
        missing.append("business_location")
    if not context["services"]:
        missing.append("confirmed_services")
    if not context["areas"]:
        missing.append("confirmed_service_areas")
    return missing


def _build_questions(context: dict[str, Any]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for service in context["services"]:
        for area in context["areas"]:
            area_label = _area_label(area.name, area.region)
            text = f"Which businesses provide {service.name} in {area_label}?"
            identity = {
                "generator_version": QUESTION_GENERATOR_VERSION,
                "service_id": service.id,
                "service_area_id": area.id,
                "text": text,
            }
            questions.append(
                {
                    "id": f"question_{_hash(identity)[:24]}",
                    "text": text,
                    "service_id": service.id,
                    "service_name": service.name,
                    "service_area_id": area.id,
                    "service_area_name": area_label,
                }
            )
            if len(questions) >= MAX_QUESTIONS_PER_SET:
                return questions
    return questions


def _context_snapshot(
    context: dict[str, Any],
    *,
    question_count: int,
) -> dict[str, Any]:
    campaign: Campaign = context["campaign"]
    total_pairs = len(context["services"]) * len(context["areas"])
    location: BusinessLocation | None = context["location"]
    target_entity = {
        "business_name": location.name if location is not None else campaign.name,
        "campaign_name": campaign.name,
        "location_name": location.name if location is not None else None,
        "domains": sorted(
            {
                domain.strip().casefold()
                for domain in (
                    campaign.domain,
                    location.domain if location is not None else None,
                )
                if domain and domain.strip()
            }
        ),
    }
    competitor_set = [
        {
            "id": row.id,
            "name": row.label or row.domain,
            "domain": row.domain.strip().casefold(),
            "review_status": row.review_status,
        }
        for row in context["competitors"]
    ]
    return {
        "campaign_id": campaign.id,
        "business_location_id": campaign.business_location_id,
        "target_entity": target_entity,
        "target_entity_hash": _hash(target_entity),
        "competitors": competitor_set,
        "competitor_set_hash": _hash(competitor_set),
        "services": [
            {
                "id": row.id,
                "name": row.name,
                "normalized_name": row.normalized_name,
                "status": row.status,
            }
            for row in context["services"]
        ],
        "service_areas": [
            {
                "id": row.id,
                "name": row.name,
                "normalized_name": row.normalized_name,
                "area_type": row.area_type,
                "region": row.region,
                "country_code": row.country_code,
                "relationship": row.relationship,
                "status": row.status,
            }
            for row in context["areas"]
        ],
        "total_pairs": total_pairs,
        "question_count": question_count,
        "truncated": question_count < total_pairs,
    }


def _evidence_summary(observations: list[AISearchObservation]) -> dict[str, Any]:
    coverage = {
        "mentioned": _fact_coverage(observations, "mention_state"),
        "recommended": _fact_coverage(observations, "recommendation_state"),
        "cited": _fact_coverage(observations, "citation_state"),
        "linked": _fact_coverage(observations, "link_state"),
    }
    measured_states = {"observed", "not_observed"}
    checked = sum(
        any(
            str(getattr(row, field_name)) in measured_states
            for field_name in (
                "mention_state",
                "recommendation_state",
                "citation_state",
                "link_state",
            )
        )
        for row in observations
    )
    unavailable = sum(
        not any(
            str(getattr(row, field_name)) in measured_states
            for field_name in (
                "mention_state",
                "recommendation_state",
                "citation_state",
                "link_state",
            )
        )
        and any(
            str(getattr(row, field_name)) == "unavailable"
            for field_name in (
                "mention_state",
                "recommendation_state",
                "citation_state",
                "link_state",
            )
        )
        for row in observations
    )
    return {
        "checked": checked,
        "mentioned": coverage["mentioned"]["observed"],
        "recommended": coverage["recommended"]["observed"],
        "cited": coverage["cited"]["observed"],
        "linked": coverage["linked"]["observed"],
        "unavailable": unavailable,
        "sample_size": checked,
        "coverage": coverage,
    }


def _fact_coverage(
    observations: list[AISearchObservation],
    field_name: str,
) -> dict[str, int]:
    states = [str(getattr(row, field_name)) for row in observations]
    return {
        "observed": states.count("observed"),
        "measured": states.count("observed") + states.count("not_observed"),
        "not_measured": states.count("not_measured"),
        "unavailable": states.count("unavailable"),
    }


def _competitor_items(observations: list[AISearchObservation]) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for row in observations:
        for raw in row.competitor_entities or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            key = name.casefold()
            item = items.setdefault(
                key,
                {"name": name, "domain": raw.get("domain"), "mention_count": 0},
            )
            item["mention_count"] += 1
    return sorted(items.values(), key=lambda item: (-item["mention_count"], item["name"]))


def _latest_evidence_run_ids(
    runs: list[AISearchCollectionRun],
    *,
    current_question_set_id: str | None,
) -> list[str]:
    """Choose one saved evidence snapshot per engine without mixing history."""

    if current_question_set_id is None:
        return []
    latest_by_engine: dict[str, AISearchCollectionRun] = {}
    for row in runs:
        if (
            row.question_set_id != current_question_set_id
            or row.status not in {"complete", "partial"}
            or row.collected_observation_count <= 0
        ):
            continue
        current = latest_by_engine.get(row.engine_registry_id)
        row_time = row.completed_at or row.requested_at
        current_time = (current.completed_at or current.requested_at) if current else None
        if current is None or row_time > current_time or (
            row_time == current_time and row.id > current.id
        ):
            latest_by_engine[row.engine_registry_id] = row
    return sorted(row.id for row in latest_by_engine.values())


def _is_complete_run(row: AISearchCollectionRun) -> bool:
    return bool(
        row.status == "complete"
        and row.requested_observation_count > 0
        and row.collected_observation_count == row.requested_observation_count
    )


def _comparison_ready(runs: list[AISearchCollectionRun]) -> bool:
    comparable = [row for row in runs if _is_complete_run(row)]
    if len(comparable) < 2:
        return False
    scopes = {
        (
            row.comparison_version,
            row.comparison_scope_hash,
            row.engine_registry_id,
            row.provider_contract_id,
            row.question_set_id,
            row.collection_contract_version,
            row.parser_version,
            row.normalizer_version,
            row.personalization_policy,
            row.language_code,
            row.device,
            row.requested_observation_count,
        )
        for row in comparable
    }
    return len(scopes) == 1


def _history_state(runs: list[AISearchCollectionRun]) -> str:
    if any(row.status in {"complete", "partial"} for row in runs):
        return "observed"
    if any(row.status in {"unavailable", "unsupported"} for row in runs):
        return "unavailable"
    return "not_measured"


def _question_set_envelope(
    row: AISearchQuestionSet,
    *,
    created: bool,
    current_context: bool,
) -> dict[str, Any]:
    return {
        "created": created,
        "question_set": _serialize_question_set(row),
        "current_context": current_context,
        "collection_state": "unavailable",
        "next_action": _next_action(
            question_set=row,
            context_ready=True,
            current_context=current_context,
        ),
        "limitations": [_COLLECTION_LIMITATION, _VOLATILITY_LIMITATION],
    }


def _serialize_question_set(row: AISearchQuestionSet) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "version": row.version,
        "generator_version": row.generator_version,
        "question_count": len(list(row.questions or [])),
        "questions": list(row.questions or []),
        "context_hash": row.context_hash,
        "question_set_hash": row.question_set_hash,
        "status": row.status,
        "created_at": row.created_at,
    }


def _serialize_engine(row: AISearchEngineRegistry) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.engine_code,
        "name": row.public_name,
        "version": row.registry_version,
        "availability": "available",
        "supported_geographies": [
            str(item) for item in (row.supported_geographies or [])
        ],
        "supported_languages": [str(item) for item in (row.supported_languages or [])],
        "supported_devices": [str(item) for item in (row.supported_devices or [])],
        "limitations": [str(item) for item in (row.limitations or [])],
    }


def _serialize_run(row: AISearchCollectionRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "comparison_version": row.comparison_version,
        "requested_at": row.requested_at,
        "completed_at": row.completed_at,
    }


def _next_action(
    *,
    question_set: AISearchQuestionSet | None,
    context_ready: bool,
    approved_engine_count: int = 0,
    current_context: bool = True,
) -> dict[str, str]:
    if not context_ready:
        return {
            "code": "complete_business_context",
            "label": "Confirm services and service areas",
            "detail": "Saved questions only use business details you have confirmed.",
            "href": "/keyword-research",
        }
    if question_set is None:
        return {
            "code": "save_questions",
            "label": "Save your customer questions",
            "detail": "Create a frozen list from your confirmed services and work areas.",
            "href": "/ai-visibility",
        }
    if not current_context:
        return {
            "code": "update_questions",
            "label": "Update customer questions",
            "detail": "Your confirmed services or work areas changed after this list was saved.",
            "href": "/ai-visibility",
        }
    if approved_engine_count == 0:
        return {
            "code": "collection_unavailable",
            "label": "Your questions are ready",
            "detail": "Checks will stay off until an engine passes production evidence checks.",
            "href": "/ai-visibility",
        }
    return {
        "code": "await_first_observation",
        "label": "Waiting for the first saved check",
        "detail": "No result is shown until question-level evidence has been saved.",
        "href": "/ai-visibility",
    }


def _current_context_hash(context: dict[str, Any]) -> str:
    questions = _build_questions(context)
    return _hash(_context_snapshot(context, question_count=len(questions)))


def _is_current_question_set(
    row: AISearchQuestionSet,
    context: dict[str, Any],
) -> bool:
    return (
        row.generator_version == QUESTION_GENERATOR_VERSION
        and row.context_hash == _current_context_hash(context)
    )


def _area_label(name: str, region: str | None) -> str:
    clean_region = str(region or "").strip()
    folded_name = name.strip().casefold()
    folded_region = clean_region.casefold()
    if (
        not clean_region
        or folded_name == folded_region
        or folded_name.endswith(f", {folded_region}")
        or folded_name.endswith(f" {folded_region}")
    ):
        return name
    return f"{name}, {clean_region}"


def _latest_question_set(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> AISearchQuestionSet | None:
    return (
        db.query(AISearchQuestionSet)
        .filter(
            AISearchQuestionSet.tenant_id == tenant_id,
            AISearchQuestionSet.organization_id == organization_id,
            AISearchQuestionSet.campaign_id == campaign_id,
        )
        .order_by(AISearchQuestionSet.version.desc(), AISearchQuestionSet.created_at.desc())
        .first()
    )


def _campaign_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def _hash(payload: Any) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
