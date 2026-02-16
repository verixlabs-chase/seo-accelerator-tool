import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.content import ContentAsset
from app.models.crawl import TechnicalIssue
from app.models.intelligence import AnomalyEvent, CampaignMilestone, IntelligenceScore, StrategyRecommendation
from app.models.local import LocalHealthSnapshot
from app.models.rank import Ranking


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
            )
        )
    for rec in recommendations:
        db.add(rec)
    db.commit()
    return recommendations


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

