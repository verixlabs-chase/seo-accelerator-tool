from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import uuid

from app.events.emitter import EventEnvelope
from app.events.outbox.event_outbox import EventOutbox
from app.models.business_location import BusinessLocation
from app.models.notification import Notification, NotificationUserState
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.user import User


def _login(client, email: str, password: str) -> tuple[str, str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return (
        payload["access_token"],
        payload["user"]["organization_id"],
        payload["user"]["id"],
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _add_notification(
    db_session,
    *,
    organization_id: str,
    observed_at: datetime,
    location: BusinessLocation | None,
    event_type: str = "report.ready",
) -> Notification:
    source_event_id = str(uuid.uuid4())
    source_event_type = "report.generated" if event_type == "report.ready" else "execution.failed"
    envelope = EventEnvelope(
        event_id=source_event_id,
        tenant_id=organization_id,
        event_type=source_event_type,
        timestamp=observed_at.isoformat(),
        payload={"test_fixture": True},
    )
    db_session.add(
        EventOutbox(
            id=source_event_id,
            tenant_id=organization_id,
            event_type=source_event_type,
            payload_json=envelope.model_dump_json(),
            payload_hash=hashlib.sha256(source_event_id.encode("ascii")).hexdigest(),
            status="processed",
            created_at=observed_at,
            processed_at=observed_at,
        )
    )
    organization = db_session.get(Organization, organization_id)
    assert organization is not None
    row = Notification(
        schema_version="alt1-notification-v1",
        tenant_id=organization_id,
        organization_id=organization_id,
        location_id=location.id if location else None,
        organization_name=organization.name,
        location_name=location.name if location else None,
        event_type=event_type,
        severity="information" if event_type == "report.ready" else "needs_attention",
        source_event_id=source_event_id,
        source_event_type=source_event_type,
        source_label="Saved reports" if event_type == "report.ready" else "Approved actions",
        resource_type="report" if event_type == "report.ready" else "action",
        resource_id=str(uuid.uuid4()),
        title="A saved report is ready" if event_type == "report.ready" else "Action needs attention",
        meaning=(
            "A saved report is ready for review."
            if event_type == "report.ready"
            else "An approved action stopped and needs review."
        ),
        action_label="Review report" if event_type == "report.ready" else "Review recovery guidance",
        action_url="/reports" if event_type == "report.ready" else "/opportunities",
        freshness_at=observed_at,
        observed_at=observed_at,
        semantic_fingerprint=hashlib.sha256(source_event_id.encode("ascii")).hexdigest(),
        cooldown_window_started_at=observed_at,
        cooldown_expires_at=observed_at + timedelta(hours=6),
        created_at=observed_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_notification_list_count_read_and_dismiss_are_per_member(
    client,
    db_session,
) -> None:
    admin_token, organization_id, admin_user_id = _login(
        client,
        "org-admin@example.com",
        "pass-org-admin",
    )
    owner_token, owner_organization_id, owner_user_id = _login(
        client,
        "org-owner@example.com",
        "pass-org-owner",
    )
    assert owner_organization_id == organization_id
    assert owner_user_id != admin_user_id
    location_one = BusinessLocation(
        organization_id=organization_id,
        name="Downtown",
        domain="downtown.example",
        status="active",
    )
    location_two = BusinessLocation(
        organization_id=organization_id,
        name="Uptown",
        domain="uptown.example",
        status="active",
    )
    db_session.add_all([location_one, location_two])
    db_session.flush()
    base_time = datetime(2026, 8, 22, 16, 0, tzinfo=UTC)
    first = _add_notification(
        db_session,
        organization_id=organization_id,
        observed_at=base_time,
        location=location_one,
    )
    second = _add_notification(
        db_session,
        organization_id=organization_id,
        observed_at=base_time + timedelta(minutes=1),
        location=location_two,
        event_type="action.failed",
    )
    organization_wide = _add_notification(
        db_session,
        organization_id=organization_id,
        observed_at=base_time + timedelta(minutes=2),
        location=None,
    )
    db_session.commit()

    listed = client.get("/api/v1/notifications", headers=_headers(admin_token))
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "private, no-store"
    payload = listed.json()["data"]
    assert payload["unread_count"] == 3
    assert payload["total"] == 3
    assert [item["id"] for item in payload["items"]] == [
        organization_wide.id,
        second.id,
        first.id,
    ]
    assert payload["items"][1]["event_type"] == "action.failed"
    assert payload["items"][1]["action_url"] == "/opportunities"
    assert payload["items"][1]["location_name"] == "Uptown"

    filtered = client.get(
        f"/api/v1/notifications?location_id={location_one.id}",
        headers=_headers(admin_token),
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["unread_count"] == 1
    assert [item["id"] for item in filtered.json()["data"]["items"]] == [first.id]

    unread = client.get(
        "/api/v1/notifications/unread-count",
        headers=_headers(admin_token),
    )
    assert unread.status_code == 200
    assert unread.json()["data"] == {"unread_count": 3, "count": 3}

    read = client.patch(
        f"/api/v1/notifications/{first.id}/read",
        headers=_headers(admin_token),
    )
    assert read.status_code == 200
    read_payload = read.json()["data"]
    assert read_payload["notification"]["is_read"] is True
    assert read_payload["notification"]["read_at"] is not None
    assert read_payload["notification"]["is_dismissed"] is False
    assert read_payload["unread_count"] == 2
    original_read_at = read_payload["notification"]["read_at"]

    repeat_read = client.patch(
        f"/api/v1/notifications/{first.id}/read",
        headers=_headers(admin_token),
    )
    assert repeat_read.status_code == 200
    assert repeat_read.json()["data"]["notification"]["read_at"] == original_read_at
    assert db_session.query(NotificationUserState).count() == 1

    owner_count = client.get(
        "/api/v1/notifications/unread-count",
        headers=_headers(owner_token),
    )
    assert owner_count.status_code == 200
    assert owner_count.json()["data"]["unread_count"] == 3

    dismissed = client.patch(
        f"/api/v1/notifications/{second.id}/dismiss",
        headers=_headers(admin_token),
    )
    assert dismissed.status_code == 200
    dismissed_payload = dismissed.json()["data"]
    assert dismissed_payload["notification"]["is_read"] is True
    assert dismissed_payload["notification"]["is_dismissed"] is True
    assert dismissed_payload["notification"]["dismissed_at"] is not None
    assert dismissed_payload["unread_count"] == 1

    active = client.get("/api/v1/notifications", headers=_headers(admin_token))
    assert active.status_code == 200
    assert active.json()["data"]["total"] == 2
    assert second.id not in {item["id"] for item in active.json()["data"]["items"]}
    history = client.get(
        "/api/v1/notifications?include_dismissed=true",
        headers=_headers(admin_token),
    )
    assert history.status_code == 200
    assert history.json()["data"]["total"] == 3
    second_item = next(
        item for item in history.json()["data"]["items"] if item["id"] == second.id
    )
    assert second_item["is_dismissed"] is True

    owner_list = client.get("/api/v1/notifications", headers=_headers(owner_token))
    assert owner_list.status_code == 200
    assert owner_list.json()["data"]["total"] == 3
    assert all(not item["is_dismissed"] for item in owner_list.json()["data"]["items"])


def test_notification_api_is_authenticated_member_only_and_tenant_isolated(
    client,
    db_session,
) -> None:
    assert client.get("/api/v1/notifications").status_code == 401
    admin_token, organization_a, _admin_user_id = _login(
        client,
        "org-admin@example.com",
        "pass-org-admin",
    )
    tenant_b_token, organization_b, _tenant_b_user_id = _login(
        client,
        "b@example.com",
        "pass-b",
    )
    assert organization_a != organization_b
    base_time = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)
    a_notice = _add_notification(
        db_session,
        organization_id=organization_a,
        observed_at=base_time,
        location=None,
    )
    b_notice = _add_notification(
        db_session,
        organization_id=organization_b,
        observed_at=base_time + timedelta(minutes=1),
        location=None,
        event_type="action.failed",
    )
    db_session.commit()

    a_list = client.get("/api/v1/notifications", headers=_headers(admin_token))
    assert a_list.status_code == 200
    assert [item["id"] for item in a_list.json()["data"]["items"]] == [a_notice.id]
    b_list = client.get("/api/v1/notifications", headers=_headers(tenant_b_token))
    assert b_list.status_code == 200
    assert [item["id"] for item in b_list.json()["data"]["items"]] == [b_notice.id]

    hidden = client.patch(
        f"/api/v1/notifications/{b_notice.id}/read",
        headers=_headers(admin_token),
    )
    assert hidden.status_code == 404
    assert (
        hidden.json()["errors"][0]["details"]["reason_code"]
        == "notification_not_found"
    )
    assert db_session.query(NotificationUserState).count() == 0

    member = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == member.id,
            OrganizationMembership.organization_id == organization_a,
        )
        .one()
    )
    membership.role = "org_user"
    db_session.commit()
    member_token, member_org, _member_id = _login(client, "a@example.com", "pass-a")
    assert member_org == organization_a
    member_response = client.get(
        "/api/v1/notifications/unread-count",
        headers=_headers(member_token),
    )
    assert member_response.status_code == 200
    assert member_response.json()["data"]["unread_count"] == 1
