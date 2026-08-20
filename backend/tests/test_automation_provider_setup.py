from __future__ import annotations

import pytest

from app.automation import (
    AUTOMATION_PROVIDER_SETUP_VERSION,
    automation_provider_setup_catalog,
)


PROVIDERS = frozenset({"zapier", "make", "pipedream", "n8n"})


def test_provider_setup_catalog_is_complete_truthful_and_outbound_only() -> None:
    items = automation_provider_setup_catalog(supported_provider_codes=PROVIDERS)

    assert {item["code"] for item in items} == PROVIDERS
    for item in items:
        assert item["version"] == AUTOMATION_PROVIDER_SETUP_VERSION
        assert item["template_status"] == "connection_kit_ready"
        assert item["official_docs_url"].startswith("https://")
        assert item["customer_account_required"] is True
        assert item["customer_supplies_webhook_url"] is True
        assert item["signed_events_required"] is True
        assert item["inbound_actions_enabled"] is False
        assert len(item["setup_steps"]) == 4
        assert len(item["workflow_steps"]) == 4
        assert item["test_confirmation"]
        assert item["recovery_note"]
        assert {field["source"] for field in item["field_map"]} == {
            "event_id",
            "event_type",
            "truth_state",
            "data.summary",
            "resource.href",
        }
        assert item["signature_contract"] == {
            "algorithm": "HMAC-SHA256",
            "signature_header": "X-InsightOS-Signature",
            "timestamp_header": "X-InsightOS-Timestamp",
            "event_id_header": "X-InsightOS-Event-ID",
            "signed_input": "{timestamp}.{exact_raw_request_body}",
            "signature_prefix": "v1=",
            "replay_window_seconds": 300,
        }
    n8n = next(item for item in items if item["code"] == "n8n")
    assert "Production URL" in n8n["webhook_source"]
    assert "temporary test URL" in n8n["production_url_note"]
    assert "Executions" in n8n["test_confirmation"]
    assert "Production URL" in n8n["recovery_note"]
    assert n8n["payload_path"] == "$json.body"

    pipedream = next(item for item in items if item["code"] == "pipedream")
    assert pipedream["route_field"] == "steps.trigger.event.body.event_type"


def test_provider_setup_catalog_fails_closed_when_provider_support_drifts() -> None:
    with pytest.raises(RuntimeError, match="out of sync"):
        automation_provider_setup_catalog(
            supported_provider_codes=frozenset({"zapier", "make"})
        )
