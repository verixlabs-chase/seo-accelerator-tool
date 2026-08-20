import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image

from app.models.business_location import BusinessLocation
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.enterprise_branding import OrganizationReportBrand
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.portfolio_targeting import (
    PortfolioLocationAccessGrant,
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
)
from app.models.reporting import MonthlyReport, ReportArtifact
from app.models.user import User
from app.services.commercial_plan_service import apply_commercial_plan


def _login(client, email: str, password: str) -> tuple[dict, dict]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["user"], {"Authorization": f"Bearer {payload['access_token']}"}


def _portal_logo() -> bytes:
    output = BytesIO()
    Image.new("RGB", (96, 32), color=(38, 94, 130)).save(output, format="PNG")
    return output.getvalue()


def _saved_html_report(
    db_session,
    *,
    organization_id: str,
    name: str,
    include_pdf: bool = True,
) -> dict[str, str | bytes]:
    now = datetime.now(UTC)
    location = BusinessLocation(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        name=name,
        domain=f"{name.lower().replace(' ', '-')}.example",
        status="active",
        created_at=now,
        updated_at=now,
    )
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location.id,
        name=f"{name} campaign",
        domain=location.domain or "example.com",
        setup_state="Active",
        created_at=now,
    )
    report = MonthlyReport(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json=json.dumps({"private_internal_note": "not serialized"}),
        generated_at=now,
    )
    html = f"<!doctype html><html><body><h1>{name} saved report</h1></body></html>".encode()
    artifact = ReportArtifact(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        campaign_id=campaign.id,
        report_id=report.id,
        artifact_type="html",
        storage_path="",
        storage_mode="database_private",
        storage_key=f"reports/{report.id}/report.html",
        content_type="text/html; charset=utf-8",
        byte_size=len(html),
        checksum_sha256=hashlib.sha256(html).hexdigest(),
        content_blob=html,
        durable=True,
        ready=True,
        created_at=now,
    )
    artifacts = [artifact]
    pdf = f"%PDF-1.4\n{name} verified saved report\n%%EOF\n".encode()
    if include_pdf:
        artifacts.append(
            ReportArtifact(
                id=str(uuid.uuid4()),
                tenant_id=organization_id,
                campaign_id=campaign.id,
                report_id=report.id,
                artifact_type="pdf",
                storage_path="",
                storage_mode="database_private",
                storage_key=f"reports/{report.id}/report.pdf",
                content_type="application/pdf",
                byte_size=len(pdf),
                checksum_sha256=hashlib.sha256(pdf).hexdigest(),
                content_blob=pdf,
                durable=True,
                ready=True,
                created_at=now,
            )
        )
    db_session.add_all([location, campaign, report, *artifacts])
    db_session.flush()
    return {
        "location_id": location.id,
        "report_id": report.id,
        "html": html.decode(),
        "pdf": pdf,
    }


def test_client_report_role_is_exact_read_only_and_location_scoped(client, db_session):
    client_user = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == client_user.id,
        )
        .one()
    )
    organization = db_session.get(Organization, membership.organization_id)
    assert organization is not None
    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="enterprise")
    membership.role = "org_client"
    assigned = _saved_html_report(db_session, organization_id=organization.id, name="Assigned location")
    unassigned = _saved_html_report(db_session, organization_id=organization.id, name="Other location")
    other_organization = (
        db_session.query(Organization).filter(Organization.id != organization.id).first()
    )
    assert other_organization is not None
    cross_tenant = _saved_html_report(
        db_session,
        organization_id=other_organization.id,
        name="Different customer location",
    )
    now = datetime.now(UTC)
    group = PortfolioLocationGroup(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Client A locations",
        status="active",
        version=1,
        created_at=now,
        updated_at=now,
    )
    member = PortfolioLocationGroupMember(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        location_group_id=group.id,
        business_location_id=assigned["location_id"],
        created_at=now,
    )
    grant = PortfolioLocationAccessGrant(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        user_id=client_user.id,
        location_group_id=group.id,
        access_role="viewer",
        status="active",
        version=1,
        created_at=now,
        updated_at=now,
    )
    logo = _portal_logo()
    brand = OrganizationReportBrand(
        tenant_id=organization.id,
        organization_id=organization.id,
        brand_name="Northstar Local Partners",
        report_title="Northstar search progress",
        footer_text="Prepared for Northstar clients.",
        accent_color="#265E82",
        logo_content=logo,
        logo_sha256=hashlib.sha256(logo).hexdigest(),
        logo_width=96,
        logo_height=32,
        logo_updated_at=now,
        hide_platform_attribution=True,
        enabled=True,
        version=4,
        updated_by_user_id=client_user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([group, member, grant, brand])
    db_session.commit()

    auth_user, headers = _login(client, "a@example.com", "pass-a")
    assert auth_user["org_role"] == "org_client"

    response = client.get("/api/v1/enterprise/client-reports", headers=headers)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 1
    assert payload["items"] == [
        {
            "id": assigned["report_id"],
            "location_name": "Assigned location",
            "period_label": "Month 1",
            "status": "ready",
            "generated_at": payload["items"][0]["generated_at"],
            "freshness": "current",
            "pdf_available": True,
        }
    ]
    assert payload["identity"] == {
        "display_name": "Northstar Local Partners",
        "portal_title": "Northstar search progress",
        "accent_color": "#265E82",
        "logo_data_url": f"data:image/png;base64,{base64.b64encode(logo).decode('ascii')}",
        "platform_attribution_visible": False,
    }
    assert payload["truth"]["identity_scope"] == "current_portal_only"
    serialized = json.dumps(payload)
    for private_value in (
        unassigned["report_id"],
        "Other location",
        "private_internal_note",
        "campaign_id",
        "organization_id",
        "artifact_id",
        "storage_key",
        "logo_sha256",
        "logo_width",
        "branding_version",
        "footer_text",
    ):
        assert private_value not in serialized

    view = client.get(
        f"/api/v1/enterprise/client-reports/{assigned['report_id']}/view",
        headers=headers,
    )
    assert view.status_code == 200
    assert view.text == assigned["html"]
    assert view.headers["cache-control"] == "private, no-store"
    assert view.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    assert view.headers["x-robots-tag"] == "noindex, nofollow"
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.tenant_id == organization.id,
            AuditLog.actor_user_id == client_user.id,
            AuditLog.event_type == "report.client_portal.opened",
        )
        .one()
    )
    assert json.loads(audit.payload_json) == {"report_id": assigned["report_id"]}

    download = client.get(
        f"/api/v1/enterprise/client-reports/{assigned['report_id']}/download",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.content == assigned["pdf"]
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"] == (
        'attachment; filename="client-search-report.pdf"'
    )
    assert download.headers["cache-control"] == "private, no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    download_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.tenant_id == organization.id,
            AuditLog.actor_user_id == client_user.id,
            AuditLog.event_type == "report.client_portal.pdf_downloaded",
        )
        .one()
    )
    assert json.loads(download_audit.payload_json) == {"report_id": assigned["report_id"]}

    assigned_pdf = (
        db_session.query(ReportArtifact)
        .filter(
            ReportArtifact.report_id == assigned["report_id"],
            ReportArtifact.artifact_type == "pdf",
        )
        .one()
    )
    assigned_pdf.checksum_sha256 = "0" * 64
    db_session.commit()
    corrupt = client.get(
        f"/api/v1/enterprise/client-reports/{assigned['report_id']}/download",
        headers=headers,
    )
    assert corrupt.status_code == 409
    assert corrupt.json()["errors"][0]["details"]["reason_code"] == (
        "client_report_pdf_invalid"
    )
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "report.client_portal.pdf_downloaded")
        .count()
        == 1
    )

    outside_scope = client.get(
        f"/api/v1/enterprise/client-reports/{unassigned['report_id']}/view",
        headers=headers,
    )
    assert outside_scope.status_code == 404
    outside_scope_download = client.get(
        f"/api/v1/enterprise/client-reports/{unassigned['report_id']}/download",
        headers=headers,
    )
    assert outside_scope_download.status_code == 404
    cross_tenant_response = client.get(
        f"/api/v1/enterprise/client-reports/{cross_tenant['report_id']}/view",
        headers=headers,
    )
    assert cross_tenant_response.status_code == 404
    cross_tenant_download = client.get(
        f"/api/v1/enterprise/client-reports/{cross_tenant['report_id']}/download",
        headers=headers,
    )
    assert cross_tenant_download.status_code == 404

    assert client.get("/api/v1/billing/summary", headers=headers).status_code == 403
    assert client.get("/api/v1/enterprise/activity", headers=headers).status_code == 403

    _, owner_headers = _login(client, "org-owner@example.com", "pass-org-owner")
    assert client.get("/api/v1/enterprise/client-reports", headers=owner_headers).status_code == 403
    assert (
        client.get(
            f"/api/v1/enterprise/client-reports/{assigned['report_id']}/download",
            headers=owner_headers,
        ).status_code
        == 403
    )
    activity = client.get(
        "/api/v1/enterprise/activity?category=reports",
        headers=owner_headers,
    )
    assert activity.status_code == 200
    opened = next(
        item
        for item in activity.json()["data"]["items"]
        if item["kind"] == "client_portal_report_opened"
    )
    assert opened["actor"] == {"label": "a@example.com", "type": "team_member"}
    assert assigned["report_id"] not in json.dumps(opened)
    downloaded = next(
        item
        for item in activity.json()["data"]["items"]
        if item["kind"] == "client_portal_pdf_downloaded"
    )
    assert downloaded["actor"] == {"label": "a@example.com", "type": "team_member"}
    assert assigned["report_id"] not in json.dumps(downloaded)


def test_client_reports_fail_closed_by_plan_and_empty_assignment(client, db_session):
    client_user = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == client_user.id,
        )
        .one()
    )
    organization = db_session.get(Organization, membership.organization_id)
    assert organization is not None
    membership.role = "org_client"
    db_session.commit()
    _, headers = _login(client, "a@example.com", "pass-a")

    denied = client.get("/api/v1/enterprise/client-reports", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["details"]["reason_code"] == "authenticated_client_reports_upgrade_required"

    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="enterprise")
    db_session.commit()
    empty = client.get("/api/v1/enterprise/client-reports", headers=headers)
    assert empty.status_code == 200
    empty_data = empty.json()["data"]
    assert empty_data["items"] == []
    assert empty_data["identity"] == {
        "display_name": "InsightOS",
        "portal_title": "Your private client reports",
        "accent_color": "#E85D19",
        "logo_data_url": None,
        "platform_attribution_visible": True,
    }
    assert empty_data["truth"]["scope"] == "assigned_locations_only"


def test_client_report_without_verified_pdf_stays_viewable_and_download_fails_closed(
    client,
    db_session,
):
    client_user = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(OrganizationMembership.user_id == client_user.id)
        .one()
    )
    organization = db_session.get(Organization, membership.organization_id)
    assert organization is not None
    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="enterprise")
    membership.role = "org_client"
    saved = _saved_html_report(
        db_session,
        organization_id=organization.id,
        name="HTML only location",
        include_pdf=False,
    )
    now = datetime.now(UTC)
    group = PortfolioLocationGroup(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        name="HTML only reports",
        status="active",
        version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all(
        [
            group,
            PortfolioLocationGroupMember(
                id=str(uuid.uuid4()),
                tenant_id=organization.id,
                organization_id=organization.id,
                location_group_id=group.id,
                business_location_id=str(saved["location_id"]),
                created_at=now,
            ),
            PortfolioLocationAccessGrant(
                id=str(uuid.uuid4()),
                tenant_id=organization.id,
                organization_id=organization.id,
                user_id=client_user.id,
                location_group_id=group.id,
                access_role="viewer",
                status="active",
                version=1,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    _, headers = _login(client, "a@example.com", "pass-a")
    listing = client.get("/api/v1/enterprise/client-reports", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["data"]["items"][0]["pdf_available"] is False
    view = client.get(
        f"/api/v1/enterprise/client-reports/{saved['report_id']}/view",
        headers=headers,
    )
    assert view.status_code == 200
    denied = client.get(
        f"/api/v1/enterprise/client-reports/{saved['report_id']}/download",
        headers=headers,
    )
    assert denied.status_code == 409
    assert denied.json()["errors"][0]["details"]["reason_code"] == (
        "client_report_pdf_unavailable"
    )
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "report.client_portal.pdf_downloaded")
        .count()
        == 0
    )
