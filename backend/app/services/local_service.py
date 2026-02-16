import json
from datetime import UTC, datetime, timedelta
from random import randint, uniform

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.local import LocalHealthSnapshot, LocalProfile, Review, ReviewVelocitySnapshot


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def _get_profile_or_create(db: Session, tenant_id: str, campaign_id: str) -> LocalProfile:
    profile = (
        db.query(LocalProfile)
        .filter(LocalProfile.tenant_id == tenant_id, LocalProfile.campaign_id == campaign_id)
        .first()
    )
    if profile:
        return profile
    _campaign_or_404(db, tenant_id, campaign_id)
    profile = LocalProfile(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        provider="gbp",
        profile_name="Primary GBP Profile",
        map_pack_position=randint(1, 20),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def collect_profile_snapshot(db: Session, tenant_id: str, campaign_id: str) -> LocalProfile:
    profile = _get_profile_or_create(db, tenant_id, campaign_id)
    profile.map_pack_position = randint(1, 20)
    profile.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(profile)
    return profile


def compute_health_score(db: Session, tenant_id: str, campaign_id: str) -> dict:
    profile = _get_profile_or_create(db, tenant_id, campaign_id)
    map_pack = profile.map_pack_position or 20
    score = max(0.0, min(100.0, 100.0 - (map_pack * 3.0) + uniform(-5.0, 5.0)))
    snap = LocalHealthSnapshot(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        profile_id=profile.id,
        health_score=round(score, 2),
        details_json=json.dumps({"map_pack_position": map_pack}),
    )
    db.add(snap)
    db.commit()
    return {"campaign_id": campaign_id, "profile_id": profile.id, "health_score": snap.health_score}


def get_latest_health(db: Session, tenant_id: str, campaign_id: str) -> dict:
    profile = _get_profile_or_create(db, tenant_id, campaign_id)
    snap = (
        db.query(LocalHealthSnapshot)
        .filter(LocalHealthSnapshot.tenant_id == tenant_id, LocalHealthSnapshot.campaign_id == campaign_id)
        .order_by(LocalHealthSnapshot.captured_at.desc())
        .first()
    )
    if snap is None:
        return compute_health_score(db, tenant_id, campaign_id)
    return {
        "campaign_id": campaign_id,
        "profile_id": profile.id,
        "health_score": snap.health_score,
        "captured_at": snap.captured_at.isoformat(),
    }


def ingest_reviews(db: Session, tenant_id: str, campaign_id: str) -> dict:
    profile = _get_profile_or_create(db, tenant_id, campaign_id)
    now = datetime.now(UTC)
    created = 0
    for i in range(5):
        external_id = f"{campaign_id}-r-{i}"
        existing = (
            db.query(Review)
            .filter(Review.tenant_id == tenant_id, Review.campaign_id == campaign_id, Review.external_review_id == external_id)
            .first()
        )
        if existing:
            continue
        rating = round(uniform(3.0, 5.0), 1)
        sentiment = "positive" if rating >= 4.0 else "neutral"
        db.add(
            Review(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                profile_id=profile.id,
                external_review_id=external_id,
                rating=rating,
                sentiment=sentiment,
                body=f"Sample review {i}",
                reviewed_at=now - timedelta(days=i * 2),
            )
        )
        created += 1
    db.commit()
    return {"campaign_id": campaign_id, "reviews_ingested": created}


def compute_review_velocity(db: Session, tenant_id: str, campaign_id: str) -> dict:
    profile = _get_profile_or_create(db, tenant_id, campaign_id)
    window_start = datetime.now(UTC) - timedelta(days=30)
    rows = (
        db.query(Review)
        .filter(
            Review.tenant_id == tenant_id,
            Review.campaign_id == campaign_id,
            Review.profile_id == profile.id,
            Review.reviewed_at >= window_start,
        )
        .all()
    )
    count = len(rows)
    avg = round(sum(r.rating for r in rows) / count, 2) if count else 0.0
    snap = ReviewVelocitySnapshot(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        profile_id=profile.id,
        reviews_last_30d=count,
        avg_rating_last_30d=avg,
    )
    db.add(snap)
    db.commit()
    return {
        "campaign_id": campaign_id,
        "profile_id": profile.id,
        "reviews_last_30d": count,
        "avg_rating_last_30d": avg,
    }


def get_reviews(db: Session, tenant_id: str, campaign_id: str) -> list[dict]:
    rows = (
        db.query(Review)
        .filter(Review.tenant_id == tenant_id, Review.campaign_id == campaign_id)
        .order_by(Review.reviewed_at.desc())
        .all()
    )
    return [
        {
            "external_review_id": r.external_review_id,
            "rating": r.rating,
            "sentiment": r.sentiment,
            "reviewed_at": r.reviewed_at.isoformat(),
        }
        for r in rows
    ]


def get_velocity(db: Session, tenant_id: str, campaign_id: str) -> dict:
    snap = (
        db.query(ReviewVelocitySnapshot)
        .filter(ReviewVelocitySnapshot.tenant_id == tenant_id, ReviewVelocitySnapshot.campaign_id == campaign_id)
        .order_by(ReviewVelocitySnapshot.captured_at.desc())
        .first()
    )
    if snap is None:
        return compute_review_velocity(db, tenant_id, campaign_id)
    return {
        "campaign_id": campaign_id,
        "profile_id": snap.profile_id,
        "reviews_last_30d": snap.reviews_last_30d,
        "avg_rating_last_30d": snap.avg_rating_last_30d,
        "captured_at": snap.captured_at.isoformat(),
    }

