import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.campaign import Campaign
from app.models.content import ContentAsset
from app.models.crawl import TechnicalIssue
from app.models.intelligence import AnomalyEvent, CampaignMilestone, IntelligenceScore, StrategyRecommendation
from app.models.local import LocalHealthSnapshot
from app.models.rank import Ranking

RECOMMENDATION_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"GENERATED"},
    "GENERATED": {"VALIDATED", " FAILED", "ARCHIVED"},
    "VALIDATED": {"APPROVED", " FAILED", "ARCHIVED"},
    "APPROVED": {"SCHEDULED", "ARCHIVED"},
    "SCHEDULED": {" EXECUTED", " FAILED", " ROLLED_BACK"},
    ' EXECUTED': set(),
    ' FAILED': set(),
    ' ROLLED_BACK': set(),
    "ARCHIVED": set(),
}


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
                status="GENERATED",
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
                status="GENERATED",
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
    if not isinstance(evidence, list) or len(evidence) == 0:
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
    row.status = target_state
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type=f"recommendation.{target_state.lower()}",
        payload={"campaign_id": campaign_id, "recommendation_id": recommendation_id, "target_state": target_state},
    )
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
    return {
        "campaign_id": campaign_id,
        "total_count": int(total),
        "counts_by_state": {str(state): int(count) for state, count in by_state_rows},
        "counts_by_risk_tier": {str(risk): int(count) for risk, count in by_risk_rows},
        "average_confidence_score": round(float(avg_confidence), 4) if avg_confidence is not None else 0.0,
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
