from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest

from app.automation import (
    AUTOMATION_EVENT_SCHEMA_VERSION,
    AutomationContractError,
    automation_event_catalog,
    build_automation_event,
    generate_signing_secret,
    sign_automation_event,
    verify_signed_automation_event,
)


NOW = datetime(2026, 8, 16, 17, 0, tzinfo=UTC)


def _report_event(**overrides):
    values = {
        "event_id": "evt_automation_report_001",
        "event_type": "report.ready",
        "occurred_at": NOW,
        "organization_id": "org_automation_001",
        "location_id": "loc_automation_001",
        "truth_state": "ready",
        "resource_type": "report",
        "resource_id": "report_001",
        "resource_href": "/reports?report=report_001",
        "data": {
            "report_id": "report_001",
            "report_label": "August progress report",
            "observed_through": "2026-08-15",
            "summary": "The saved report is ready for owner review.",
            "report_href": "/reports?report=report_001",
        },
    }
    values.update(overrides)
    return build_automation_event(**values)


def test_signed_outbound_event_is_canonical_and_verifiable() -> None:
    event = _report_event()
    secret = generate_signing_secret()
    signed = sign_automation_event(event, signing_secret=secret, timestamp=int(NOW.timestamp()))

    assert signed.headers["X-InsightOS-Schema"] == AUTOMATION_EVENT_SCHEMA_VERSION
    assert signed.headers["X-InsightOS-Event-ID"] == event.event_id
    assert signed.headers["X-InsightOS-Signature"].startswith("v1=")
    decoded = json.loads(signed.body)
    assert signed.body == json.dumps(
        decoded,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert decoded["data"]["summary"] == event.data["summary"]

    verified = verify_signed_automation_event(
        body=signed.body,
        headers=signed.headers,
        signing_secret=secret,
        now=NOW,
    )
    assert verified == event


def test_signature_rejects_tampering_wrong_identity_and_replay() -> None:
    event = _report_event()
    secret = generate_signing_secret()
    signed = sign_automation_event(event, signing_secret=secret, timestamp=int(NOW.timestamp()))
    tampered_body = signed.body.replace(b"owner review", b"automatic publish")

    with pytest.raises(AutomationContractError) as tampered:
        verify_signed_automation_event(
            body=tampered_body,
            headers=signed.headers,
            signing_secret=secret,
            now=NOW,
        )
    assert tampered.value.reason_code == "automation_event_signature_invalid"

    identity_headers = {**signed.headers, "X-InsightOS-Event-ID": "evt_other"}
    with pytest.raises(AutomationContractError) as identity:
        verify_signed_automation_event(
            body=signed.body,
            headers=identity_headers,
            signing_secret=secret,
            now=NOW,
        )
    assert identity.value.reason_code == "automation_event_identity_mismatch"

    with pytest.raises(AutomationContractError) as stale:
        verify_signed_automation_event(
            body=signed.body,
            headers=signed.headers,
            signing_secret=secret,
            now=NOW + timedelta(seconds=301),
        )
    assert stale.value.reason_code == "automation_event_stale"


def test_contract_rejects_unapproved_types_fields_resources_and_sensitive_data() -> None:
    with pytest.raises(AutomationContractError) as event_type:
        _report_event(event_type="database.row_changed")
    assert event_type.value.reason_code == "automation_event_type_not_approved"

    with pytest.raises(AutomationContractError) as field:
        _report_event(data={"report_id": "report_001", "provider_payload": {"raw": True}})
    assert field.value.reason_code == "automation_event_fields_not_approved"

    with pytest.raises(AutomationContractError) as resource:
        _report_event(resource_type="action")
    assert resource.value.reason_code == "automation_event_resource_mismatch"

    with pytest.raises(AutomationContractError) as sensitive:
        _report_event(
            data={
                "report_id": "report_001",
                "summary": {"customer_email": "owner@example.com"},
            }
        )
    assert sensitive.value.reason_code == "automation_event_sensitive_field"


def test_catalog_is_bounded_and_does_not_enable_commands_or_delivery() -> None:
    catalog = automation_event_catalog()
    assert [item["code"] for item in catalog] == [
        "report.ready",
        "recommendation.ready",
        "approval.requested",
        "action.completed",
        "action.failed",
        "connection.health_changed",
    ]
    serialized = json.dumps(catalog).lower()
    assert "database" not in serialized
    assert "token" not in serialized
    assert "approve action" not in serialized
    assert "publish" not in serialized
