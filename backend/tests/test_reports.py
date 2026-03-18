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

    detail = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert len(detail.json()["data"]["artifacts"]) >= 1
    artifacts = detail.json()["data"]["artifacts"]
    html_artifact = next(item for item in artifacts if item["artifact_type"] == "html")
    pdf_artifact = next(item for item in artifacts if item["artifact_type"] == "pdf")
    assert html_artifact["storage_mode"] == "local_disk"
    assert html_artifact["ready"] is True
    assert html_artifact["retrievable"] is False
    assert html_artifact["durable"] is False
    assert html_artifact["reason"] is None
    assert pdf_artifact["storage_mode"] == "local_disk"
    assert pdf_artifact["ready"] is True
    assert pdf_artifact["retrievable"] is False
    assert pdf_artifact["durable"] is False
    assert pdf_artifact["reason"] is None

    delivered = client.post(
        f"/api/v1/reports/{report_id}/deliver",
        json={"recipient": "owner@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delivered.status_code == 200
    assert delivered.json()["data"]["delivery_status"] == "sent"


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
    assert pdf_artifact["retrievable"] is False

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
