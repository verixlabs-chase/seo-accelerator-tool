from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from app.automation.outbound_contract import (
    build_automation_event,
    sign_automation_event,
)
from app.automation.provider_setup import automation_provider_setup_catalog


AUTOMATION_CONFORMANCE_VERSION = "insightos.automation.conformance.v1"
_FIXTURE_SECRET = "INSIGHTOS-CONFORMANCE-ONLY-DO-NOT-CONFIGURE-v1"
_FIXTURE_TIME = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def automation_provider_conformance_kit(
    *, provider: str, supported_provider_codes: frozenset[str]
) -> dict[str, object]:
    setup_by_code = {
        str(item["code"]): item
        for item in automation_provider_setup_catalog(
            supported_provider_codes=supported_provider_codes
        )
    }
    setup = setup_by_code.get(provider)
    if setup is None:
        raise ValueError("Unsupported automation conformance provider.")

    event = build_automation_event(
        event_id="evt_conformance_test_only_001",
        event_type="connection.health_changed",
        occurred_at=_FIXTURE_TIME,
        organization_id="org_conformance_test_only",
        location_id=None,
        truth_state="ready",
        resource_type="connection",
        resource_id="connection_conformance_test_only",
        resource_href="/settings#external-automation",
        data={
            "connection_name": "Receiver conformance test",
            "state": "ready",
            "summary": "Synthetic test only. No customer record or live action is included.",
            "recovery_href": "/settings#external-automation",
        },
    )
    signed = sign_automation_event(
        event,
        signing_secret=_FIXTURE_SECRET,
        timestamp=int(_FIXTURE_TIME.timestamp()),
    )
    body_text = signed.body.decode("utf-8")
    return {
        "version": AUTOMATION_CONFORMANCE_VERSION,
        "provider": provider,
        "provider_label": setup["label"],
        "test_only": True,
        "cannot_enable_live_delivery": True,
        "fixture_signing_secret": _FIXTURE_SECRET,
        "request": {
            "method": "POST",
            "content_type": "application/json",
            "headers": signed.headers,
            "exact_raw_body": body_text,
            "parsed_body": json.loads(body_text),
        },
        "provider_paths": {
            "payload": setup["payload_path"],
            "headers": setup["headers_path"],
            "route_field": setup["route_field"],
        },
        "expected": {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "truth_state": event.truth_state,
            "body_sha256": hashlib.sha256(signed.body).hexdigest(),
            "signature": signed.headers["X-InsightOS-Signature"],
            "accepted_once": True,
            "external_mutation_expected": False,
        },
        "checks": [
            "Parse the exact JSON body and route connection.health_changed to the test branch.",
            "Recompute HMAC-SHA256 over {timestamp}.{exact_raw_request_body} and compare it in constant time.",
            "Reject the same body after changing any byte.",
            "Reject timestamps more than 300 seconds from the receiving clock in live delivery.",
            "Deduplicate repeated requests with X-InsightOS-Event-ID before running an external action.",
        ],
        "safety": {
            "contains_customer_data": False,
            "contains_live_credentials": False,
            "inbound_actions_enabled": False,
            "message": (
                "This public fixture secret is only for receiver testing. "
                "Never replace the one-time secret generated for a saved connection."
            ),
        },
    }
