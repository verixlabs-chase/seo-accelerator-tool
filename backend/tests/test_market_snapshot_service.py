from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models.campaign import Campaign
from app.models.rank import CampaignKeyword, KeywordCluster
from app.models.user import User
from app.services import market_snapshot_service


def _build_keyword(db_session) -> CampaignKeyword:
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name="Market Campaign",
        domain="market.example",
        created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(campaign)
    db_session.flush()
    cluster = KeywordCluster(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        name="Market",
        created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(cluster)
    db_session.flush()
    keyword = CampaignKeyword(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        cluster_id=cluster.id,
        keyword="keyword market",
        location_code="US",
        created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(keyword)
    db_session.commit()
    return keyword


def test_market_snapshot_upsert_is_hash_guarded(db_session) -> None:
    keyword = _build_keyword(db_session)
    snapshot_input = market_snapshot_service.KeywordMarketSnapshotInput(
        keyword_id=keyword.id,
        search_volume=1000,
        avg_cpc=Decimal("12.50"),
        geo_scope="US",
        device_class="desktop",
        source_provider="manual",
        snapshot_date=date(2026, 3, 2),
        confidence_score=0.8,
    )

    row = market_snapshot_service.upsert_keyword_market_snapshot(db_session, snapshot_input)
    first_hash = row.deterministic_hash
    first_updated_at = row.updated_at

    row_again = market_snapshot_service.upsert_keyword_market_snapshot(db_session, snapshot_input)

    assert row_again.id == row.id
    assert row_again.deterministic_hash == first_hash
    assert row_again.updated_at == first_updated_at


def test_market_snapshot_version_drift_updates_hash(db_session) -> None:
    keyword = _build_keyword(db_session)
    original = market_snapshot_service.KeywordMarketSnapshotInput(
        keyword_id=keyword.id,
        search_volume=1000,
        avg_cpc=Decimal("12.50"),
        geo_scope="US",
        device_class="desktop",
        source_provider="manual",
        snapshot_date=date(2026, 3, 2),
        confidence_score=0.8,
    )
    changed = market_snapshot_service.KeywordMarketSnapshotInput(
        keyword_id=keyword.id,
        search_volume=1000,
        avg_cpc=Decimal("14.00"),
        geo_scope="US",
        device_class="desktop",
        source_provider="manual",
        snapshot_date=date(2026, 3, 2),
        confidence_score=0.8,
    )

    row = market_snapshot_service.upsert_keyword_market_snapshot(db_session, original)
    first_hash = row.deterministic_hash
    updated = market_snapshot_service.upsert_keyword_market_snapshot(db_session, changed)

    assert updated.id == row.id
    assert updated.deterministic_hash != first_hash
    assert updated.avg_cpc == Decimal("14.00")


def test_market_snapshot_replay_mode_is_read_only(monkeypatch) -> None:
    monkeypatch.setenv("REPLAY_MODE", "1")
    normalized = market_snapshot_service.normalize_keyword_market_snapshot(
        market_snapshot_service.KeywordMarketSnapshotInput(
            keyword_id="keyword-1",
            search_volume=500,
            avg_cpc=Decimal("9.25"),
            geo_scope="US",
            device_class="mobile",
            source_provider="manual",
            snapshot_date=date(2026, 3, 2),
            confidence_score=0.75,
        )
    )

    assert market_snapshot_service.replay_mode_enabled() is True
    assert normalized["avg_cpc"] == "9.25"
    assert normalized["device_class"] == "mobile"
