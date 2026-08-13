import uuid

from app.models.audit_log import AuditLog
from app.models.authority import DirectoryListing, DirectoryListingObservation
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.migration_import import MigrationImportBatch, MigrationImportRecord
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def test_migration_csv_dry_run_matches_locations_and_writes_nothing(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    created = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Reno Local SEO", "domain": "junkmagiciansnv.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    before_count = (
        db_session.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == org_id)
        .count()
    )

    csv_text = """Record Type,Location Name,Website,City,State,Country,Keyword,Group,Competitor
location,Reno Local SEO,https://junkmagiciansnv.com/,Reno,NV,US,,,
location,Lexington Local SEO,lexington-junk.example,Lexington,KY,US,,,
keyword,Lexington Local SEO,,,,,junk removal lexington,Core service,
keyword,Lexington Local SEO,,,,,junk removal lexington,Duplicate,
competitor,Lexington Local SEO,,,,,,,competitor.example
keyword,Missing Location,,,,,appliance removal,Core service,
"""
    response = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "brightlocal", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["mode"] == "dry_run"
    assert len(payload["review_hash"]) == 64
    assert len(payload["source_sha256"]) == 64
    assert payload["writes_performed"] == 0
    assert payload["summary"] == {
        "total_rows": 6,
        "ready": 3,
        "already_saved": 1,
        "duplicates_in_file": 1,
        "needs_attention": 1,
        "locations": 2,
        "keywords": 3,
        "competitors": 1,
        "ranking_history": 0,
        "listing_history": 0,
    }
    assert payload["field_mapping"]["phrase"] == "Keyword"
    assert payload["rows"][0]["status"] == "already_saved"
    assert payload["rows"][0]["matched_location_name"] == "Reno Local SEO"
    assert payload["rows"][3]["status"] == "duplicate"
    assert payload["rows"][5]["status"] == "needs_attention"
    assert payload["rows"][5]["issues"][0]["code"] == "location_reference_missing"
    assert (
        db_session.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == org_id)
        .count()
        == before_count
    )


def test_migration_csv_dry_run_rejects_missing_required_headers(client) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")

    response = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "other", "csv_text": "Keyword,Website\njunk removal,example.com\n"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "migration_required_headers_missing"


def test_migration_csv_dry_run_respects_organization_scope(client) -> None:
    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    _token_b, org_b = _login(client, "b@example.com", "pass-b")

    response = client.post(
        f"/api/v1/organizations/{org_b}/migration-imports/dry-run",
        json={
            "source_system": "semrush",
            "csv_text": "Record Type,Location Name,Website\nlocation,Other Org,example.com\n",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 403
    assert response.json()["errors"][0]["details"]["reason_code"] == "organization_scope_mismatch"


def test_confirmed_migration_is_atomic_idempotent_and_rollbackable(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = """Record Type,Location Name,Website,City,State,Country,Keyword,Group,Competitor
location,Lexington Office,lexington-junk.example,Lexington,KY,US,,,
keyword,Lexington Office,,,,,junk removal lexington,Core service,
competitor,Lexington Office,,,,,,,competitor.example
"""
    reviewed = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "other", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed.status_code == 200
    review = reviewed.json()["data"]
    request_id = str(uuid.uuid4())
    body = {
        "source_system": "other",
        "source_filename": "legacy-setup.csv",
        "csv_text": csv_text,
        "review_hash": review["review_hash"],
        "client_request_id": request_id,
        "confirmed": True,
    }

    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    batch = applied.json()["data"]["batch"]
    assert batch["status"] == "applied"
    assert batch["summary"]["records_applied"] == 3
    assert batch["summary"]["locations_created"] == 1
    assert batch["summary"]["keywords_created"] == 1
    assert batch["summary"]["competitors_created"] == 1
    assert [record["status"] for record in batch["records"]] == ["applied"] * 3

    db_session.expire_all()
    assert db_session.query(MigrationImportBatch).filter_by(id=batch["id"]).count() == 1
    assert db_session.query(MigrationImportRecord).filter_by(batch_id=batch["id"]).count() == 3
    assert db_session.query(BusinessLocation).filter_by(organization_id=org_id).count() == 1
    assert db_session.query(Campaign).filter_by(organization_id=org_id).count() == 1
    assert db_session.query(KeywordCluster).filter_by(tenant_id=org_id).count() == 1
    assert db_session.query(CampaignKeyword).filter_by(tenant_id=org_id).count() == 1
    assert db_session.query(Competitor).filter_by(tenant_id=org_id).count() == 1
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.tenant_id == org_id,
            AuditLog.event_type == "migration.import.applied",
        )
        .count()
        == 1
    )

    retried = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retried.status_code == 200
    assert retried.json()["data"]["batch"]["id"] == batch["id"]
    db_session.expire_all()
    assert db_session.query(BusinessLocation).filter_by(organization_id=org_id).count() == 1

    history = client.get(
        f"/api/v1/organizations/{org_id}/migration-imports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.json()["data"]["items"][0]["id"] == batch["id"]

    rolled_back = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/{batch['id']}/rollback",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["data"]["batch"]["status"] == "rolled_back"
    db_session.expire_all()
    assert db_session.query(BusinessLocation).filter_by(organization_id=org_id).count() == 0
    assert db_session.query(Campaign).filter_by(organization_id=org_id).count() == 0
    assert db_session.query(CampaignKeyword).filter_by(tenant_id=org_id).count() == 0
    assert db_session.query(Competitor).filter_by(tenant_id=org_id).count() == 0
    assert db_session.query(MigrationImportBatch).filter_by(id=batch["id"]).one().status == "rolled_back"


def test_migration_rollback_refuses_to_delete_newer_rank_data(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = """Record Type,Location Name,Website,Keyword,Group
location,Reno Office,reno-junk.example,,
keyword,Reno Office,,junk removal reno,Core service
"""
    reviewed = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "other", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json={
            "source_system": "other",
            "csv_text": csv_text,
            "review_hash": reviewed["review_hash"],
            "client_request_id": str(uuid.uuid4()),
            "confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    batch_id = applied.json()["data"]["batch"]["id"]
    db_session.expire_all()
    keyword = db_session.query(CampaignKeyword).filter_by(tenant_id=org_id).one()
    db_session.add(
        Ranking(
            tenant_id=org_id,
            campaign_id=keyword.campaign_id,
            keyword_id=keyword.id,
            current_position=8,
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/{batch_id}/rollback",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert (
        response.json()["errors"][0]["details"]["reason_code"]
        == "migration_rollback_blocked_by_new_work"
    )
    db_session.expire_all()
    assert db_session.query(CampaignKeyword).filter_by(id=keyword.id).count() == 1
    assert db_session.query(MigrationImportBatch).filter_by(id=batch_id).one().status == "applied"


def test_migration_imports_qualified_ranking_history_and_reports_ignored_columns(
    client,
    db_session,
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = """Record Type,Location Name,Website,Keyword,Group,Position,Captured At,Original ID,Estimated Traffic
location,Reno History,reno-history.example,,,,,,
keyword,Reno History,,junk removal reno,Core service,,,,
ranking,Reno History,,junk removal reno,,12,2026-07-31,old-rank-17,340
"""
    reviewed_response = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "semrush", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed_response.status_code == 200
    review = reviewed_response.json()["data"]
    assert review["summary"]["ready"] == 3
    assert review["summary"]["ranking_history"] == 1
    assert review["ignored_columns"] == [
        {
            "column": "Estimated Traffic",
            "populated_rows": 1,
            "reason": "This column is not supported by the current importer.",
        }
    ]

    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json={
            "source_system": "semrush",
            "source_filename": "ranking-history.csv",
            "csv_text": csv_text,
            "review_hash": review["review_hash"],
            "client_request_id": str(uuid.uuid4()),
            "confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    batch = applied.json()["data"]["batch"]
    assert batch["summary"]["ranking_history_created"] == 1
    db_session.expire_all()
    snapshot = db_session.query(RankingSnapshot).filter_by(tenant_id=org_id).one()
    assert snapshot.position == 12
    assert snapshot.captured_at.date().isoformat() == "2026-07-31"
    assert snapshot.month_partition == "2026-07"
    assert snapshot.source_type == "imported"
    assert snapshot.source_system == "semrush"
    assert snapshot.source_record_id == "old-rank-17"
    assert snapshot.import_batch_id == batch["id"]
    assert db_session.query(Ranking).filter_by(tenant_id=org_id).count() == 0

    campaign = db_session.query(Campaign).filter_by(organization_id=org_id).one()
    snapshots_response = client.get(
        f"/api/v1/rank/snapshots?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshots_response.status_code == 200
    snapshots_payload = snapshots_response.json()["data"]
    assert snapshots_payload["imported_history_count"] == 1
    assert snapshots_payload["items"][0]["source_type"] == "imported"
    assert snapshots_payload["items"][0]["import_batch_id"] == batch["id"]
    assert snapshots_payload["truth"]["freshness_state"] == "unknown"

    report_readiness = client.get(
        f"/api/v1/reports/readiness?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert report_readiness.status_code == 200
    rank_source = next(
        item
        for item in report_readiness.json()["data"]["sources"]
        if item["key"] == "rank_tracking"
    )
    assert rank_source["state"] == "partial"
    assert rank_source["last_updated"] is None

    reviewed_again = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "semrush", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed_again.status_code == 200
    statuses = [row["status"] for row in reviewed_again.json()["data"]["rows"]]
    assert statuses == ["already_saved", "already_saved", "already_saved"]

    rolled_back = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/{batch['id']}/rollback",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rolled_back.status_code == 200
    db_session.expire_all()
    assert db_session.query(RankingSnapshot).filter_by(import_batch_id=batch["id"]).count() == 0


def test_migration_imports_listing_history_without_claiming_fresh_verification(
    client,
    db_session,
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = """Record Type,Location Name,Website,City,State,Country,Directory Name,Listing URL,Listing Status,Listing Business Name,Listing Address,Listing City,Listing Region,Listing Postal Code,Listing Phone,Listing Website,Captured At,Source Record ID,Directory Importance
location,Reno Listings,reno-listings.example,Reno,NV,US,,,,,,,,,,,,,
listing,Reno Listings,,,,US,Google Business Profile,https://example.com/reno-profile,verified,Reno Listings,123 Main Street,Reno,NV,89501,775-555-0100,reno-listings.example,2026-07-31,old-listing-17,essential
"""
    reviewed_response = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "brightlocal", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed_response.status_code == 200
    review = reviewed_response.json()["data"]
    assert review["summary"]["ready"] == 2
    assert review["summary"]["listing_history"] == 1
    assert review["rows"][1]["detail"].endswith(
        "It will not count as a fresh public listing check."
    )

    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json={
            "source_system": "brightlocal",
            "source_filename": "listing-history.csv",
            "csv_text": csv_text,
            "review_hash": review["review_hash"],
            "client_request_id": str(uuid.uuid4()),
            "confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    batch = applied.json()["data"]["batch"]
    assert batch["summary"]["listing_history_created"] == 1
    assert batch["records"][1]["result"]["source_qualification"] == (
        "imported_history_not_freshly_verified"
    )

    db_session.expire_all()
    listing = db_session.query(DirectoryListing).filter_by(tenant_id=org_id).one()
    observation = (
        db_session.query(DirectoryListingObservation).filter_by(listing_id=listing.id).one()
    )
    assert listing.status == "unavailable"
    assert listing.last_verified_at is None
    assert listing.source_type == "imported"
    assert listing.source_claimed_status == "verified"
    assert listing.source_system == "brightlocal"
    assert listing.source_record_id == "old-listing-17"
    assert listing.import_batch_id == batch["id"]
    assert observation.source_type == "imported"
    assert observation.source_claimed_status == "verified"

    campaign = db_session.query(Campaign).filter_by(organization_id=org_id).one()
    inventory_response = client.get(
        f"/api/v1/citations/inventory?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()["data"]
    assert inventory["summary"]["total"] == 1
    assert inventory["summary"]["freshly_checked"] == 0
    assert inventory["summary"]["imported_history"] == 1
    assert inventory["summary"]["confirmed"] == 0
    assert inventory["truth"]["classification"] == "imported_history"
    assert inventory["items"][0]["source_type"] == "imported"

    reviewed_again = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "brightlocal", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed_again.status_code == 200
    assert [row["status"] for row in reviewed_again.json()["data"]["rows"]] == [
        "already_saved",
        "already_saved",
    ]

    rolled_back = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/{batch['id']}/rollback",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rolled_back.status_code == 200
    db_session.expire_all()
    assert db_session.query(DirectoryListing).filter_by(import_batch_id=batch["id"]).count() == 0
    assert (
        db_session.query(DirectoryListingObservation)
        .filter_by(import_batch_id=batch["id"])
        .count()
        == 0
    )
