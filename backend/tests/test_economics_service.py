from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.campaign import Campaign
from app.models.keyword_daily_economics import KeywordDailyEconomics
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking
from app.models.user import User
from app.services import economics_service, market_snapshot_service


def _build_keyword_fixture(db_session) -> tuple[Campaign, CampaignKeyword]:
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name="Economics Campaign",
        domain="economics.example",
        created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(campaign)
    db_session.flush()
    cluster = KeywordCluster(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        name="Core",
        created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(cluster)
    db_session.flush()
    keyword = CampaignKeyword(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        cluster_id=cluster.id,
        keyword="organic media value",
        location_code="US",
        created_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(keyword)
    db_session.flush()
    ranking = Ranking(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        keyword_id=keyword.id,
        current_position=7,
        previous_position=9,
        delta=2,
        confidence=0.9,
        updated_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
    )
    db_session.add(ranking)
    db_session.commit()
    return campaign, keyword


def _seed_snapshot(db_session, keyword_id: str, *, avg_cpc: str = "12.00", device_class: str = "desktop") -> None:
    market_snapshot_service.upsert_keyword_market_snapshot(
        db_session,
        market_snapshot_service.KeywordMarketSnapshotInput(
            keyword_id=keyword_id,
            search_volume=1000,
            avg_cpc=Decimal(avg_cpc),
            geo_scope="US",
            device_class=device_class,
            source_provider="manual",
            snapshot_date=date(2026, 3, 2),
            confidence_score=0.8,
        ),
    )


def test_ctr_curve_math_is_deterministic() -> None:
    desktop = economics_service.ctr_for_rank(3, device_class="desktop")
    mobile = economics_service.ctr_for_rank(3, device_class="mobile")

    assert desktop == Decimal("0.110000")
    assert mobile == Decimal("0.104000")
    assert economics_service.calculate_estimated_clicks(1000, 3, device_class="desktop") == 110


def test_keyword_economics_hash_is_stable() -> None:
    metric_input = economics_service.KeywordEconomicsInput(
        campaign_id="campaign-1",
        keyword_id="keyword-1",
        metric_date=date(2026, 3, 2),
        search_volume=1200,
        cpc=Decimal("18.50"),
        rank=7,
        device_class="desktop",
    )

    first = economics_service.normalize_keyword_daily_economics(metric_input)
    second = economics_service.normalize_keyword_daily_economics(metric_input)

    assert first == second
    assert first["deterministic_hash"] == second["deterministic_hash"]


def test_upsert_keyword_daily_economics_reads_stored_snapshot(db_session) -> None:
    campaign, keyword = _build_keyword_fixture(db_session)
    _seed_snapshot(db_session, keyword.id)
    metric_input = economics_service.build_keyword_economics_input_from_ranking(
        db_session,
        keyword_id=keyword.id,
        metric_date=date(2026, 3, 2),
    )

    row = economics_service.upsert_keyword_daily_economics(db_session, metric_input)
    first_updated_at = row.updated_at
    first_hash = row.deterministic_hash

    row_again = economics_service.upsert_keyword_daily_economics(db_session, metric_input)

    assert row.id == row_again.id
    assert row_again.updated_at == first_updated_at
    assert row_again.deterministic_hash == first_hash
    assert row_again.estimated_clicks == 36
    assert row_again.paid_equivalent_value == Decimal("432.00")
    assert row_again.campaign_id == campaign.id
    assert row_again.ctr_model_version == "ctr-v1:desktop"


def test_snapshot_drift_changes_economics_output(db_session) -> None:
    _campaign, keyword = _build_keyword_fixture(db_session)
    _seed_snapshot(db_session, keyword.id, avg_cpc="12.00")
    metric_input = economics_service.build_keyword_economics_input_from_ranking(
        db_session,
        keyword_id=keyword.id,
        metric_date=date(2026, 3, 2),
    )
    row = economics_service.upsert_keyword_daily_economics(db_session, metric_input)
    first_hash = row.deterministic_hash

    _seed_snapshot(db_session, keyword.id, avg_cpc="14.00")
    refreshed_input = economics_service.build_keyword_economics_input_from_ranking(
        db_session,
        keyword_id=keyword.id,
        metric_date=date(2026, 3, 2),
    )
    updated = economics_service.upsert_keyword_daily_economics(db_session, refreshed_input)

    assert updated.deterministic_hash != first_hash
    assert updated.paid_equivalent_value == Decimal("504.00")


def test_simulate_rank_reads_latest_snapshot(db_session) -> None:
    _campaign, keyword = _build_keyword_fixture(db_session)
    _seed_snapshot(db_session, keyword.id, avg_cpc="14.00")
    result = economics_service.simulate_rank(db_session, keyword.id, 2)

    assert result["projected_clicks"] == 157
    assert result["projected_value"] == Decimal("2198.00")
    assert result["delta_value"] == Decimal("1694.00")
    assert result["opportunity_gap"] == Decimal("1694.00")
    assert result["current_rank"] == 7.0
    assert result["snapshot_date"] == "2026-03-02"


def test_replay_mode_does_not_change_economics_outputs(monkeypatch) -> None:
    monkeypatch.setenv("REPLAY_MODE", "1")
    metric_input = economics_service.KeywordEconomicsInput(
        campaign_id="campaign-1",
        keyword_id="keyword-1",
        metric_date=date(2026, 3, 2),
        search_volume=750,
        cpc=Decimal("8.50"),
        rank=5,
    )

    normalized = economics_service.normalize_keyword_daily_economics(metric_input)

    assert economics_service.replay_mode_enabled() is True
    assert normalized["estimated_clicks"] == 46
    assert normalized["paid_equivalent_value"] == "391.00"


def test_keyword_daily_economics_unique_constraint_enforced(db_session) -> None:
    campaign, keyword = _build_keyword_fixture(db_session)
    now = datetime.now(UTC)
    db_session.add(
        KeywordDailyEconomics(
            campaign_id=campaign.id,
            keyword_id=keyword.id,
            metric_date=date(2026, 3, 2),
            search_volume=100,
            cpc=Decimal("5.00"),
            estimated_clicks=10,
            paid_equivalent_value=Decimal("50.00"),
            ctr_model_version=economics_service.CTR_MODEL_VERSION,
            deterministic_hash="a" * 64,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    db_session.add(
        KeywordDailyEconomics(
            campaign_id=campaign.id,
            keyword_id=keyword.id,
            metric_date=date(2026, 3, 2),
            search_volume=200,
            cpc=Decimal("6.00"),
            estimated_clicks=20,
            paid_equivalent_value=Decimal("120.00"),
            ctr_model_version=economics_service.CTR_MODEL_VERSION,
            deterministic_hash="b" * 64,
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def _seed_keyword_economics(
    db_session,
    campaign: Campaign,
    *,
    keyword_text: str,
    position: int,
    search_volume: int,
    avg_cpc: str,
) -> CampaignKeyword:
    cluster = db_session.query(KeywordCluster).filter(KeywordCluster.campaign_id == campaign.id).first()
    assert cluster is not None
    keyword = CampaignKeyword(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        cluster_id=cluster.id,
        keyword=keyword_text,
        location_code="US",
        created_at=datetime(2026, 3, 2, 9, 5, tzinfo=UTC),
    )
    db_session.add(keyword)
    db_session.flush()
    db_session.add(
        Ranking(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            keyword_id=keyword.id,
            current_position=position,
            previous_position=position + 1,
            delta=1,
            confidence=0.9,
            updated_at=datetime(2026, 3, 2, 9, 5, tzinfo=UTC),
        )
    )
    db_session.commit()
    market_snapshot_service.upsert_keyword_market_snapshot(
        db_session,
        market_snapshot_service.KeywordMarketSnapshotInput(
            keyword_id=keyword.id,
            search_volume=search_volume,
            avg_cpc=Decimal(avg_cpc),
            geo_scope="US",
            device_class="desktop",
            source_provider="manual",
            snapshot_date=date(2026, 3, 2),
            confidence_score=0.8,
        ),
    )
    metric_input = economics_service.build_keyword_economics_input_from_ranking(
        db_session,
        keyword_id=keyword.id,
        metric_date=date(2026, 3, 2),
    )
    economics_service.upsert_keyword_daily_economics(db_session, metric_input)
    return keyword


def test_campaign_level_aggregations_are_deterministic(db_session) -> None:
    campaign, keyword = _build_keyword_fixture(db_session)
    _seed_snapshot(db_session, keyword.id)
    metric_input = economics_service.build_keyword_economics_input_from_ranking(
        db_session,
        keyword_id=keyword.id,
        metric_date=date(2026, 3, 2),
    )
    economics_service.upsert_keyword_daily_economics(db_session, metric_input)
    second_keyword = _seed_keyword_economics(
        db_session,
        campaign,
        keyword_text="seo opportunity gap",
        position=4,
        search_volume=800,
        avg_cpc="8.00",
    )

    current = economics_service.current_organic_media_value(db_session, campaign.id)
    projected = economics_service.projected_value_if_rank_improves(db_session, campaign.id)
    top_keywords = economics_service.top_keywords_by_value(db_session, campaign.id)
    opportunities = economics_service.highest_opportunity_gap_keywords(db_session, campaign.id)

    assert current["current_value"] == Decimal("944.00")
    assert projected["projected_value"] == Decimal("1268.00")
    assert projected["value_delta"] == Decimal("324.00")
    assert top_keywords[0]["keyword_id"] == second_keyword.id
    assert top_keywords[0]["current_value"] == Decimal("512.00")
    assert opportunities[0]["keyword_id"] == second_keyword.id
    assert opportunities[0]["opportunity_gap"] == Decimal("192.00")


def test_projected_value_for_scenarios_is_bounded_and_deterministic(db_session) -> None:
    campaign, keyword = _build_keyword_fixture(db_session)
    _seed_snapshot(db_session, keyword.id)
    metric_input = economics_service.build_keyword_economics_input_from_ranking(
        db_session,
        keyword_id=keyword.id,
        metric_date=date(2026, 3, 2),
    )
    economics_service.upsert_keyword_daily_economics(db_session, metric_input)
    _seed_keyword_economics(
        db_session,
        campaign,
        keyword_text="seo opportunity gap",
        position=4,
        search_volume=800,
        avg_cpc="8.00",
    )

    conservative = economics_service.projected_value_for_scenario(db_session, campaign.id, economics_service.Scenario.CONSERVATIVE)
    moderate = economics_service.projected_value_for_scenario(db_session, campaign.id, economics_service.Scenario.MODERATE)
    strong = economics_service.projected_value_for_scenario(db_session, campaign.id, economics_service.Scenario.STRONG)
    dominant = economics_service.projected_value_for_scenario(db_session, campaign.id, economics_service.Scenario.DOMINANT)

    assert conservative["projected_value"] == Decimal("1268.00")
    assert conservative["delta"] == Decimal("324.00")
    assert conservative["percentage_lift"] == Decimal("34.32")
    assert moderate["projected_value"] == Decimal("1740.00")
    assert moderate["delta"] == Decimal("796.00")
    assert moderate["percentage_lift"] == Decimal("84.32")
    assert strong["projected_value"] == Decimal("2024.00")
    assert strong["delta"] == Decimal("1080.00")
    assert strong["percentage_lift"] == Decimal("114.41")
    assert dominant["projected_value"] == Decimal("5244.00")
    assert dominant["delta"] == Decimal("4300.00")
    assert dominant["percentage_lift"] == Decimal("455.51")
    assert dominant["confidence_weight"] == Decimal("0.80")
