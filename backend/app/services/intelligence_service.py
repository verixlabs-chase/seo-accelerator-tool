import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.events import emit_event
from app.intelligence.lexicon import get_active_lexicon
from app.intelligence.recommendation_execution_engine import schedule_execution
from app.models.action_plan import ActionPlanOccurrence, ActionPlanStep
from app.models.campaign import Campaign
from app.models.content import ContentAsset
from app.models.crawl import TechnicalIssue
from app.enums import StrategyRecommendationStatus
from app.utils.enum_guard import ensure_enum
from app.models.intelligence import AnomalyEvent, CampaignMilestone, IntelligenceScore, StrategyRecommendation
from app.models.local import LocalHealthSnapshot
from app.models.rank import Ranking
from app.services.intelligence_runtime_service import build_intelligence_engine_state

RECOMMENDATION_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"GENERATED"},
    "GENERATED": {"VALIDATED", "FAILED", "ARCHIVED"},
    "VALIDATED": {"APPROVED", "FAILED", "ARCHIVED"},
    "APPROVED": {"SCHEDULED", "ARCHIVED"},
    "SCHEDULED": {"EXECUTED", "FAILED", "ROLLED_BACK"},
    "EXECUTED": set(),
    "FAILED": set(),
    "ROLLED_BACK": set(),
    "ARCHIVED": set(),
}


def _recommendation_action_candidates(recommendation: StrategyRecommendation) -> list[str]:
    candidates: list[str] = []

    try:
        evidence = json.loads(recommendation.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}

    if isinstance(evidence, dict):
        for key in ("action_id", "recommended_action_id", "action"):
            value = evidence.get(key)
            if value:
                candidates.append(str(value))

        nested_evidence = evidence.get("evidence")
        if isinstance(nested_evidence, dict):
            for key in ("action_id", "recommended_action_id", "action"):
                value = nested_evidence.get(key)
                if value:
                    candidates.append(str(value))

        recommended_actions = evidence.get("recommended_actions")
        if isinstance(recommended_actions, list):
            candidates.extend(str(item) for item in recommended_actions if item)

    recommendation_type = str(recommendation.recommendation_type or "")
    if recommendation_type:
        candidates.append(recommendation_type)
        if "::" in recommendation_type:
            candidates.append(recommendation_type.rsplit("::", 1)[-1])

    return list(dict.fromkeys(candidates))


def build_recommendation_action_plans(
    db: Session,
    *,
    tenant_id: str,
    recommendations: list[StrategyRecommendation],
) -> dict[str, dict]:
    """Resolve stored recommendations to versioned, deterministic lexicon actions."""

    lexicon = get_active_lexicon(db, tenant_id=tenant_id)
    plans: dict[str, dict] = {}

    for recommendation in recommendations:
        action = next(
            (
                lexicon.action_index[candidate]
                for candidate in _recommendation_action_candidates(recommendation)
                if candidate in lexicon.action_index
            ),
            None,
        )
        if action is None:
            continue

        plans[recommendation.id] = {
            "action_id": action.action_id,
            "category": action.category,
            "display_name": action.display_name,
            "why_it_matters": action.why_it_matters,
            "steps": list(action.steps),
            "risk_tier": action.risk_tier,
            "effort": str(action.effort),
            "owner_role": action.owner_role,
            "dependencies": list(action.dependencies),
            "success_metric_ids": list(action.success_metric_ids),
            "observation_window_days": action.observation_window_days,
            "lexicon_id": lexicon.meta.lexicon_id,
            "lexicon_version": lexicon.meta.version,
        }

    return plans


_ACTIVE_ACTION_PLAN_STATUSES = {
    "ready",
    "in_progress",
    "blocked",
    "waiting_for_results",
    "snoozed",
}
_RESOLVED_STEP_STATUSES = {"done", "skipped"}


def _action_plan_cadence(
    plan: dict,
    *,
    completed_action_ids: set[str],
) -> str:
    dependencies = {str(item) for item in plan.get("dependencies", []) if item}
    if dependencies - completed_action_ids:
        return "later"
    if int(plan.get("risk_tier", 0) or 0) >= 3:
        return "daily"
    if str(plan.get("effort", "")) == "high" or int(
        plan.get("observation_window_days", 0) or 0
    ) >= 60:
        return "monthly"
    return "weekly"


def _action_plan_period_key(cadence: str, now: datetime) -> str:
    if cadence == "daily":
        return now.date().isoformat()
    if cadence == "weekly":
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if cadence == "monthly":
        return now.strftime("%Y-%m")
    return "once"


def _action_plan_due_at(cadence: str, now: datetime) -> datetime | None:
    if cadence == "daily":
        return now + timedelta(days=1)
    if cadence == "weekly":
        return now + timedelta(days=7)
    if cadence == "monthly":
        return now + timedelta(days=30)
    return None


def _action_plan_content_hash(plan: dict, cadence: str) -> str:
    payload = {
        "action_id": plan["action_id"],
        "cadence": cadence,
        "steps": list(plan.get("steps", [])),
        "dependencies": list(plan.get("dependencies", [])),
        "success_metric_ids": list(plan.get("success_metric_ids", [])),
        "observation_window_days": plan.get("observation_window_days"),
        "lexicon_id": plan.get("lexicon_id"),
        "lexicon_version": plan.get("lexicon_version"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _serialize_action_plan_occurrence(
    db: Session,
    occurrence: ActionPlanOccurrence,
    *,
    now: datetime | None = None,
) -> dict:
    resolved_now = now or datetime.now(UTC)
    steps = (
        db.query(ActionPlanStep)
        .filter(
            ActionPlanStep.tenant_id == occurrence.tenant_id,
            ActionPlanStep.occurrence_id == occurrence.id,
        )
        .order_by(ActionPlanStep.position.asc(), ActionPlanStep.id.asc())
        .all()
    )
    required_steps = [step for step in steps if step.required]
    completed_required = sum(step.status == "done" for step in required_steps)
    completed_total = sum(step.status in _RESOLVED_STEP_STATUSES for step in steps)
    next_step = next(
        (
            step
            for step in steps
            if step.status not in _RESOLVED_STEP_STATUSES and step.status != "blocked"
        ),
        None,
    )
    if next_step is None:
        next_step = next((step for step in steps if step.status == "blocked"), None)

    due_at = occurrence.due_at
    if due_at is not None and due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    if occurrence.status in {"waiting_for_results", "completed"}:
        due_state = "completed"
    elif occurrence.status == "snoozed":
        due_state = "snoozed"
    elif due_at is None:
        due_state = "later"
    elif due_at < resolved_now:
        due_state = "overdue"
    elif due_at <= resolved_now + timedelta(days=1):
        due_state = "due_now"
    else:
        due_state = "upcoming"

    serialized_steps = [
        {
            "id": step.id,
            "step_key": step.step_key,
            "position": step.position,
            "instruction": step.instruction,
            "required": step.required,
            "status": step.status,
            "blocker_reason": step.blocker_reason,
            "evidence": list(step.evidence or []),
            "completed_by_user_id": step.completed_by_user_id,
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            "updated_at": step.updated_at.isoformat(),
        }
        for step in steps
    ]
    serialized_next = next(
        (item for item in serialized_steps if next_step and item["id"] == next_step.id),
        None,
    )
    return {
        "id": occurrence.id,
        "recommendation_id": occurrence.recommendation_id,
        "action_id": occurrence.action_id,
        "cadence": occurrence.cadence,
        "period_key": occurrence.period_key,
        "timezone": occurrence.timezone,
        "due_at": due_at.isoformat() if due_at else None,
        "due_state": due_state,
        "status": occurrence.status,
        "content_hash": occurrence.content_hash,
        "lexicon_id": occurrence.lexicon_id,
        "lexicon_version": occurrence.lexicon_version,
        "progress": {
            "completed_required": completed_required,
            "required_total": len(required_steps),
            "completed_total": completed_total,
            "total": len(steps),
        },
        "next_step": serialized_next,
        "steps": serialized_steps,
        "completed_at": occurrence.completed_at.isoformat()
        if occurrence.completed_at
        else None,
        "created_at": occurrence.created_at.isoformat(),
        "updated_at": occurrence.updated_at.isoformat(),
    }


def ensure_action_plan_occurrences(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    recommendations: list[StrategyRecommendation],
    action_plans: dict[str, dict],
    now: datetime | None = None,
) -> dict[str, dict]:
    """Materialize one resumable, deterministic work occurrence per action."""

    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    organization_id = campaign.organization_id or tenant_id
    resolved_now = now or datetime.now(UTC)
    recommendation_by_id = {item.id: item for item in recommendations}
    completed_action_ids = {
        row[0]
        for row in (
            db.query(ActionPlanOccurrence.action_id)
            .filter(
                ActionPlanOccurrence.tenant_id == tenant_id,
                ActionPlanOccurrence.campaign_id == campaign_id,
                ActionPlanOccurrence.status.in_({"waiting_for_results", "completed"}),
            )
            .distinct()
            .all()
        )
    }
    work_items: dict[str, dict] = {}

    for recommendation_id, plan in action_plans.items():
        recommendation = recommendation_by_id.get(recommendation_id)
        if recommendation is None:
            continue
        action_id = str(plan["action_id"])
        cadence = _action_plan_cadence(
            plan,
            completed_action_ids=completed_action_ids,
        )
        period_key = _action_plan_period_key(cadence, resolved_now)
        content_hash = _action_plan_content_hash(plan, cadence)

        occurrence = (
            db.query(ActionPlanOccurrence)
            .filter(
                ActionPlanOccurrence.tenant_id == tenant_id,
                ActionPlanOccurrence.campaign_id == campaign_id,
                ActionPlanOccurrence.recommendation_id == recommendation_id,
                ActionPlanOccurrence.action_id == action_id,
                ActionPlanOccurrence.status.in_(_ACTIVE_ACTION_PLAN_STATUSES),
            )
            .order_by(ActionPlanOccurrence.created_at.desc())
            .first()
        )
        if occurrence is None:
            occurrence = (
                db.query(ActionPlanOccurrence)
                .filter(
                    ActionPlanOccurrence.tenant_id == tenant_id,
                    ActionPlanOccurrence.campaign_id == campaign_id,
                    ActionPlanOccurrence.recommendation_id == recommendation_id,
                    ActionPlanOccurrence.action_id == action_id,
                    ActionPlanOccurrence.period_key == period_key,
                    ActionPlanOccurrence.content_hash == content_hash,
                )
                .order_by(ActionPlanOccurrence.created_at.desc())
                .first()
            )
        if occurrence is None:
            idempotency_key = hashlib.sha256(
                f"{tenant_id}:{recommendation_id}:{action_id}:{period_key}:{content_hash}".encode(
                    "utf-8"
                )
            ).hexdigest()
            occurrence = ActionPlanOccurrence(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign_id,
                business_location_id=campaign.business_location_id,
                recommendation_id=recommendation_id,
                action_id=action_id,
                cadence=cadence,
                period_key=period_key,
                timezone="UTC",
                due_at=_action_plan_due_at(cadence, resolved_now),
                status="ready",
                lexicon_id=str(plan["lexicon_id"]),
                lexicon_version=str(plan["lexicon_version"]),
                content_hash=content_hash,
                idempotency_key=idempotency_key,
                created_at=resolved_now,
                updated_at=resolved_now,
            )
            db.add(occurrence)
            db.flush()
            for position, instruction in enumerate(plan.get("steps", []), start=1):
                step_key = hashlib.sha256(
                    f"{action_id}:{position}:{instruction}".encode("utf-8")
                ).hexdigest()[:40]
                db.add(
                    ActionPlanStep(
                        tenant_id=tenant_id,
                        organization_id=organization_id,
                        occurrence_id=occurrence.id,
                        step_key=step_key,
                        position=position,
                        instruction=str(instruction),
                        required=True,
                        status="not_started",
                        created_at=resolved_now,
                        updated_at=resolved_now,
                    )
                )
            db.flush()

        work_items[recommendation_id] = _serialize_action_plan_occurrence(
            db,
            occurrence,
            now=resolved_now,
        )

    db.commit()
    return work_items


def update_action_plan_step(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    occurrence_id: str,
    step_id: str,
    step_status: str,
    blocker_reason: str | None,
    evidence: list[str] | None,
    actor_user_id: str,
) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    occurrence = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.id == occurrence_id,
            ActionPlanOccurrence.tenant_id == tenant_id,
            ActionPlanOccurrence.organization_id == organization_id,
            ActionPlanOccurrence.campaign_id == campaign_id,
        )
        .first()
    )
    if occurrence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action plan not found")
    step = (
        db.query(ActionPlanStep)
        .filter(
            ActionPlanStep.id == step_id,
            ActionPlanStep.tenant_id == tenant_id,
            ActionPlanStep.organization_id == organization_id,
            ActionPlanStep.occurrence_id == occurrence_id,
        )
        .first()
    )
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist step not found")

    resolved_now = datetime.now(UTC)
    step.status = step_status
    step.blocker_reason = blocker_reason if step_status == "blocked" else None
    if evidence is not None:
        step.evidence = [str(item) for item in evidence]
    if step_status in _RESOLVED_STEP_STATUSES:
        step.completed_by_user_id = actor_user_id
        step.completed_at = resolved_now
    else:
        step.completed_by_user_id = None
        step.completed_at = None
    step.updated_at = resolved_now
    db.flush()

    steps = (
        db.query(ActionPlanStep)
        .filter(
            ActionPlanStep.tenant_id == tenant_id,
            ActionPlanStep.occurrence_id == occurrence_id,
        )
        .order_by(ActionPlanStep.position.asc())
        .all()
    )
    required_steps = [item for item in steps if item.required]
    if required_steps and all(item.status == "done" for item in required_steps):
        occurrence.status = "waiting_for_results"
        occurrence.completed_at = resolved_now
    elif any(item.status == "blocked" for item in steps):
        occurrence.status = "blocked"
        occurrence.completed_at = None
    elif any(item.status in {"in_progress", "done"} for item in steps):
        occurrence.status = "in_progress"
        occurrence.completed_at = None
    else:
        occurrence.status = "ready"
        occurrence.completed_at = None
    occurrence.updated_at = resolved_now
    db.commit()
    db.refresh(occurrence)
    return _serialize_action_plan_occurrence(db, occurrence, now=resolved_now)


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def _required_milestones_for_month(month_number: int) -> list[str]:
    mapping = {
        1: ["crawl_baseline_complete", "rank_baseline_complete"],
        2: ["on_page_fixes_started", "content_plan_published"],
        3: ["citation_stack_started", "outreach_seeded"],
    }
    return mapping.get(month_number, [f"month_{month_number}_core_complete"])


def evaluate_monthly_rules(db: Session, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    required = _required_milestones_for_month(month_number)
    created = 0
    for key in required:
        row = (
            db.query(CampaignMilestone)
            .filter(
                CampaignMilestone.tenant_id == tenant_id,
                CampaignMilestone.campaign_id == campaign_id,
                CampaignMilestone.month_number == month_number,
                CampaignMilestone.milestone_key == key,
            )
            .first()
        )
        if row is None:
            db.add(
                CampaignMilestone(
                    tenant_id=tenant_id,
                    campaign_id=campaign_id,
                    month_number=month_number,
                    milestone_key=key,
                    status="pending",
                )
            )
            created += 1
    db.commit()
    return {"campaign_id": campaign_id, "month_number": month_number, "required_milestones": required, "created": created}


def schedule_monthly_actions(db: Session, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    summary = evaluate_monthly_rules(db, tenant_id, campaign_id, month_number)
    return {"campaign_id": campaign_id, "month_number": month_number, "actions_scheduled": len(summary["required_milestones"])}


def compute_score(db: Session, tenant_id: str, campaign_id: str) -> IntelligenceScore:
    _campaign_or_404(db, tenant_id, campaign_id)
    issue_count = db.query(TechnicalIssue).filter(TechnicalIssue.tenant_id == tenant_id, TechnicalIssue.campaign_id == campaign_id).count()
    published_count = (
        db.query(ContentAsset)
        .filter(ContentAsset.tenant_id == tenant_id, ContentAsset.campaign_id == campaign_id, ContentAsset.status == "published")
        .count()
    )
    avg_rank = db.query(Ranking).filter(Ranking.tenant_id == tenant_id, Ranking.campaign_id == campaign_id).all()
    avg_rank_pos = (sum(r.current_position for r in avg_rank) / len(avg_rank)) if avg_rank else 100.0
    health = (
        db.query(LocalHealthSnapshot)
        .filter(LocalHealthSnapshot.tenant_id == tenant_id, LocalHealthSnapshot.campaign_id == campaign_id)
        .order_by(LocalHealthSnapshot.captured_at.desc())
        .first()
    )
    local_health = health.health_score if health else 50.0

    score_value = max(
        0.0,
        min(
            100.0,
            (100.0 - min(avg_rank_pos, 100.0)) * 0.35
            + max(0, 30 - issue_count) * 1.0
            + min(published_count * 5, 20)
            + (local_health * 0.25),
        ),
    )
    details = {
        "issue_count": issue_count,
        "published_count": published_count,
        "avg_rank_position": round(avg_rank_pos, 2),
        "local_health": round(local_health, 2),
    }
    row = IntelligenceScore(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        score_type="composite",
        score_value=round(score_value, 2),
        details_json=json.dumps(details),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def detect_anomalies(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    latest_two = (
        db.query(IntelligenceScore)
        .filter(IntelligenceScore.tenant_id == tenant_id, IntelligenceScore.campaign_id == campaign_id)
        .order_by(IntelligenceScore.captured_at.desc())
        .limit(2)
        .all()
    )
    created = 0
    if len(latest_two) >= 2:
        delta = latest_two[0].score_value - latest_two[1].score_value
        if delta <= -15:
            db.add(
                AnomalyEvent(
                    tenant_id=tenant_id,
                    campaign_id=campaign_id,
                    anomaly_type="score_drop",
                    severity="high",
                    details_json=json.dumps({"delta": delta}),
                )
            )
            created += 1
    db.commit()
    return {"campaign_id": campaign_id, "anomalies_created": created}


def upsert_recommendations(db: Session, tenant_id: str, campaign_id: str) -> list[StrategyRecommendation]:
    score = (
        db.query(IntelligenceScore)
        .filter(IntelligenceScore.tenant_id == tenant_id, IntelligenceScore.campaign_id == campaign_id)
        .order_by(IntelligenceScore.captured_at.desc())
        .first()
    )
    recommendations: list[StrategyRecommendation] = []
    if score is None:
        score = compute_score(db, tenant_id, campaign_id)
    if score.score_value < 40:
        recommendations.append(
            StrategyRecommendation(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                recommendation_type="stabilize_foundations",
                rationale="Composite score is low; prioritize technical fixes and local profile improvements.",
                confidence=0.82,
                confidence_score=0.82,
                evidence_json=json.dumps(
                    [
                        "intelligence_score_below_threshold",
                        "technical_issue_pressure_detected",
                    ]
                ),
                risk_tier=1,
                rollback_plan_json=json.dumps(
                    {
                        "steps": [
                            "revert_content_changes",
                            "recompute_score_snapshot",
                        ]
                    }
                ),
                status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
            )
        )
    else:
        recommendations.append(
            StrategyRecommendation(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                recommendation_type="scale_growth_content",
                rationale="Baseline score is stable; increase content throughput and backlink acquisition velocity.",
                confidence=0.76,
                confidence_score=0.76,
                evidence_json=json.dumps(
                    [
                        "intelligence_score_stable",
                        "growth_capacity_available",
                    ]
                ),
                risk_tier=1,
                rollback_plan_json=json.dumps(
                    {
                        "steps": [
                            "revert_growth_plan_tasks",
                            "restore_prior_campaign_plan",
                        ]
                    }
                ),
                status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
            )
        )
    for rec in recommendations:
        _validate_recommendation_payload(rec)
    for rec in recommendations:
        db.add(rec)
        db.flush()
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="recommendation.generated",
            payload={"campaign_id": campaign_id, "recommendation_id": rec.id, "status": rec.status},
        )
    db.commit()
    return recommendations


def _validate_recommendation_payload(rec: StrategyRecommendation) -> None:
    if rec.confidence_score < 0.0 or rec.confidence_score > 1.0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confidence_score must be between 0 and 1")
    if rec.risk_tier < 0 or rec.risk_tier > 4:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="risk_tier must be between 0 and 4")
    try:
        evidence = json.loads(rec.evidence_json or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="evidence_json must be valid JSON list") from exc
    evidence_items = evidence.get("evidence") if isinstance(evidence, dict) else evidence
    if not isinstance(evidence_items, list) or len(evidence_items) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="evidence must be a non-empty array")
    try:
        rollback_plan = json.loads(rec.rollback_plan_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rollback_plan_json must be valid JSON object") from exc
    if not isinstance(rollback_plan, dict) or len(rollback_plan) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rollback_plan must be a non-empty object")


def transition_recommendation_state(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    recommendation_id: str,
    target_state: str,
) -> StrategyRecommendation:
    row = db.get(StrategyRecommendation, recommendation_id)
    if row is None or row.tenant_id != tenant_id or row.campaign_id != campaign_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    allowed = RECOMMENDATION_ALLOWED_TRANSITIONS.get(row.status, set())
    if target_state not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid recommendation transition: {row.status} -> {target_state}",
        )
    if target_state in {"APPROVED", "SCHEDULED", " EXECUTED"} and row.status != "VALIDATED" and row.status != "APPROVED" and row.status != "SCHEDULED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Activation blocked: recommendation must be VALIDATED first",
        )
    _validate_recommendation_payload(row)
    row.status = ensure_enum(target_state, StrategyRecommendationStatus)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type=f"recommendation.{target_state.lower()}",
        payload={"campaign_id": campaign_id, "recommendation_id": recommendation_id, "target_state": target_state},
    )
    if target_state == "SCHEDULED":
        # Scheduling stays an explicit lifecycle step. Only queue an execution
        # once the recommendation is intentionally advanced beyond APPROVED.
        schedule_execution(recommendation_id, db=db)
    db.commit()
    db.refresh(row)
    return row


def get_latest_score(db: Session, tenant_id: str, campaign_id: str) -> IntelligenceScore:
    row = (
        db.query(IntelligenceScore)
        .filter(IntelligenceScore.tenant_id == tenant_id, IntelligenceScore.campaign_id == campaign_id)
        .order_by(IntelligenceScore.captured_at.desc())
        .first()
    )
    if row is None:
        row = compute_score(db, tenant_id, campaign_id)
    return row


def get_recommendations(db: Session, tenant_id: str, campaign_id: str) -> list[StrategyRecommendation]:
    rows = (
        db.query(StrategyRecommendation)
        .filter(StrategyRecommendation.tenant_id == tenant_id, StrategyRecommendation.campaign_id == campaign_id)
        .order_by(StrategyRecommendation.created_at.desc())
        .all()
    )
    if rows:
        return rows
    return upsert_recommendations(db, tenant_id, campaign_id)


def get_recommendation_summary(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    total = (
        db.query(func.count(StrategyRecommendation.id))
        .filter(StrategyRecommendation.tenant_id == tenant_id, StrategyRecommendation.campaign_id == campaign_id)
        .scalar()
        or 0
    )
    by_state_rows = (
        db.query(StrategyRecommendation.status, func.count(StrategyRecommendation.id))
        .filter(StrategyRecommendation.tenant_id == tenant_id, StrategyRecommendation.campaign_id == campaign_id)
        .group_by(StrategyRecommendation.status)
        .all()
    )
    by_risk_rows = (
        db.query(StrategyRecommendation.risk_tier, func.count(StrategyRecommendation.id))
        .filter(StrategyRecommendation.tenant_id == tenant_id, StrategyRecommendation.campaign_id == campaign_id)
        .group_by(StrategyRecommendation.risk_tier)
        .all()
    )
    avg_confidence = (
        db.query(func.avg(StrategyRecommendation.confidence_score))
        .filter(StrategyRecommendation.tenant_id == tenant_id, StrategyRecommendation.campaign_id == campaign_id)
        .scalar()
    )
    recommendation_rows = (
        db.query(StrategyRecommendation)
        .filter(
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
        )
        .all()
    )
    return {
        "campaign_id": campaign_id,
        "total_count": int(total),
        "counts_by_state": {str(state): int(count) for state, count in by_state_rows},
        "counts_by_risk_tier": {str(risk): int(count) for risk, count in by_risk_rows},
        "average_confidence_score": round(float(avg_confidence), 4) if avg_confidence is not None else 0.0,
        "engine": build_intelligence_engine_state(recommendation_rows),
    }


def advance_month(db: Session, tenant_id: str, campaign_id: str, override: bool) -> dict:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    current_month = campaign.month_number
    evaluate_monthly_rules(db, tenant_id, campaign_id, current_month)
    pending = (
        db.query(CampaignMilestone)
        .filter(
            CampaignMilestone.tenant_id == tenant_id,
            CampaignMilestone.campaign_id == campaign_id,
            CampaignMilestone.month_number == current_month,
            CampaignMilestone.status != "completed",
        )
        .all()
    )
    if pending and not override:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Month advancement blocked: {len(pending)} milestones incomplete.",
        )
    if override:
        for row in pending:
            row.status = "completed"
            row.completed_at = datetime.now(UTC)
    campaign.month_number = min(12, campaign.month_number + 1)
    db.commit()
    return {"campaign_id": campaign.id, "advanced_to_month": campaign.month_number, "override": override}




