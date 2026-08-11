from app.services import reporting_service


class _WrappedDatabaseError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.orig = RuntimeError(message)


def test_report_failure_metadata_identifies_database_object_without_logging_values():
    metadata = reporting_service._report_failure_metadata(
        _WrappedDatabaseError('permission denied for table audit_logs'),
        stage="emit_report_event",
    )

    assert metadata["database_object"] == "audit_logs"
    assert metadata["failure_category"] == "table_privilege"
    assert "permission denied" not in str(metadata)


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_reports_generate_list_get_and_deliver(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Reporting Campaign", "domain": "reports.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    listed = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) >= 1
    assert listed.json()["data"]["truth"]["classification"] == "synthetic"
    assert "generated" in listed.json()["data"]["truth"]["states"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert len(detail.json()["data"]["artifacts"]) >= 1
    assert detail.json()["data"]["truth"]["classification"] == "synthetic"
    assert "minimal_artifact" in detail.json()["data"]["truth"]["states"]
    assert "non_durable" in detail.json()["data"]["truth"]["states"]
    assert "delivery_unverified" in detail.json()["data"]["truth"]["states"]
    artifacts = detail.json()["data"]["artifacts"]
    html_artifact = next(item for item in artifacts if item["artifact_type"] == "html")
    pdf_artifact = next(item for item in artifacts if item["artifact_type"] == "pdf")
    assert html_artifact["storage_mode"] == "local_disk"
    assert html_artifact["ready"] is True
    assert html_artifact["retrievable"] is True
    assert html_artifact["durable"] is False
    assert html_artifact["reason"] is None
    assert pdf_artifact["storage_mode"] == "local_disk"
    assert pdf_artifact["ready"] is True
    assert pdf_artifact["retrievable"] is True
    assert pdf_artifact["durable"] is False
    assert pdf_artifact["reason"] is None

    delivered = client.post(
        f"/api/v1/reports/{report_id}/deliver",
        json={"recipient": "owner@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delivered.status_code == 200
    assert delivered.json()["data"]["delivery_status"] == "sent"
    assert delivered.json()["data"]["truth"]["classification"] == "synthetic"
    assert "delivery_unverified" in delivered.json()["data"]["truth"]["states"]

    delivered_detail = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert delivered_detail.status_code == 200
    assert len(delivered_detail.json()["data"]["delivery_events"]) == 1
    delivery_event = delivered_detail.json()["data"]["delivery_events"][0]
    assert delivery_event["attempt_number"] == 1
    assert delivery_event["sent_at"] is not None
    assert delivery_event["delivered_at"] is None
    assert delivery_event["failure_reason"] is None


def test_reports_schedule_truth_exposes_schedule_state(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Reporting Schedule Truth", "domain": "reports-schedule.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    missing = client.get(
        f"/api/v1/reports/schedule?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 200
    assert missing.json()["data"] is None

    saved = client.put(
        "/api/v1/reports/schedule",
        json={
            "campaign_id": campaign["id"],
            "cadence": "weekly",
            "timezone": "UTC",
            "next_run_at": "2026-01-01T00:00:00Z",
            "enabled": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["truth"]["classification"] == "operator_assisted"
    assert "scheduled" in saved.json()["data"]["truth"]["states"]


def test_reports_reject_cross_org_campaign_mismatch(client, db_session, create_test_org):
    token_a = _login(client, "a@example.com", "pass-a")
    login_b = client.post("/api/v1/auth/login", json={"email": "b@example.com", "password": "pass-b"})
    assert login_b.status_code == 200

    tenant_a = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"}).json()["data"]["user"]["tenant_id"]
    tenant_b = login_b.json()["data"]["user"]["tenant_id"]

    org_b = create_test_org(tenant_id=tenant_b, name="Reports Scope Org B")

    from tests.conftest import create_test_campaign

    mismatched_campaign = create_test_campaign(
        db_session,
        org_b.id,
        tenant_id=tenant_a,
        name="Cross Org Reporting Campaign",
        domain="cross-org-reports.example",
    )
    db_session.commit()

    generate = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": mismatched_campaign.id, "month_number": 1},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert generate.status_code == 404

    schedule = client.put(
        "/api/v1/reports/schedule",
        json={
            "campaign_id": mismatched_campaign.id,
            "cadence": "daily",
            "timezone": "UTC",
            "next_run_at": "2026-01-01T00:00:00Z",
            "enabled": True,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert schedule.status_code == 404


def test_reports_delivery_fails_when_artifact_is_not_ready(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Reporting Delivery Guard", "domain": "reports-guard.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    artifacts = detail.json()["data"]["artifacts"]
    html_artifact = next(item for item in artifacts if item["artifact_type"] == "html")
    pdf_artifact = next(item for item in detail.json()["data"]["artifacts"] if item["artifact_type"] == "pdf")
    assert html_artifact["ready"] is True
    assert pdf_artifact["ready"] is True
    assert pdf_artifact["retrievable"] is True

    from app.models.reporting import ReportArtifact

    first_report_pdf = (
        db_session.query(ReportArtifact)
        .filter(
            ReportArtifact.report_id == report_id,
            ReportArtifact.artifact_type == "pdf",
        )
        .one()
    )
    first_report_pdf.storage_path = ""
    first_report_pdf.storage_key = ""
    db_session.commit()

    delivered_with_html_remaining = client.post(
        f"/api/v1/reports/{report_id}/deliver",
        json={"recipient": "owner@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delivered_with_html_remaining.status_code == 200
    partial_payload = delivered_with_html_remaining.json()["data"]
    assert partial_payload["delivery_status"] == "sent"
    assert partial_payload["artifact_readiness"]["ready"] is True
    assert any(
        item["artifact_type"] == "html" and item["ready"] is True
        for item in partial_payload["artifact_readiness"]["statuses"]
    )
    assert any(
        item["artifact_type"] == "pdf" and item["reason"] == "missing_storage_path"
        for item in partial_payload["artifact_readiness"]["statuses"]
    )

    generated_missing_all = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generated_missing_all.status_code == 200
    missing_all_report_id = generated_missing_all.json()["data"]["id"]

    second_report_artifacts = (
        db_session.query(ReportArtifact)
        .filter(ReportArtifact.report_id == missing_all_report_id)
        .all()
    )
    assert len(second_report_artifacts) >= 1
    for artifact in second_report_artifacts:
        artifact.storage_path = ""
        artifact.storage_key = ""
    db_session.commit()

    delivered = client.post(
        f"/api/v1/reports/{missing_all_report_id}/deliver",
        json={"recipient": "owner@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delivered.status_code == 200
    payload = delivered.json()["data"]
    assert payload["delivery_status"] == "failed"
    assert payload["reason"] == "artifact_not_ready"
    assert payload["artifact_readiness"]["ready"] is False
    assert all(item["reason"] == "missing_storage_path" for item in payload["artifact_readiness"]["statuses"])

    refreshed = client.get(f"/api/v1/reports/{missing_all_report_id}", headers={"Authorization": f"Bearer {token}"})
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["report"]["report_status"] == "generated"
    assert refreshed.json()["data"]["delivery_events"][0]["delivery_status"] == "failed"
    refreshed_pdf = next(item for item in refreshed.json()["data"]["artifacts"] if item["artifact_type"] == "pdf")
    assert refreshed_pdf["ready"] is False
    assert refreshed_pdf["reason"] == "missing_storage_path"


def test_reports_persist_recipients_and_protect_shared_files(client, db_session):
    from urllib.parse import urlparse

    from app.models.reporting import ReportShareLink

    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Secure Report Sharing", "domain": "secure-reports.example"},
        headers=headers,
    ).json()["data"]
    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 1},
        headers=headers,
    )
    report_id = generated.json()["data"]["id"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers=headers).json()["data"]
    html_artifact = next(item for item in detail["artifacts"] if item["artifact_type"] == "html")
    download_path = f"/api/v1/reports/{report_id}/artifacts/{html_artifact['id']}"
    downloaded = client.get(download_path, headers=headers)
    assert downloaded.status_code == 200
    assert "text/html" in downloaded.headers["content-type"]
    assert downloaded.content.startswith(b"<!doctype html>")

    saved_recipient = client.put(
        "/api/v1/reports/recipients",
        json={
            "campaign_id": campaign["id"],
            "email": "Owner@Example.com",
            "display_name": "Business Owner",
            "recipient_role": "owner",
        },
        headers=headers,
    )
    assert saved_recipient.status_code == 200
    recipient = saved_recipient.json()["data"]
    assert recipient["email"] == "owner@example.com"
    listed_recipients = client.get(
        f"/api/v1/reports/recipients?campaign_id={campaign['id']}",
        headers=headers,
    ).json()["data"]["items"]
    assert len(listed_recipients) == 1
    disabled = client.patch(
        f"/api/v1/reports/recipients/{recipient['id']}?enabled=false",
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False

    created_link = client.post(
        f"/api/v1/reports/{report_id}/share-links",
        json={"expires_in_hours": 24},
        headers=headers,
    )
    assert created_link.status_code == 200
    link_payload = created_link.json()["data"]
    assert link_payload["status"] == "active"
    assert link_payload["share_url"]
    raw_token = urlparse(link_payload["share_url"]).path.rsplit("/", 1)[-1]
    stored_link = db_session.get(ReportShareLink, link_payload["id"])
    assert stored_link is not None
    assert stored_link.token_hash != raw_token
    assert len(stored_link.token_hash) == 64

    shared_path = urlparse(link_payload["share_url"]).path
    shared = client.get(shared_path)
    assert shared.status_code == 200
    assert shared.headers["x-robots-tag"] == "noindex, nofollow"
    assert shared.content.startswith(b"<!doctype html>")

    listed_links = client.get(f"/api/v1/reports/{report_id}/share-links", headers=headers)
    listed_payload = listed_links.json()["data"]["items"][0]
    assert listed_payload["open_count"] == 1
    assert listed_payload["share_url"] is None

    revoked = client.delete(f"/api/v1/reports/share-links/{link_payload['id']}", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"
    assert client.get(shared_path).status_code == 410


def test_rpt1_report_freezes_location_story_and_regenerates_same_snapshot(client, db_session):
    from datetime import date, timedelta

    from app.models.campaign import Campaign
    from app.models.campaign_daily_metric import CampaignDailyMetric

    token = _login(client, "a@example.com", "pass-a")
    campaign_data = client.post(
        "/api/v1/campaigns",
        json={"name": "Reno Service Team", "domain": "reno-service.example"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_data["id"])
    assert campaign is not None
    observed_end = date(2026, 8, 10)

    rows = (
        (observed_end - timedelta(days=30), 100, 1000, 7.0, 8),
        (observed_end - timedelta(days=1), 50, 650, 5.5, 6),
        (observed_end, 100, 1350, 4.5, 4),
    )
    for index, (metric_date, clicks, impressions, position, issues) in enumerate(rows):
        db_session.add(
            CampaignDailyMetric(
                organization_id=campaign.organization_id,
                portfolio_id=campaign.portfolio_id,
                sub_account_id=campaign.sub_account_id,
                campaign_id=campaign.id,
                metric_date=metric_date,
                clicks=clicks,
                impressions=impressions,
                avg_position=position,
                technical_issue_count=issues,
                intelligence_score=70 + index,
                reviews_last_30d=10 + index,
                avg_rating_last_30d=4.5,
                normalization_version="analytics-v1",
                deterministic_hash=f"{'a' * 60}{index:04d}",
            )
        )
    db_session.commit()

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign.id, "month_number": 8},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    payload = detail.json()["data"]
    snapshot = payload["snapshot"]
    assert snapshot["schema_version"] == "rpt1-owner-v1"
    assert len(snapshot["snapshot_hash"]) == 64
    assert snapshot["campaign"]["id"] == campaign.id
    assert snapshot["campaign"]["location_name"] == "Reno Service Team"
    assert snapshot["period"]["end"] == observed_end.isoformat()
    visits = next(metric for metric in snapshot["metrics"] if metric["key"] == "google_visits")
    assert visits["current"] == 150
    assert visits["previous"] == 100
    assert visits["change_percent"] == 50.0
    assert visits["result"] == "improved"
    assert "Reno Service Team" in snapshot["executive_summary"]["headline"]

    original_summary = payload["report"]["summary_json"]
    regenerated = client.post(
        f"/api/v1/reports/{report_id}/regenerate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert regenerated.status_code == 200
    regenerated_payload = regenerated.json()["data"]
    assert regenerated_payload["snapshot_hash"] == snapshot["snapshot_hash"]
    assert regenerated_payload["snapshot_valid"] is True
    assert {item["artifact_type"] for item in regenerated_payload["artifacts"]} == {"html", "pdf"}

    refreshed = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["report"]["summary_json"] == original_summary
    assert refreshed.json()["data"]["snapshot"]["snapshot_hash"] == snapshot["snapshot_hash"]
