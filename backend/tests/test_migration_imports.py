import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.authority import DirectoryListing, DirectoryListingObservation
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.migration_import import (
    MigrationImportBatch,
    MigrationImportRecord,
    MigrationUploadChunk,
    MigrationUploadSession,
)
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot
from app.models.reporting import ReportDeliveryEvent, ReportRecipient
from app.services.migration_upload_service import purge_expired_upload_sessions


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
        "report_recipients": 0,
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


def test_resumable_migration_upload_is_idempotent_reviewable_and_applyable(
    client, db_session
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = (
        "Record Type,Location Name,Website,City,State,Country,Keyword,Group\n"
        "location,Boise Office,boise-junk.example,Boise,ID,US,,\n"
        "keyword,Boise Office,,,,,junk removal boise,Core service\n"
    )
    chunks = [csv_text[:62], csv_text[62:121], csv_text[121:]]
    file_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    create_request_id = str(uuid.uuid4())
    created = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads",
        json={
            "source_system": "other",
            "source_filename": "large-legacy.csv",
            "total_chunks": len(chunks),
            "expected_sha256": file_hash,
            "client_request_id": create_request_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    upload = created.json()["data"]["upload"]
    upload_id = upload["id"]
    assert upload["status"] == "uploading"
    assert upload["received_chunk_indexes"] == []

    retried_create = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads",
        json={
            "source_system": "other",
            "source_filename": "large-legacy.csv",
            "total_chunks": len(chunks),
            "expected_sha256": file_hash,
            "client_request_id": create_request_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retried_create.status_code == 200
    assert retried_create.json()["data"]["upload"]["id"] == upload_id

    def upload_chunk(index: int, content: str):
        return client.put(
            f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/chunks/{index}",
            json={
                "content": content,
                "chunk_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    second = upload_chunk(1, chunks[1])
    assert second.status_code == 200
    assert second.json()["data"]["already_received"] is False
    replayed = upload_chunk(1, chunks[1])
    assert replayed.status_code == 200
    assert replayed.json()["data"]["already_received"] is True
    conflict = upload_chunk(1, f"{chunks[1]}changed")
    assert conflict.status_code == 409
    assert (
        conflict.json()["errors"][0]["details"]["reason_code"]
        == "migration_upload_chunk_conflict"
    )

    incomplete = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/review",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert incomplete.status_code == 409
    assert (
        incomplete.json()["errors"][0]["details"]["reason_code"]
        == "migration_upload_incomplete"
    )

    assert upload_chunk(2, chunks[2]).status_code == 200
    assert upload_chunk(0, chunks[0]).status_code == 200
    status_response = client.get(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["data"]["upload"]["received_chunk_indexes"] == [0, 1, 2]

    reviewed = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/review?page_size=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed.status_code == 200
    review = reviewed.json()["data"]
    assert review["summary"]["total_rows"] == 2
    assert len(review["rows"]) == 1
    assert review["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total_rows": 2,
        "total_pages": 2,
        "has_more": True,
    }
    page_two = client.get(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/review/rows?page=2&page_size=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert page_two.status_code == 200
    assert page_two.json()["data"]["rows"][0]["record_type"] == "keyword"

    locked_chunk = upload_chunk(0, chunks[0])
    assert locked_chunk.status_code == 409
    assert (
        locked_chunk.json()["errors"][0]["details"]["reason_code"]
        == "migration_upload_locked"
    )

    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/apply",
        json={
            "review_hash": review["review_hash"],
            "client_request_id": str(uuid.uuid4()),
            "confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    result = applied.json()["data"]
    assert result["batch"]["summary"]["records_applied"] == 2
    assert result["upload"]["status"] == "applied"
    db_session.expire_all()
    assert db_session.query(MigrationUploadSession).filter_by(id=upload_id).one().status == "applied"
    assert db_session.query(MigrationUploadChunk).filter_by(session_id=upload_id).count() == 3


def test_resumable_migration_upload_rejects_wrong_complete_file_hash(client) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    csv_text = "Record Type,Location Name,Website\nlocation,Austin Office,austin.example\n"
    created = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads",
        json={
            "source_system": "other",
            "source_filename": "changed.csv",
            "total_chunks": 1,
            "expected_sha256": "0" * 64,
            "client_request_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    upload_id = created.json()["data"]["upload"]["id"]
    uploaded = client.put(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/chunks/0",
        json={
            "content": csv_text,
            "chunk_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uploaded.status_code == 200
    reviewed = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/review",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed.status_code == 409
    assert (
        reviewed.json()["errors"][0]["details"]["reason_code"]
        == "migration_upload_file_hash_mismatch"
    )


def test_resumable_migration_upload_reviews_more_than_direct_row_limit(client) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    rows = ["Record Type,Location Name,Website,Keyword,Group"]
    rows.append("location,Large Account,large-account.example,,")
    rows.extend(
        f"keyword,Large Account,,service search {index},Imported"
        for index in range(2_501)
    )
    csv_text = "\n".join(rows) + "\n"

    direct = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "other", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert direct.status_code == 422
    assert (
        direct.json()["errors"][0]["details"]["reason_code"]
        == "migration_row_limit_exceeded"
    )

    source_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    created = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads",
        json={
            "source_system": "other",
            "source_filename": "large-account.csv",
            "total_chunks": 1,
            "expected_sha256": source_hash,
            "client_request_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    upload_id = created.json()["data"]["upload"]["id"]
    uploaded = client.put(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/chunks/0",
        json={"content": csv_text, "chunk_sha256": source_hash},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uploaded.status_code == 200
    reviewed = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/review?page_size=25",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed.status_code == 200
    review = reviewed.json()["data"]
    assert review["summary"]["total_rows"] == 2_502
    assert review["summary"]["ready"] == 2_502
    assert review["pagination"]["total_pages"] == 101
    assert len(review["rows"]) == 25


def test_expired_migration_upload_content_is_purged(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    csv_text = "Record Type,Location Name,Website\nlocation,Old Upload,old.example\n"
    source_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    created = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads",
        json={
            "source_system": "other",
            "source_filename": "old.csv",
            "total_chunks": 1,
            "expected_sha256": source_hash,
            "client_request_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    upload_id = created.json()["data"]["upload"]["id"]
    uploaded = client.put(
        f"/api/v1/organizations/{org_id}/migration-imports/uploads/{upload_id}/chunks/0",
        json={"content": csv_text, "chunk_sha256": source_hash},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uploaded.status_code == 200
    upload = db_session.query(MigrationUploadSession).filter_by(id=upload_id).one()
    upload.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    result = purge_expired_upload_sessions(db_session)
    db_session.commit()

    assert result == {"sessions_deleted": 1, "chunks_deleted": 1}
    assert db_session.query(MigrationUploadSession).filter_by(id=upload_id).count() == 0
    assert db_session.query(MigrationUploadChunk).filter_by(session_id=upload_id).count() == 0


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


def test_migration_imports_report_recipients_disabled_without_sending(
    client,
    db_session,
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = """Record Type,Location Name,Website,City,State,Country,Recipient Email,Recipient Name,Recipient Role,Source Record ID
location,Reno Reports,reno-reports.example,Reno,NV,US,,,,
report recipient,Reno Reports,,,,,OWNER@EXAMPLE.COM,Alex Owner,owner,old-recipient-17
"""
    reviewed = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "other", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviewed.status_code == 200
    review = reviewed.json()["data"]
    assert review["adapter"] == "insightos_standard_csv_v1"
    assert review["summary"]["report_recipients"] == 1
    assert review["rows"][1]["detail"].endswith(
        "No report will be sent until an owner turns it on."
    )

    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json={
            "source_system": "other",
            "source_filename": "report-recipients.csv",
            "csv_text": csv_text,
            "review_hash": review["review_hash"],
            "client_request_id": str(uuid.uuid4()),
            "confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    batch = applied.json()["data"]["batch"]
    assert batch["summary"]["report_recipients_created"] == 1
    assert batch["records"][1]["result"]["delivery_state"] == (
        "disabled_until_owner_review"
    )

    db_session.expire_all()
    recipient = db_session.query(ReportRecipient).filter_by(tenant_id=org_id).one()
    assert recipient.email == "owner@example.com"
    assert recipient.enabled is False
    assert recipient.source_type == "imported"
    assert recipient.source_system == "other"
    assert recipient.source_record_id == "old-recipient-17"
    assert recipient.import_batch_id == batch["id"]
    assert db_session.query(ReportDeliveryEvent).filter_by(tenant_id=org_id).count() == 0

    listed = client.get(
        f"/api/v1/reports/recipients?campaign_id={recipient.campaign_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    listed_recipient = listed.json()["data"]["items"][0]
    assert listed_recipient["enabled"] is False
    assert listed_recipient["source_type"] == "imported"

    rolled_back = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/{batch['id']}/rollback",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rolled_back.status_code == 200
    db_session.expire_all()
    assert db_session.query(ReportRecipient).filter_by(import_batch_id=batch["id"]).count() == 0


def test_migration_source_adapters_map_familiar_export_headers(client) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    semrush_csv = """Type,Project,Root Domain,Keyword,Tags
location,Reno Project,reno-project.example,,
keyword,Reno Project,,junk removal reno,Core service
"""
    semrush = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "semrush", "csv_text": semrush_csv},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert semrush.status_code == 200
    semrush_review = semrush.json()["data"]
    assert semrush_review["adapter"] == "semrush_csv_v1"
    assert semrush_review["field_mapping"]["location_name"] == "Project"
    assert semrush_review["field_mapping"]["website"] == "Root Domain"
    assert semrush_review["field_mapping"]["keyword_group"] == "Tags"
    assert semrush_review["summary"]["ready"] == 2

    brightlocal_csv = """Type,Business,Website URL,Citation Name,Citation Link,Citation State,Last Checked
location,Reno Citations,reno-citations.example,,,,
listing,Reno Citations,,Google Business Profile,https://example.com/reno,live,2026-07-31
"""
    brightlocal = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "brightlocal", "csv_text": brightlocal_csv},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert brightlocal.status_code == 200
    brightlocal_review = brightlocal.json()["data"]
    assert brightlocal_review["adapter"] == "brightlocal_csv_v1"
    assert brightlocal_review["field_mapping"]["location_name"] == "Business"
    assert brightlocal_review["field_mapping"]["directory_name"] == "Citation Name"
    assert brightlocal_review["field_mapping"]["captured_at"] == "Last Checked"
    assert brightlocal_review["summary"]["ready"] == 2


def test_reviewed_imported_recipient_is_protected_from_rollback(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    csv_text = """Record Type,Location Name,Website,Recipient Email,Recipient Role
location,Protected Reports,protected-reports.example,,
report recipient,Protected Reports,,client@example.com,client
"""
    review = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/dry-run",
        json={"source_system": "other", "csv_text": csv_text},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    applied = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/apply",
        json={
            "source_system": "other",
            "csv_text": csv_text,
            "review_hash": review["review_hash"],
            "client_request_id": str(uuid.uuid4()),
            "confirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert applied.status_code == 200
    batch_id = applied.json()["data"]["batch"]["id"]
    db_session.expire_all()
    recipient = db_session.query(ReportRecipient).filter_by(tenant_id=org_id).one()

    approved = client.patch(
        f"/api/v1/reports/recipients/{recipient.id}?enabled=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["source_type"] == "imported_approved"

    rollback = client.post(
        f"/api/v1/organizations/{org_id}/migration-imports/{batch_id}/rollback",
        json={"confirmed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rollback.status_code == 409
    assert rollback.json()["errors"][0]["details"]["reason_code"] == (
        "migration_rollback_blocked_by_new_work"
    )
    db_session.expire_all()
    assert db_session.query(ReportRecipient).filter_by(id=recipient.id).count() == 1
