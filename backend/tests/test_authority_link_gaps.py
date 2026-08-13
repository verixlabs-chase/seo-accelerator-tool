from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.intelligence.lexicon import get_builtin_lexicon
from app.models.authority import AuthorityLinkChange, AuthorityLinkChangeRun
from app.models.campaign import Campaign
from app.models.business_location import BusinessLocation
from app.models.business_service import BusinessService
from app.models.business_service_area import BusinessServiceArea
from app.models.competitor import Competitor
from app.models.intelligence import StrategyRecommendation
from app.providers.authority import DataForSeoAuthorityProvider
from app.services import action_plan_measurement_service, authority_service


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


class FakeAuthorityGapProvider:
    def __init__(self) -> None:
        self.calls = 0

    def page_intersection(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        assert kwargs == {
            "targets": ["other-rival.com", "rival.com"],
            "exclude_target": "ownsite.com",
            "limit": 25,
        }
        return {
            "cost": Decimal("0.024108"),
            "items": [
                {
                    "page_intersection": {
                        "1": [
                            {
                                "domain_from": "reno-chamber.org",
                                "url_from": "https://reno-chamber.org/member-resources",
                                "page_from_title": "Reno junk removal member resources",
                                "url_to": "https://other-rival.com/community",
                                "item_type": "anchor",
                                "dofollow": True,
                                "anchor": "local service partners",
                                "first_seen": "2026-01-10 08:00:00 +00:00",
                                "last_seen": "2026-08-12 08:00:00 +00:00",
                                "is_lost": False,
                            }
                        ],
                        "2": [
                            {
                                "domain_from": "reno-chamber.org",
                                "url_from": "https://reno-chamber.org/member-resources",
                                "page_from_title": "Reno junk removal member resources",
                                "url_to": "https://rival.com/community",
                                "item_type": "anchor",
                                "dofollow": True,
                                "anchor": "local service partners",
                                "first_seen": "2026-02-10 08:00:00 +00:00",
                                "last_seen": "2026-08-11 08:00:00 +00:00",
                                "is_lost": False,
                            }
                        ],
                    }
                }
            ],
        }


def test_authority_gap_refresh_saves_exact_pages_and_is_idempotent(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Authority Gap", "domain": "https://www.ownsite.com/"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    assert campaign is not None and campaign.organization_id is not None
    location = BusinessLocation(
        organization_id=campaign.organization_id,
        name="Reno",
        domain="ownsite.com",
        primary_city="Reno",
        city="Reno",
        region="NV",
    )
    db_session.add(location)
    db_session.flush()
    campaign.business_location_id = location.id
    db_session.add_all(
        [
            BusinessService(
                tenant_id=campaign.tenant_id,
                organization_id=campaign.organization_id,
                business_location_id=location.id,
                scope_type="location",
                scope_key=location.id,
                name="Junk removal",
                normalized_name="junk removal",
                aliases=["junk hauling"],
                status="confirmed",
                source="manual",
                confidence=1.0,
            ),
            BusinessServiceArea(
                tenant_id=campaign.tenant_id,
                organization_id=campaign.organization_id,
                business_location_id=location.id,
                area_type="city",
                name="Reno",
                normalized_name="reno",
                region="NV",
                relationship="included",
                status="confirmed",
                source="manual",
                confidence=1.0,
            ),
            Competitor(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                domain="rival.com",
                label="Rival",
                discovery_source="manual",
                review_status="confirmed",
            ),
            Competitor(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                domain="other-rival.com",
                label="Other Rival",
                discovery_source="manual",
                review_status="confirmed",
            ),
        ]
    )
    db_session.commit()

    provider = FakeAuthorityGapProvider()
    created = authority_service.refresh_authority_link_gaps(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        idempotency_key="authority-gap-2026-08-12",
        provider=provider,
        now=datetime(2026, 8, 12, 18, 0, tzinfo=UTC),
    )
    assert created["created"] is True
    assert created["summary"] == {
        "exact_pages": 1,
        "referring_domains": 1,
        "competitors_compared": 2,
        "service_and_area_matches": 1,
        "service_matches": 0,
        "area_matches": 0,
        "needs_review": 0,
    }
    gap = created["items"][0]
    assert gap["referring_domain"] == "reno-chamber.org"
    assert gap["source_url"] == "https://reno-chamber.org/member-resources"
    assert gap["competitor_match_count"] == 2
    assert {item["target_url"] for item in gap["competitor_matches"]} == {
        "https://other-rival.com/community",
        "https://rival.com/community",
    }
    assert gap["first_seen_at"] == "2026-01-10T08:00:00+00:00"
    assert gap["last_seen_at"] == "2026-08-12T08:00:00+00:00"
    assert gap["relevance_classification"] == "service_and_area_match"
    assert gap["matched_services"][0]["name"] == "Junk removal"
    assert gap["matched_service_areas"][0]["name"] == "Reno"
    assert "score" not in gap

    action_response = client.post(
        "/api/v1/authority/actions",
        json={
            "campaign_id": campaign.id,
            "source_type": "competitor_gap",
            "source_id": gap["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert action_response.status_code == 200
    action_payload = action_response.json()["data"]
    assert action_payload["created"] is True
    assert action_payload["item"]["action_id"] == "authority.build_relevant_mention"
    recommendation = db_session.get(StrategyRecommendation, action_payload["item"]["id"])
    assert recommendation is not None
    evidence = __import__("json").loads(recommendation.evidence_json)
    assert evidence["measurement_contract"] == {
        "metric_id": "authority.referring_page_link_present",
        "plain_language": "Whether this exact page links to the business website.",
        "source_url": gap["source_url"],
        "owner_domain": "ownsite.com",
        "baseline": 0,
        "target": 1,
        "direction": "higher_is_better",
        "check": "Run a fresh website-mention check after the follow-up.",
    }
    listed_recommendations = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed_recommendations.status_code == 200
    action_item = next(
        item
        for item in listed_recommendations.json()["data"]["items"]
        if item["id"] == recommendation.id
    )
    assert action_item["action_plan"]["action_id"] == "authority.build_relevant_mention"
    assert action_item["action_plan"]["success_metric_ids"] == [
        "authority.referring_page_link_present"
    ]
    assert action_item["action_plan"]["work_item"]["action_id"] == (
        "authority.build_relevant_mention"
    )
    outreach_response = client.post(
        "/api/v1/authority/outreach-drafts",
        json={
            "campaign_id": campaign.id,
            "source_type": "competitor_gap",
            "source_id": gap["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert outreach_response.status_code == 200
    outreach_payload = outreach_response.json()["data"]
    assert outreach_payload["created"] is True
    outreach = outreach_payload["item"]
    assert outreach["status"] == "draft"
    assert outreach["contact_email"] is None
    assert outreach["manual_send_only"] is True
    assert outreach["send_available"] is False
    assert "Junk removal" in outreach["message_body"]
    assert "Reno" in outreach["message_body"]
    assert "promise" not in outreach["message_body"].lower()

    duplicate_outreach = client.post(
        "/api/v1/authority/outreach-drafts",
        json={
            "campaign_id": campaign.id,
            "source_type": "competitor_gap",
            "source_id": gap["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert duplicate_outreach.status_code == 200
    assert duplicate_outreach.json()["data"]["created"] is False
    assert duplicate_outreach.json()["data"]["item"]["id"] == outreach["id"]

    unconfirmed_review = client.patch(
        f"/api/v1/authority/outreach-drafts/{outreach['id']}",
        json={
            "campaign_id": campaign.id,
            "subject": outreach["subject"],
            "message_body": outreach["message_body"],
            "status": "reviewed",
            "owner_confirmed_recipient": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unconfirmed_review.status_code == 409

    reviewed_response = client.patch(
        f"/api/v1/authority/outreach-drafts/{outreach['id']}",
        json={
            "campaign_id": campaign.id,
            "contact_name": "Website owner",
            "contact_page_url": "https://reno-chamber.org/contact",
            "subject": outreach["subject"],
            "message_body": outreach["message_body"],
            "status": "reviewed",
            "owner_confirmed_recipient": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed_response.status_code == 200
    reviewed = reviewed_response.json()["data"]["item"]
    assert reviewed["status"] == "reviewed"
    assert reviewed["status_label"] == "Ready for you to send"
    assert reviewed["send_available"] is False

    outreach_list = client.get(
        f"/api/v1/authority/outreach-drafts?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert outreach_list.status_code == 200
    assert outreach_list.json()["data"]["summary"] == {
        "drafts": 0,
        "reviewed": 1,
        "closed": 0,
    }
    assert "dataforseo" not in str(outreach_list.json()).lower()
    metric = get_builtin_lexicon().metric_index["authority.referring_page_link_present"]
    baseline = action_plan_measurement_service._authority_link_presence_metric(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        metric=metric,
        captured_at=datetime(2026, 8, 12, 18, 5, tzinfo=UTC),
        evidence_payload=evidence,
    )
    assert baseline["status"] == "available"
    assert baseline["value"] == 0

    change_run = AuthorityLinkChangeRun(
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        idempotency_key="authority-measurement-after-follow-up",
        status="complete",
        owner_domain="ownsite.com",
        result_limit_per_state=12,
        source_kind="live_link_index",
        new_count=1,
        lost_count=0,
        observed_at=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
        created_at=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
    )
    db_session.add(change_run)
    db_session.flush()
    restored = AuthorityLinkChange(
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        run_id=change_run.id,
        change_state="new",
        referring_domain=gap["referring_domain"],
        source_url=gap["source_url"],
        source_page_title=gap["source_page_title"],
        target_url="https://ownsite.com/",
        link_type="anchor",
        dofollow=True,
        anchor="junk removal",
        first_seen_at=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
        observed_at=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
        evidence={"source_type": "live_link_index", "reported_state": "new"},
    )
    db_session.add(restored)
    db_session.commit()
    outcome = action_plan_measurement_service._authority_link_presence_metric(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        metric=metric,
        captured_at=datetime(2026, 8, 12, 19, 5, tzinfo=UTC),
        evidence_payload=evidence,
    )
    assert outcome["status"] == "available"
    assert outcome["value"] == 1
    assert outcome["source_record_id"] == restored.id
    duplicate_action = client.post(
        "/api/v1/authority/actions",
        json={
            "campaign_id": campaign.id,
            "source_type": "competitor_gap",
            "source_id": gap["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert duplicate_action.status_code == 200
    assert duplicate_action.json()["data"]["created"] is False

    replay = authority_service.refresh_authority_link_gaps(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        idempotency_key="authority-gap-2026-08-12",
        provider=provider,
    )
    assert replay["created"] is False
    assert replay["run"]["id"] == created["run"]["id"]
    assert provider.calls == 1

    response = client.get(
        f"/api/v1/authority/link-gaps?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["truth"]["classification"] == "provider_backed"
    assert payload["items"][0]["source_url"] == gap["source_url"]
    assert "dataforseo" not in str(payload).lower()


def test_authority_provider_uses_bounded_page_intersection_request() -> None:
    observed: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["payload"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "cost": 0.024036,
                        "result": [
                            {
                                "items": [
                                    {
                                        "page_intersection": {
                                            "1": [
                                                {
                                                    "domain_from": "example.org",
                                                    "url_from": "https://example.org/resources",
                                                    "url_to": "https://rival.com/",
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DataForSeoAuthorityProvider(login="login", password="password", client=client)
    result = provider.page_intersection(
        targets=["rival.com"],
        exclude_target="ownsite.com",
        limit=25,
    )
    assert result["cost"] == Decimal("0.024036")
    assert len(result["items"]) == 1
    assert observed["url"].endswith("/v3/backlinks/page_intersection/live")
    task = observed["payload"][0]
    assert task["targets"] == {"1": "rival.com"}
    assert task["exclude_targets"] == ["ownsite.com"]
    assert task["limit"] == 25
    assert task["backlinks_status_type"] == "live"


class FakeAuthorityLinkChangeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def backlink_changes(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        assert kwargs == {"target": "ownsite.com", "limit_per_state": 12}
        return {
            "cost": Decimal("0.048072"),
            "new_items": [
                {
                    "domain_from": "reno-neighbors.org",
                    "url_from": "https://reno-neighbors.org/recommended-services",
                    "page_from_title": "Recommended local services",
                    "url_to": "https://ownsite.com/junk-removal",
                    "item_type": "anchor",
                    "dofollow": True,
                    "anchor": "junk removal",
                    "first_seen": "2026-08-10 10:00:00 +00:00",
                    "last_seen": "2026-08-12 10:00:00 +00:00",
                    "is_new": True,
                    "is_lost": False,
                }
            ],
            "lost_items": [
                {
                    "domain_from": "old-partner.org",
                    "url_from": "https://old-partner.org/resources",
                    "page_from_title": "Community resources",
                    "url_to": "https://ownsite.com/",
                    "item_type": "anchor",
                    "dofollow": False,
                    "anchor": "local service",
                    "first_seen": "2025-01-10 10:00:00 +00:00",
                    "last_seen": "2026-08-01 10:00:00 +00:00",
                    "is_new": False,
                    "is_lost": True,
                }
            ],
        }


def test_authority_link_changes_save_explicit_new_and_lost_evidence(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Owner Link History", "domain": "https://www.ownsite.com/"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    assert campaign is not None and campaign.organization_id is not None

    provider = FakeAuthorityLinkChangeProvider()
    created = authority_service.refresh_authority_link_changes(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        idempotency_key="authority-link-changes-2026-08-12",
        provider=provider,
        now=datetime(2026, 8, 12, 19, 0, tzinfo=UTC),
    )
    assert created["created"] is True
    assert created["summary"] == {
        "new_links": 1,
        "lost_links": 1,
        "new_websites": 1,
        "lost_websites": 1,
    }
    assert created["new_items"][0]["source_url"].endswith("/recommended-services")
    assert created["new_items"][0]["change_state"] == "new"
    assert created["lost_items"][0]["change_state"] == "lost"
    assert created["lost_items"][0]["target_url"] == "https://ownsite.com/"
    assert "verification_goal" in created["lost_items"][0]

    action_response = client.post(
        "/api/v1/authority/actions",
        json={
            "campaign_id": campaign.id,
            "source_type": "lost_link",
            "source_id": created["lost_items"][0]["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert action_response.status_code == 200
    assert action_response.json()["data"]["created"] is True
    assert action_response.json()["data"]["item"]["action_id"] == "authority.restore_lost_link"

    replay = authority_service.refresh_authority_link_changes(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        idempotency_key="authority-link-changes-2026-08-12",
        provider=provider,
    )
    assert replay["created"] is False
    assert replay["run"]["id"] == created["run"]["id"]
    assert provider.calls == 1

    response = client.get(
        f"/api/v1/authority/link-changes?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["new_links"] == 1
    assert payload["summary"]["lost_links"] == 1
    assert "dataforseo" not in str(payload).lower()


def test_authority_provider_requests_bounded_new_and_lost_owner_links() -> None:
    observed: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content.decode("utf-8"))
        observed.append(payload[0])
        state = payload[0]["backlinks_status_type"]
        item = {
            "domain_from": "example.org",
            "url_from": f"https://example.org/{state}",
            "url_to": "https://ownsite.com/",
            "is_new": state == "live",
            "is_lost": state == "lost",
        }
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "cost": 0.024036,
                        "result": [{"items": [item]}],
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DataForSeoAuthorityProvider(login="login", password="password", client=client)
    result = provider.backlink_changes(target="ownsite.com", limit_per_state=12)
    assert result["cost"] == Decimal("0.048072")
    assert len(result["new_items"]) == 1
    assert len(result["lost_items"]) == 1
    assert [task["backlinks_status_type"] for task in observed] == ["live", "lost"]
    assert all(task["target"] == "ownsite.com" for task in observed)
    assert all(task["mode"] == "one_per_domain" for task in observed)
    assert all(task["limit"] == 12 for task in observed)
    assert observed[0]["filters"] == ["is_new", "=", True]


class FakeAuthorityInventoryProvider:
    def __init__(self) -> None:
        self.calls = 0

    def authority_inventory(self, **kwargs):  # noqa: ANN003
        self.calls += 1
        assert kwargs == {
            "target": "ownsite.com",
            "business_name": "Own Site",
            "link_limit": 50,
            "mention_limit": 10,
        }
        return {
            "cost": Decimal("0.073"),
            "link_items": [
                {
                    "domain_from": "reno-community.org",
                    "url_from": "https://reno-community.org/partners",
                    "page_from_title": "Reno community partners",
                    "url_to": "https://ownsite.com/junk-removal",
                    "item_type": "anchor",
                    "dofollow": True,
                    "anchor": "Own Site junk removal",
                    "first_seen": "2026-06-01 10:00:00 +00:00",
                    "last_seen": "2026-08-12 10:00:00 +00:00",
                    "is_lost": False,
                }
            ],
            "mention_items": [
                {
                    "main_domain": "reno-guide.org",
                    "url": "https://reno-guide.org/junk-removal-options",
                    "title": "Reno junk removal guide",
                    "snippet": "Own Site provides junk removal in Reno.",
                },
                {
                    "main_domain": "linked-guide.org",
                    "url": "https://linked-guide.org/local-services",
                    "title": "Local services featuring Own Site",
                    "snippet": "Own Site is listed here.",
                },
            ],
            "mention_link_items": [
                {
                    "domain_from": "linked-guide.org",
                    "url_from": "https://linked-guide.org/local-services",
                    "url_to": "https://ownsite.com/",
                    "is_lost": False,
                }
            ],
        }


def test_authority_inventory_saves_links_and_only_same_run_verified_unlinked_mentions(
    client, db_session
):
    token = _login(client, "a@example.com", "pass-a")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Own Site", "domain": "https://www.ownsite.com/"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    assert campaign is not None and campaign.organization_id is not None
    location = BusinessLocation(
        organization_id=campaign.organization_id,
        name="Own Site Reno",
        domain="ownsite.com",
        primary_city="Reno",
        city="Reno",
        region="NV",
    )
    db_session.add(location)
    db_session.flush()
    campaign.business_location_id = location.id
    db_session.add_all(
        [
            BusinessService(
                tenant_id=campaign.tenant_id,
                organization_id=campaign.organization_id,
                business_location_id=location.id,
                scope_type="location",
                scope_key=location.id,
                name="Junk removal",
                normalized_name="junk removal",
                aliases=[],
                status="confirmed",
                source="manual",
                confidence=1.0,
            ),
            BusinessServiceArea(
                tenant_id=campaign.tenant_id,
                organization_id=campaign.organization_id,
                business_location_id=location.id,
                area_type="city",
                name="Reno",
                normalized_name="reno",
                region="NV",
                relationship="included",
                status="confirmed",
                source="manual",
                confidence=1.0,
            ),
        ]
    )
    db_session.commit()

    provider = FakeAuthorityInventoryProvider()
    created = authority_service.refresh_authority_inventory(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_name="  Own   Site  ",
        idempotency_key="authority-inventory-2026-08-12",
        provider=provider,
        now=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
    )
    assert created["created"] is True
    assert created["summary"] == {
        "incoming_links": 1,
        "linking_websites": 1,
        "exact_name_pages_checked": 2,
        "unlinked_mentions": 1,
    }
    assert created["links"][0]["source_url"].endswith("/partners")
    mention = created["unlinked_mentions"][0]
    assert mention["source_url"] == "https://reno-guide.org/junk-removal-options"
    assert mention["relevance_classification"] == "service_and_area_match"
    assert "no website link found" in mention["status_label"].lower()
    assert "linked-guide.org" not in str(created["unlinked_mentions"])
    assert "dataforseo" not in str(created).lower()

    action_response = client.post(
        "/api/v1/authority/actions",
        json={
            "campaign_id": campaign.id,
            "source_type": "unlinked_mention",
            "source_id": mention["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert action_response.status_code == 200
    assert action_response.json()["data"]["item"]["action_id"] == (
        "authority.build_relevant_mention"
    )
    outreach_response = client.post(
        "/api/v1/authority/outreach-drafts",
        json={
            "campaign_id": campaign.id,
            "source_type": "unlinked_mention",
            "source_id": mention["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert outreach_response.status_code == 200
    outreach = outreach_response.json()["data"]["item"]
    assert outreach["manual_send_only"] is True
    assert "thank you for including" in outreach["message_body"].lower()

    replay = authority_service.refresh_authority_inventory(
        db_session,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_name="Own Site",
        idempotency_key="authority-inventory-2026-08-12",
        provider=provider,
    )
    assert replay["created"] is False
    assert replay["run"]["id"] == created["run"]["id"]
    assert provider.calls == 1


def test_authority_provider_inventory_uses_bounded_exact_name_and_same_url_link_check() -> None:
    observed: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        task = __import__("json").loads(request.content.decode("utf-8"))[0]
        observed.append((request.url.path, task))
        if request.url.path.endswith("/content_analysis/search/live"):
            items = [
                {
                    "main_domain": "example.org",
                    "url": "https://example.org/own-site",
                    "title": "Own Site",
                    "snippet": "Own Site serves Reno.",
                }
            ]
        else:
            items = []
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "cost": 0.024,
                        "result": [{"items": items}],
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DataForSeoAuthorityProvider(login="login", password="password", client=client)
    result = provider.authority_inventory(
        target="ownsite.com",
        business_name="Own Site",
        link_limit=50,
        mention_limit=10,
    )
    assert result["cost"] == Decimal("0.072")
    assert len(observed) == 3
    inventory_task = observed[0][1]
    mention_task = observed[1][1]
    verification_task = observed[2][1]
    assert inventory_task["mode"] == "one_per_domain"
    assert inventory_task["limit"] == 50
    assert mention_task["keyword"] == '"Own Site"'
    assert mention_task["search_mode"] == "one_per_domain"
    assert mention_task["limit"] == 10
    assert verification_task["mode"] == "as_is"
    assert verification_task["filters"] == [
        "url_from",
        "in",
        ["https://example.org/own-site"],
    ]
