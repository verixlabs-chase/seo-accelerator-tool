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
        assert item["template_status"] == "setup_guide_only"
        assert item["signed_events_required"] is True
        assert item["inbound_actions_enabled"] is False
        assert len(item["setup_steps"]) == 4
    n8n = next(item for item in items if item["code"] == "n8n")
    assert "Production URL" in n8n["webhook_source"]
    assert "temporary test URL" in n8n["production_url_note"]


def test_provider_setup_catalog_fails_closed_when_provider_support_drifts() -> None:
    with pytest.raises(RuntimeError, match="out of sync"):
        automation_provider_setup_catalog(
            supported_provider_codes=frozenset({"zapier", "make"})
        )
