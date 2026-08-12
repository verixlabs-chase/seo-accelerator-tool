from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.services import competitor_service


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_competitor_crud_snapshots_and_gaps(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Competitor Campaign", "domain": "ownsite.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    create = client.post(
        "/api/v1/competitors",
        json={
            "campaign_id": campaign["id"],
            "domain": "rival.com",
            "label": "Rival One",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 200

    listed = client.get(
        f"/api/v1/competitors?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) == 1
    assert listed.json()["data"]["truth"]["classification"] == "synthetic"

    snapshots = client.get(
        f"/api/v1/competitors/snapshots?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshots.status_code == 200
    assert snapshots.json()["data"]["summary"]["snapshots_collected"] == 1
    assert len(snapshots.json()["data"]["items"]) >= 1
    assert snapshots.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

    gaps = client.get(
        f"/api/v1/competitors/gaps?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gaps.status_code == 200
    assert gaps.json()["data"]["items"] == []
    assert gaps.json()["data"]["truth"]["classification"] == "synthetic"


class FakeCompetitorDiscoveryProvider:
    def competitor_domains(self, **kwargs):  # noqa: ANN003
        assert kwargs["target"] == "ownsite.com"
        return {
            "items": [
                {
                    "domain": "real-rival.com",
                    "intersections": 18,
                    "avg_position": 7.4,
                    "metrics": {"organic": {"etv": 245.8}},
                },
                {"domain": "ownsite.com", "intersections": 99},
                {"domain": "weak-match.com", "intersections": 1},
            ],
            "cost": 0.01,
        }


def test_discovery_requires_owner_confirmation_and_preserves_evidence(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Competitor Discovery", "domain": "ownsite.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    payload = competitor_service.discover_competitors(
        db_session,
        tenant_id=campaign_payload["tenant_id"],
        campaign_id=campaign_payload["id"],
        provider=FakeCompetitorDiscoveryProvider(),
        now=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
    )

    assert payload["suggestions_found"] == 1
    suggestion = next(item for item in payload["items"] if item["domain"] == "real-rival.com")
    assert suggestion["review_status"] == "suggested"
    assert suggestion["overlap_count"] == 18
    assert suggestion["average_position"] == 7.4
    assert all(item["domain"] != "weak-match.com" for item in payload["items"])

    reviewed = competitor_service.review_competitor(
        db_session,
        tenant_id=campaign_payload["tenant_id"],
        campaign_id=campaign_payload["id"],
        competitor_id=suggestion["id"],
        decision="confirmed",
    )
    assert reviewed.review_status == "confirmed"


def test_research_compares_exact_owner_and_competitor_positions(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Competitor Evidence", "domain": "ownsite.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    assert campaign is not None and campaign.organization_id is not None
    competitor = Competitor(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        domain="rival.com",
        label="Local Rival",
        discovery_source="manual",
        review_status="confirmed",
    )
    run = KeywordResearchRun(
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        status="complete",
        location_name="Reno, Nevada, United States",
        sources=["competitor_rankings"],
        warnings=[],
        suggestion_count=1,
        completed_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
    )
    db_session.add_all([competitor, run])
    db_session.flush()
    db_session.add(
        KeywordResearchSuggestion(
            run_id=run.id,
            tenant_id=campaign.tenant_id,
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            business_location_id=campaign.business_location_id,
            keyword="junk removal reno",
            normalized_keyword="junk removal reno",
            source_types=["competitor_rankings"],
            evidence={
                "ranked_url": "https://ownsite.com/junk-removal",
                "competitors": [
                    {
                        "competitor_id": competitor.id,
                        "domain": "rival.com",
                        "label": "Local Rival",
                        "position": 3,
                        "url": "https://rival.com/junk-removal-reno",
                    }
                ],
            },
            search_volume=120,
            current_position=11,
            intent="Ready to hire",
            opportunity_group="new_opportunity",
            relevance_score=95,
            relevance_status="relevant",
            matched_service_name="Junk removal",
            matched_service_area_name="Reno",
            opportunity_score=88,
            recommended_action="Improve this page",
            recommendation_reason="A competitor is ahead.",
            source_updated_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/competitors/research?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["exact_gaps"] == 1
    gap = payload["items"][0]
    assert gap["keyword"] == "junk removal reno"
    assert gap["owner_position"] == 11
    assert gap["competitor_position"] == 3
    assert gap["competitor_url"] == "https://rival.com/junk-removal-reno"
    assert gap["owner_url"] == "https://ownsite.com/junk-removal"
    assert gap["page_status"] == "existing"
    assert "gap_score" not in gap
