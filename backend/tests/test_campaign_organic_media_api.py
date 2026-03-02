from datetime import UTC, date, datetime
from decimal import Decimal
import uuid

from app.models.campaign import Campaign
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking
from app.models.user import User
from app.services import economics_service, market_snapshot_service


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _seed_campaign_with_economics(db_session) -> tuple[Campaign, CampaignKeyword, CampaignKeyword]:
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name="Organic Value Campaign",
        domain="value.example",
        created_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    db_session.add(campaign)
    db_session.flush()
    cluster = KeywordCluster(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        name="Value Cluster",
        created_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
    )
    db_session.add(cluster)
    db_session.flush()

    keyword_specs = [
        ("organic media value", 7, 1000, "12.00"),
        ("seo opportunity gap", 4, 800, "8.00"),
    ]
    created_keywords: list[CampaignKeyword] = []
    for keyword_text, position, search_volume, avg_cpc in keyword_specs:
        keyword = CampaignKeyword(
            tenant_id=user.tenant_id,
            campaign_id=campaign.id,
            cluster_id=cluster.id,
            keyword=keyword_text,
            location_code="US",
            created_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
        )
        db_session.add(keyword)
        db_session.flush()
        db_session.add(
            Ranking(
                tenant_id=user.tenant_id,
                campaign_id=campaign.id,
                keyword_id=keyword.id,
                current_position=position,
                previous_position=position + 1,
                delta=1,
                confidence=0.9,
                updated_at=datetime(2026, 3, 2, 10, 0, tzinfo=UTC),
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
        created_keywords.append(keyword)

    return campaign, created_keywords[0], created_keywords[1]


def test_campaign_organic_media_value_endpoint_returns_db_backed_aggregation(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, first_keyword, second_keyword = _seed_campaign_with_economics(db_session)

    response = client.get(
        f"/api/v1/campaigns/{campaign.id}/organic-media-value",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["campaign_id"] == campaign.id
    assert payload["current_value"] == "944.00"
    assert payload["projected_value"] == "1268.00"
    assert payload["value_delta"] == "324.00"
    assert payload["keyword_count"] == 2
    assert payload["as_of"] == "2026-03-02"
    assert [row["keyword_id"] for row in payload["top_keywords_by_value"]] == [second_keyword.id, first_keyword.id]


def test_campaign_organic_media_opportunity_endpoint_returns_keyword_gaps(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, first_keyword, second_keyword = _seed_campaign_with_economics(db_session)

    response = client.get(
        f"/api/v1/campaigns/{campaign.id}/organic-media-opportunity",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["campaign_id"] == campaign.id
    assert payload["current_value"] == "944.00"
    assert payload["projected_value"] == "1268.00"
    assert payload["value_delta"] == "324.00"
    assert payload["keyword_count"] == 2
    assert [row["keyword_id"] for row in payload["opportunity_keywords"]] == [second_keyword.id, first_keyword.id]
    assert payload["opportunity_keywords"][0]["opportunity_gap"] == "192.00"
    assert payload["opportunity_keywords"][1]["opportunity_gap"] == "132.00"

def test_campaign_organic_media_scenarios_endpoint_returns_bounded_projections(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, _first_keyword, _second_keyword = _seed_campaign_with_economics(db_session)

    response = client.get(
        f"/api/v1/campaigns/{campaign.id}/organic-media-scenarios",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["campaign_id"] == campaign.id
    assert payload["current_value"] == "944.00"
    assert payload["keyword_count"] == 2
    assert payload["as_of"] == "2026-03-02"
    assert payload["scenarios"] == [
        {
            "scenario": "CONSERVATIVE",
            "projected_value": "1268.00",
            "delta": "324.00",
            "percentage_lift": "34.32",
            "confidence_weight": "0.80",
        },
        {
            "scenario": "MODERATE",
            "projected_value": "1740.00",
            "delta": "796.00",
            "percentage_lift": "84.32",
            "confidence_weight": "0.80",
        },
        {
            "scenario": "STRONG",
            "projected_value": "2024.00",
            "delta": "1080.00",
            "percentage_lift": "114.41",
            "confidence_weight": "0.80",
        },
        {
            "scenario": "DOMINANT",
            "projected_value": "5244.00",
            "delta": "4300.00",
            "percentage_lift": "455.51",
            "confidence_weight": "0.80",
        },
    ]
