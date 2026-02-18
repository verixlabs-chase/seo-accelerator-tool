import json
import re
from collections.abc import Iterable
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.campaign import Campaign
from app.models.competitor import CompetitorPage
from app.models.crawl import CrawlPageResult, Page
from app.models.entity import CompetitorEntity, EntityAnalysisRun, PageEntity
from app.models.intelligence import StrategyRecommendation
from app.services import observability_service

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
_STOPWORDS = {
    "the",
    "and",
    "with",
    "for",
    "from",
    "that",
    "this",
    "your",
    "are",
    "you",
    "www",
    "com",
    "https",
    "http",
}


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def _extract_entities(chunks: Iterable[str]) -> set[str]:
    entities: set[str] = set()
    for chunk in chunks:
        for token in _TOKEN_RE.findall((chunk or "").lower()):
            if token in _STOPWORDS:
                continue
            entities.add(token)
    return entities


def _url_tokens(url: str) -> list[str]:
    parsed = urlparse(url or "")
    host = parsed.netloc.replace(".", " ")
    path = parsed.path.replace("/", " ")
    return [host, path]


def extract_page_entities(db: Session, tenant_id: str, campaign_id: str) -> int:
    _campaign_or_404(db, tenant_id, campaign_id)
    rows = (
        db.query(CrawlPageResult, Page)
        .join(Page, Page.id == CrawlPageResult.page_id)
        .filter(CrawlPageResult.tenant_id == tenant_id, CrawlPageResult.campaign_id == campaign_id)
        .all()
    )
    created = 0
    for result, page in rows:
        entities = _extract_entities([result.title or "", page.url or "", *_url_tokens(page.url)])
        for entity in entities:
            try:
                with db.begin_nested():
                    row = PageEntity(
                        tenant_id=tenant_id,
                        campaign_id=campaign_id,
                        page_id=page.id,
                        crawl_page_result_id=result.id,
                        entity=entity,
                        source_type="page",
                    )
                    db.add(row)
                    db.flush()
                    created += 1
            except IntegrityError:
                continue
    db.commit()
    return created


def extract_competitor_entities(db: Session, tenant_id: str, campaign_id: str) -> int:
    _campaign_or_404(db, tenant_id, campaign_id)
    pages = (
        db.query(CompetitorPage)
        .filter(CompetitorPage.tenant_id == tenant_id, CompetitorPage.campaign_id == campaign_id)
        .all()
    )
    created = 0
    for page in pages:
        entities = _extract_entities([page.url or "", *_url_tokens(page.url)])
        for entity in entities:
            try:
                with db.begin_nested():
                    row = CompetitorEntity(
                        tenant_id=tenant_id,
                        campaign_id=campaign_id,
                        competitor_id=page.competitor_id,
                        competitor_page_id=page.id,
                        entity=entity,
                        source_type="serp_snapshot",
                    )
                    db.add(row)
                    db.flush()
                    created += 1
            except IntegrityError:
                continue
    db.commit()
    return created


def _build_recommendations(missing_entities: list[str], confidence_score: float, evidence: list[str]) -> list[dict]:
    if not missing_entities:
        return []
    return [
        {
            "recommendation_type": "entity_gap_remediation",
            "confidence_score": confidence_score,
            "evidence": evidence,
            "expected_impact": "Improve semantic authority coverage against competitor entity footprint.",
            "risk_tier": 1,
            "rollback_plan": {"steps": ["remove_entity_targets", "recompute_entity_analysis"]},
        }
    ]


def run_entity_analysis(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    page_created = extract_page_entities(db, tenant_id, campaign_id)
    competitor_created = extract_competitor_entities(db, tenant_id, campaign_id)

    page_entities = {
        row[0]
        for row in db.query(PageEntity.entity)
        .filter(PageEntity.tenant_id == tenant_id, PageEntity.campaign_id == campaign_id)
        .all()
    }
    competitor_entities = {
        row[0]
        for row in db.query(CompetitorEntity.entity)
        .filter(CompetitorEntity.tenant_id == tenant_id, CompetitorEntity.campaign_id == campaign_id)
        .all()
    }
    overlap = page_entities.intersection(competitor_entities)
    missing = sorted(list(competitor_entities - page_entities))
    if len(competitor_entities) == 0:
        entity_score = 100.0
    else:
        entity_score = round((len(overlap) / max(1, len(competitor_entities))) * 100.0, 2)
    confidence_score = round(min(1.0, 0.4 + ((len(page_entities) + len(competitor_entities)) / 100.0)), 2)
    evidence = [
        f"campaign_entities={len(page_entities)}",
        f"competitor_entities={len(competitor_entities)}",
        f"overlap_count={len(overlap)}",
    ]
    recommendations = _build_recommendations(missing, confidence_score, evidence)

    analysis = EntityAnalysisRun(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        entity_score=entity_score,
        overlap_count=len(overlap),
        campaign_entity_count=len(page_entities),
        competitor_entity_count=len(competitor_entities),
        missing_entities_json=json.dumps(missing),
        confidence_score=confidence_score,
        evidence_json=json.dumps(evidence),
        recommendations_json=json.dumps(recommendations),
    )
    db.add(analysis)
    db.flush()

    for rec in recommendations:
        db.add(
            StrategyRecommendation(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                recommendation_type=rec["recommendation_type"],
                rationale=rec["expected_impact"],
                confidence=rec["confidence_score"],
                confidence_score=rec["confidence_score"],
                evidence_json=json.dumps(rec["evidence"]),
                risk_tier=rec["risk_tier"],
                rollback_plan_json=json.dumps(rec["rollback_plan"]),
                status="GENERATED",
            )
        )

    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="entity.analysis.completed",
        payload={
            "campaign_id": campaign_id,
            "analysis_id": analysis.id,
            "entity_score": entity_score,
            "missing_entities": missing[:25],
        },
    )
    observability_service.record_entity_analysis()
    db.commit()
    return {
        "id": analysis.id,
        "campaign_id": campaign_id,
        "entity_score": entity_score,
        "missing_entities": missing[:25],
        "confidence_score": confidence_score,
        "evidence": evidence,
        "recommendations": recommendations,
        "created_at": analysis.created_at,
        "entities_extracted": {"pages": page_created, "competitors": competitor_created},
    }


def get_latest_entity_report(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    row = (
        db.query(EntityAnalysisRun)
        .filter(EntityAnalysisRun.tenant_id == tenant_id, EntityAnalysisRun.campaign_id == campaign_id)
        .order_by(EntityAnalysisRun.created_at.desc())
        .first()
    )
    if row is None:
        return run_entity_analysis(db, tenant_id, campaign_id)
    return {
        "id": row.id,
        "campaign_id": campaign_id,
        "entity_score": row.entity_score,
        "missing_entities": json.loads(row.missing_entities_json or "[]"),
        "confidence_score": row.confidence_score,
        "evidence": json.loads(row.evidence_json or "[]"),
        "recommendations": json.loads(row.recommendations_json or "[]"),
        "created_at": row.created_at,
    }
