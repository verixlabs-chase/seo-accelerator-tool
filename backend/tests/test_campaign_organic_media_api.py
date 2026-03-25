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
    assert payload["legacy_contract"] is True
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
    assert payload["legacy_contract"] is True
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
    assert payload["legacy_contract"] is True
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


def test_campaign_organic_value_baseline_endpoint_returns_normalized_v1_contract(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, _first_keyword, _second_keyword = _seed_campaign_with_economics(db_session)

    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["campaign_id"] == campaign.id
    assert payload["feature"] == "organic_value_roi_baseline_v1"
    assert payload["current_value"]["amount"] == "944.00"
    assert payload["current_value"]["status"] == "available"
    assert payload["upside_opportunity"]["amount"] == "324.00"
    assert payload["roi_baseline"]["status"] == "unavailable"
    assert [row["key"] for row in payload["scenarios"]] == ["conservative", "expected", "aggressive"]
    assert payload["scenarios"][1]["projected_value"] == "1740.00"
    assert payload["scenarios"][1]["roi_baseline"]["status"] == "unavailable"
    assert any(item["source_type"] == "estimated" for item in payload["assumptions"])
    assert any(item["source_type"] == "provider_derived" for item in payload["assumptions"])
    assert any(item["source_type"] == "unavailable" for item in payload["assumptions"])
    assert payload["confidence"]["level"] in {"medium", "high"}
    assert len(payload["caveats"]) >= 3
    assert payload["truth"]["classification"] in {"heuristic", "operator_assisted"}


def test_campaign_organic_value_baseline_endpoint_uses_user_provided_investment_for_ratio(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, _first_keyword, _second_keyword = _seed_campaign_with_economics(db_session)

    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_seo_investment": "500.00"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["roi_baseline"]["status"] == "available"
    assert payload["roi_baseline"]["ratio"] == "1.89"
    assert payload["roi_baseline"]["net_amount"] == "444.00"
    assert payload["assumptions"][1]["source_type"] == "user_provided"
    assert payload["scenarios"][0]["roi_baseline"]["ratio"] == "2.54"
    assert payload["scenarios"][1]["roi_baseline"]["ratio"] == "3.48"


def test_campaign_organic_value_baseline_reads_persisted_assumption_when_request_omits_it(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, _first_keyword, _second_keyword = _seed_campaign_with_economics(db_session)

    first = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_seo_investment": "750.00"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert second.status_code == 200
    payload = second.json()["data"]
    assert payload["roi_baseline"]["status"] == "available"
    assert payload["roi_baseline"]["ratio"] == "1.26"
    assert payload["assumptions"][1]["value"] == "750.00"
    assert payload["assumptions"][1]["source_type"] == "user_provided"


def test_campaign_organic_value_baseline_can_clear_persisted_assumption(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, _first_keyword, _second_keyword = _seed_campaign_with_economics(db_session)

    saved = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_seo_investment": "500.00"},
    )
    assert saved.status_code == 200

    cleared = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={"clear_monthly_seo_investment": True},
    )

    assert cleared.status_code == 200
    payload = cleared.json()["data"]
    assert payload["roi_baseline"]["status"] == "unavailable"
    assert payload["assumptions"][1]["status"] == "unavailable"
    assert payload["assumptions"][1]["value"] is None


def test_legacy_organic_media_routes_keep_shape_after_unified_service_persistence(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    campaign, first_keyword, second_keyword = _seed_campaign_with_economics(db_session)

    baseline = client.post(
        f"/api/v1/campaigns/{campaign.id}/organic-value-baseline",
        headers={"Authorization": f"Bearer {token}"},
        json={"monthly_seo_investment": "1200.00"},
    )
    assert baseline.status_code == 200

    value_response = client.get(
        f"/api/v1/campaigns/{campaign.id}/organic-media-value",
        headers={"Authorization": f"Bearer {token}"},
    )
    opportunity_response = client.get(
        f"/api/v1/campaigns/{campaign.id}/organic-media-opportunity",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert value_response.status_code == 200
    assert opportunity_response.status_code == 200
    value_payload = value_response.json()["data"]
    opportunity_payload = opportunity_response.json()["data"]
    assert value_payload["current_value"] == "944.00"
    assert value_payload["projected_value"] == "1268.00"
    assert [row["keyword_id"] for row in value_payload["top_keywords_by_value"]] == [second_keyword.id, first_keyword.id]
    assert opportunity_payload["value_delta"] == "324.00"
    assert [row["keyword_id"] for row in opportunity_payload["opportunity_keywords"]] == [second_keyword.id, first_keyword.id]
