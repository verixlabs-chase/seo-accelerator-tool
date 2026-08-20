import json
import tomllib
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.services import premium_report_service, report_artifact_storage_service, reporting_service


def test_report_files_sanitize_saved_system_wording() -> None:
    supplier = "".join(("Data", "For", "SEO"))
    snapshot = {
        "campaign": {"name": "Reno Service Team", "location_name": "Reno Service Team"},
        "period": {"start": "2026-07-01", "end": "2026-07-31"},
        "executive_summary": {
            "headline": f"{supplier} technical report",
            "summary": "Review the deterministic summary before deciding what to do.",
        },
        "metrics": [
            {
                "key": "google_visits",
                "label": "Visits from Google",
                "current": 12,
                "unit": "visits",
                "result": "steady",
                "change_percent": 0,
                "direction": "steady",
                "source": {"label": supplier, "last_updated": "2026-07-31"},
                "coverage": {"current": {"state": "complete", "observed": 31, "expected": 31}},
            }
        ],
        "trend_series": [],
        "wins": [],
        "risks": [],
        "completed_actions": [],
        "measured_outcomes": [],
        "next_priorities": [],
        "source": {"freshness_state": "current"},
    }

    html = premium_report_service.render_report_html(snapshot)
    pdf_text = "\n".join(premium_report_service.report_pdf_lines(snapshot))

    assert supplier.lower() not in html.lower()
    assert supplier.lower() not in pdf_text.lower()
    assert "deterministic summary" not in html.lower()
    assert "technical evidence" not in html.lower()
    assert "search data service" in html.lower()


def test_report_pdf_dependency_is_declared_for_vercel_runtime():
    backend_root = Path(__file__).resolve().parents[1]
    with (backend_root / "pyproject.toml").open("rb") as project_file:
        project_dependencies = tomllib.load(project_file)["project"]["dependencies"]

    runtime_requirements = (backend_root / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert any(dependency.lower().startswith("reportlab==") for dependency in project_dependencies)
    assert any(requirement.lower().startswith("reportlab==") for requirement in runtime_requirements)


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


def test_serverless_reports_persist_and_download_private_database_artifacts(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        report_artifact_storage_service,
        "get_report_artifact_storage",
        lambda: report_artifact_storage_service.DatabaseReportArtifactStorage(),
    )
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Durable Reporting Campaign", "domain": "durable-reports.com"},
        headers=headers,
    ).json()["data"]

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 1},
        headers=headers,
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert detail.status_code == 200
    artifacts = detail.json()["data"]["artifacts"]
    assert {item["artifact_type"] for item in artifacts} == {"html", "pdf"}
    assert all(item["storage_mode"] == "database_private" for item in artifacts)
    assert all(item["durable"] is True for item in artifacts)
    assert all(item["retrievable"] is True for item in artifacts)
    assert all(item["storage_path"] == "" for item in artifacts)

    from app.models.reporting import ReportArtifact

    stored_rows = (
        db_session.query(ReportArtifact)
        .filter(ReportArtifact.report_id == report_id)
        .all()
    )
    assert all(item.content_blob for item in stored_rows)

    html_artifact = next(item for item in artifacts if item["artifact_type"] == "html")
    html_response = client.get(
        f"/api/v1/reports/{report_id}/artifacts/{html_artifact['id']}",
        headers=headers,
    )
    assert html_response.status_code == 200
    assert html_response.content.startswith(b"<!doctype html>")

    pdf_artifact = next(item for item in artifacts if item["artifact_type"] == "pdf")
    pdf_response = client.get(
        f"/api/v1/reports/{report_id}/artifacts/{pdf_artifact['id']}",
        headers=headers,
    )
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF-")


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

    readiness = client.get(
        f"/api/v1/reports/readiness?campaign_id={mismatched_campaign.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert readiness.status_code == 404

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


def test_portfolio_report_comparison_keeps_location_snapshots_separate(client, db_session):
    from app.models.reporting import MonthlyReport

    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaigns = [
        client.post(
            "/api/v1/campaigns",
            json={"name": name, "domain": domain},
            headers=headers,
        ).json()["data"]
        for name, domain in (
            ("North Service Area", "north.example"),
            ("South Service Area", "south.example"),
            ("East Service Area", "east.example"),
        )
    ]

    generated_report_ids = []
    for campaign in campaigns[:2]:
        generated = client.post(
            "/api/v1/reports/generate",
            json={"campaign_id": campaign["id"], "month_number": 6},
            headers=headers,
        )
        assert generated.status_code == 200
        generated_report_ids.append(generated.json()["data"]["id"])

    comparison = client.get("/api/v1/reports/portfolio-comparison", headers=headers)
    assert comparison.status_code == 200
    payload = comparison.json()["data"]
    rows = {item["campaign_id"]: item for item in payload["locations"]}

    assert payload["source_contract"] == "latest_frozen_report_snapshot_per_location"
    assert payload["totals_are_combined"] is False
    assert payload["location_count"] == 3
    assert payload["comparable_location_count"] == 2
    assert payload["periods_aligned"] is True
    assert payload["comparison_ready"] is True
    assert rows[campaigns[0]["id"]]["comparison_state"] == "ready"
    assert rows[campaigns[1]["id"]]["comparison_state"] == "ready"
    assert rows[campaigns[2]["id"]]["comparison_state"] == "missing_report"
    assert rows[campaigns[0]["id"]]["report"]["id"] == generated_report_ids[0]
    assert rows[campaigns[1]["id"]]["report"]["id"] == generated_report_ids[1]
    assert rows[campaigns[0]["id"]]["report"]["snapshot_hash"]
    assert any("needs a report" in warning for warning in payload["warnings"])

    portfolio_pdf = client.get("/api/v1/reports/portfolio-artifact", headers=headers)
    assert portfolio_pdf.status_code == 200
    assert portfolio_pdf.headers["content-type"] == "application/pdf"
    assert "insightos-all-location-report.pdf" in portfolio_pdf.headers["content-disposition"]
    assert portfolio_pdf.headers["etag"]
    portfolio_reader = PdfReader(BytesIO(portfolio_pdf.content))
    assert len(portfolio_reader.pages) >= 5
    portfolio_text = "\n".join(page.extract_text() or "" for page in portfolio_reader.pages)
    assert "INSIGHTOS ALL-LOCATION REPORT" in portfolio_text
    assert "Prepared for" in portfolio_text
    assert "North Service Area" in portfolio_text
    assert "South Service Area" in portfolio_text
    assert "2 of 3" in portfolio_text
    assert "East Service Area" in portfolio_text
    assert "Create a report for this location before comparing it" in portfolio_text
    assert "exact saved report for each location" in portfolio_text
    assert "report identity that was active" in portfolio_text
    assert "Later branding changes do not rewrite this saved document" in " ".join(portfolio_text.split())
    assert portfolio_reader.metadata.author == "VerixLabs"
    outline_titles = [item.title for item in portfolio_reader.outline if hasattr(item, "title")]
    assert "Portfolio summary" in outline_titles
    assert "Location comparison" in outline_titles
    assert "Saved report record" in outline_titles

    repeated_pdf = client.get("/api/v1/reports/portfolio-artifact", headers=headers)
    assert repeated_pdf.status_code == 200
    assert repeated_pdf.headers["etag"] == portfolio_pdf.headers["etag"]

    tampered = db_session.get(MonthlyReport, generated_report_ids[1])
    assert tampered is not None
    tampered_snapshot = json.loads(tampered.summary_json)
    tampered_snapshot["month_number"] = 99
    tampered.summary_json = json.dumps(tampered_snapshot)
    db_session.commit()

    after_tamper = client.get("/api/v1/reports/portfolio-comparison", headers=headers)
    assert after_tamper.status_code == 200
    tampered_payload = after_tamper.json()["data"]
    tampered_rows = {item["campaign_id"]: item for item in tampered_payload["locations"]}
    assert tampered_payload["comparison_ready"] is False
    assert tampered_payload["comparable_location_count"] == 1
    assert tampered_rows[campaigns[1]["id"]]["comparison_state"] == "invalid_snapshot"
    assert tampered_rows[campaigns[1]["id"]]["metrics"] == []
    rejected_pdf = client.get("/api/v1/reports/portfolio-artifact", headers=headers)
    assert rejected_pdf.status_code == 409
    assert "matching reports for at least two locations" in rejected_pdf.json()["errors"][0]["message"]


def test_enterprise_report_identity_is_future_only_and_survives_downgrade(
    client,
    db_session,
    monkeypatch,
):
    from app.models.organization import Organization
    from app.models.organization_membership import OrganizationMembership
    from app.models.user import User
    from app.services.commercial_plan_service import apply_commercial_plan

    monkeypatch.setattr(
        report_artifact_storage_service,
        "get_report_artifact_storage",
        lambda: report_artifact_storage_service.DatabaseReportArtifactStorage(),
    )
    owner = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == owner.id)
        .one()
    )
    membership.role = "org_owner"
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"}
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    organization_id = login.json()["data"]["user"]["tenant_id"]
    headers = {"Authorization": f"Bearer {token}"}
    organization = db_session.get(Organization, organization_id)
    assert organization is not None

    blocked = client.put(
        "/api/v1/reports/branding",
        json={
            "brand_name": "Northstar Local",
            "report_title": "Client growth report",
            "footer_text": "Prepared for private client review.",
            "accent_color": "#336699",
            "hide_platform_attribution": True,
            "enabled": True,
        },
        headers=headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["errors"][0]["details"]["reason_code"] == "white_label_reporting_upgrade_required"

    apply_commercial_plan(
        db_session, organization_id=organization_id, plan_code="enterprise"
    )
    db_session.commit()

    saved = client.put(
        "/api/v1/reports/branding",
        json={
            "brand_name": "Northstar Local",
            "report_title": "Client growth report",
            "footer_text": "Prepared for private client review.",
            "accent_color": "#336699",
            "hide_platform_attribution": True,
            "enabled": True,
        },
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["applied_to_new_reports"] is True
    assert saved.json()["data"]["truth"]["existing_reports_unchanged"] is True

    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Enterprise Client", "domain": "enterprise-client.example"},
        headers=headers,
    ).json()["data"]
    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 7},
        headers=headers,
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]
    detail = client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert detail.status_code == 200
    brand = detail.json()["data"]["snapshot"]["brand"]
    assert brand == {
        "brand_name": "Northstar Local",
        "product_name": "Northstar Local",
        "publisher": "Northstar Local",
        "report_title": "Client growth report",
        "footer_text": "Prepared for private client review.",
        "accent_color": "#336699",
        "prepared_for": "Enterprise Client",
        "show_platform_attribution": False,
        "custom_branding_applied": True,
        "branding_version": 1,
    }
    html_artifact = next(
        item for item in detail.json()["data"]["artifacts"] if item["artifact_type"] == "html"
    )
    html = client.get(
        f"/api/v1/reports/{report_id}/artifacts/{html_artifact['id']}", headers=headers
    )
    assert html.status_code == 200
    assert "Northstar Local" in html.text
    assert "Client growth report" in html.text
    assert "Prepared for private client review." in html.text
    assert "--brand-accent:#336699" in html.text
    assert "Powered by InsightOS" not in html.text

    frozen_snapshot = detail.json()["data"]["snapshot"]
    pdf_reader = PdfReader(BytesIO(reporting_service.read_report_artifact(
        db_session,
        tenant_id=organization_id,
        report_id=report_id,
        artifact_id=next(
            item["id"] for item in detail.json()["data"]["artifacts"] if item["artifact_type"] == "pdf"
        ),
        organization_id=organization_id,
    )[1]))
    assert pdf_reader.metadata.author == "Northstar Local"
    assert "NORTHSTAR LOCAL" in "\n".join(page.extract_text() or "" for page in pdf_reader.pages)

    apply_commercial_plan(db_session, organization_id=organization_id, plan_code="solo")
    db_session.commit()
    after_downgrade = client.get("/api/v1/reports/branding", headers=headers)
    assert after_downgrade.status_code == 200
    assert after_downgrade.json()["data"]["saved_for_recovery"] is True
    assert after_downgrade.json()["data"]["applied_to_new_reports"] is False

    still_frozen = client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert still_frozen.json()["data"]["snapshot"] == frozen_snapshot


def test_report_prefers_direct_search_console_facts_and_explains_readiness(client, db_session):
    from datetime import date, timedelta

    from app.models.campaign import Campaign
    from app.models.campaign_daily_metric import CampaignDailyMetric
    from app.models.search_console_daily_metric import SearchConsoleDailyMetric

    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign_data = client.post(
        "/api/v1/campaigns",
        json={"name": "Direct Source Report", "domain": "direct-source.example"},
        headers=headers,
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_data["id"])
    assert campaign is not None
    observed_end = date(2026, 8, 10)

    db_session.add(
        CampaignDailyMetric(
            organization_id=campaign.organization_id,
            portfolio_id=campaign.portfolio_id,
            sub_account_id=campaign.sub_account_id,
            campaign_id=campaign.id,
            metric_date=observed_end,
            clicks=999,
            impressions=9999,
            avg_position=99,
            normalization_version="analytics-v1",
            deterministic_hash="a" * 64,
        )
    )
    for index, (metric_date, clicks, impressions, position) in enumerate(
        (
            (observed_end - timedelta(days=30), 10, 100, 8.0),
            (observed_end - timedelta(days=1), 20, 200, 5.0),
            (observed_end, 30, 300, 4.0),
        )
    ):
        db_session.add(
            SearchConsoleDailyMetric(
                organization_id=campaign.organization_id,
                campaign_id=campaign.id,
                metric_date=metric_date,
                clicks=clicks,
                impressions=impressions,
                ctr=clicks / impressions,
                avg_position=position,
                property_uri="sc-domain:direct-source.example",
                deterministic_hash=f"{index + 1}" * 64,
            )
        )
    db_session.commit()

    readiness = client.get(
        f"/api/v1/reports/readiness?campaign_id={campaign.id}",
        headers=headers,
    )
    assert readiness.status_code == 200
    readiness_payload = readiness.json()["data"]
    assert readiness_payload["status"] == "limited"
    assert readiness_payload["can_generate"] is True
    search_source = next(
        item for item in readiness_payload["sources"] if item["key"] == "search_console"
    )
    assert search_source["state"] in {"partial", "stale"}
    assert search_source["coverage"]["current"]["observed"] == 2
    assert search_source["coverage"]["comparison"]["observed"] == 1

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign.id, "month_number": 8},
        headers=headers,
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]
    detail = client.get(f"/api/v1/reports/{report_id}", headers=headers)
    snapshot = detail.json()["data"]["snapshot"]
    visits = next(item for item in snapshot["metrics"] if item["key"] == "google_visits")
    assert visits["current"] == 50
    assert visits["previous"] == 10
    assert visits["change_percent"] == 400.0
    assert snapshot["appendix"]["current_search_console_records"] == 2
    assert snapshot["appendix"]["comparison_search_console_records"] == 1


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
    from datetime import UTC, date, datetime, timedelta

    from app.models.campaign import Campaign
    from app.models.campaign_daily_metric import CampaignDailyMetric
    from app.models.rank import CampaignKeyword, KeywordCluster, RankingSnapshot

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
    cluster = KeywordCluster(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        name="Tracked services",
    )
    db_session.add(cluster)
    db_session.flush()
    for index, keyword_text in enumerate(("reno junk removal", "appliance removal reno"), start=1):
        keyword = CampaignKeyword(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            cluster_id=cluster.id,
            keyword=keyword_text,
            location_code="US",
        )
        db_session.add(keyword)
        db_session.flush()
        db_session.add(
            RankingSnapshot(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                keyword_id=keyword.id,
                position=10 + index,
                confidence=0.9,
                captured_at=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
                month_partition="2026-08",
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
    assert snapshot["schema_version"] == "rpt1-owner-v2"
    assert len(snapshot["snapshot_hash"]) == 64
    assert snapshot["campaign"]["id"] == campaign.id
    assert snapshot["campaign"]["location_name"] == "Reno Service Team"
    assert snapshot["period"]["end"] == observed_end.isoformat()
    visits = next(metric for metric in snapshot["metrics"] if metric["key"] == "google_visits")
    assert visits["current"] == 150
    assert visits["previous"] == 100
    assert visits["change_percent"] == 50.0
    assert visits["result"] == "improved"
    assert visits["source"]["label"] == "Google Search Console"
    assert visits["coverage"]["current"]["state"] == "partial"
    website_issues = next(metric for metric in snapshot["metrics"] if metric["key"] == "website_issues")
    assert website_issues["current"] is None
    assert website_issues["coverage"]["current"]["state"] == "unavailable"
    tracked_position = next(metric for metric in snapshot["metrics"] if metric["key"] == "tracked_keyword_position")
    assert tracked_position["coverage"]["current"] == {
        "state": "complete",
        "observed": 2,
        "expected": 2,
    }
    google_trend = next(item for item in snapshot["trend_series"] if item["key"] == "google_discovery")
    assert len(google_trend["points"]) == 2
    assert google_trend["points"][-1]["visits"] == 100
    assert any(item["metric_key"] == "google_visits" for item in snapshot["source"]["metric_inventory"])
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


def test_report_next_actions_are_unique_detailed_and_measurable(client, db_session):
    from datetime import UTC, date, datetime, timedelta

    from app.models.action_plan import ActionPlanOccurrence
    from app.models.campaign import Campaign
    from app.models.campaign_daily_metric import CampaignDailyMetric
    from app.models.intelligence import StrategyRecommendation

    token = _login(client, "a@example.com", "pass-a")
    campaign_data = client.post(
        "/api/v1/campaigns",
        json={"name": "Detailed Report Campaign", "domain": "detailed-report.example"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_data["id"])
    assert campaign is not None
    observed_end = date(2026, 8, 10)
    db_session.add(
        CampaignDailyMetric(
            organization_id=campaign.organization_id,
            portfolio_id=campaign.portfolio_id,
            sub_account_id=campaign.sub_account_id,
            campaign_id=campaign.id,
            metric_date=observed_end,
            clicks=10,
            impressions=100,
            avg_position=8.0,
            technical_issue_count=0,
            intelligence_score=70,
            reviews_last_30d=0,
            avg_rating_last_30d=None,
            normalization_version="analytics-v1",
            deterministic_hash="d" * 64,
        )
    )
    action_ids = [
        "reputation.launch_review_request_workflow",
        "reputation.launch_review_request_workflow",
        "reputation.launch_review_request_workflow",
        "reputation.restore_review_momentum",
    ]
    due_base = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    for index, action_id in enumerate(action_ids):
        recommendation = StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type=action_id,
            rationale="The saved review pace needs attention.",
            confidence=0.82,
            confidence_score=0.82,
            evidence_json='{"evidence":["The recent review pace is below the saved goal."]}',
            risk_tier=2,
            rollback_plan_json='{"steps":[]}',
            status="GENERATED",
            idempotency_key=f"report-action-rec-{index}",
        )
        db_session.add(recommendation)
        db_session.flush()
        db_session.add(
            ActionPlanOccurrence(
                tenant_id=campaign.tenant_id,
                organization_id=campaign.organization_id,
                campaign_id=campaign.id,
                business_location_id=campaign.business_location_id,
                recommendation_id=recommendation.id,
                action_id=action_id,
                cadence="weekly",
                period_key=f"2026-W{32 + index}",
                timezone="UTC",
                due_at=due_base + timedelta(days=index),
                status="ready",
                lexicon_id="seo-intelligence-core",
                lexicon_version="1.0.0",
                content_hash=f"{index + 1}" * 64,
                idempotency_key=f"report-action-occurrence-{index}",
            )
        )
    db_session.commit()

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign.id, "month_number": 9},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]
    detail_payload = client.get(
        f"/api/v1/reports/{report_id}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    snapshot = detail_payload["snapshot"]

    priorities = snapshot["next_priorities"]
    assert len(priorities) == 1
    assert len({item["measurement"]["metric_id"] for item in priorities}) == 1
    assert all(item["steps"] for item in priorities)
    assert all(item["why_it_matters"] for item in priorities)
    assert all(item["measurement"]["label"] for item in priorities)
    assert all(item["measurement"]["check_after_days"] for item in priorities)

    html_artifact = next(item for item in detail_payload["artifacts"] if item["artifact_type"] == "html")
    html_response = client.get(
        f"/api/v1/reports/{report_id}/artifacts/{html_artifact['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert html_response.status_code == 200
    html = html_response.text
    assert "Performance over time" in html
    assert "Where the numbers came from" in html
    assert "How results will be checked" in html
    assert html.count("Ask recent customers for reviews consistently</h3>") == 1

    pdf_artifact = next(item for item in detail_payload["artifacts"] if item["artifact_type"] == "pdf")
    pdf_response = client.get(
        f"/api/v1/reports/{report_id}/artifacts/{pdf_artifact['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pdf_response.status_code == 200
    reader = PdfReader(BytesIO(pdf_response.content))
    assert len(reader.pages) >= 3
    assert reader.metadata.title == "Detailed Report Campaign progress report"
    assert reader.metadata.author == "VerixLabs"
    assert reader.trailer["/Root"]["/Lang"] == "en-US"
    assert len(reader.outline) >= 4
    page_text = [page.extract_text() or "" for page in reader.pages]
    assert all(text.strip() for text in page_text)
    pdf_text = "\n".join(page_text)
    assert "Your results at a glance" in pdf_text
    assert "Performance over time" in pdf_text
    assert "What to do next" in pdf_text
    assert "How results will be checked" in pdf_text
    assert "Where the numbers came from" in pdf_text
    assert "InsightOS by VerixLabs" in pdf_text
    assert pdf_text.count("Ask completed customers for reviews consistently") == 1
