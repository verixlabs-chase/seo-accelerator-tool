from __future__ import annotations

from dataclasses import dataclass


AUTOMATION_PROVIDER_SETUP_VERSION = "insightos.automation.provider-setup.v1"


@dataclass(frozen=True)
class AutomationProviderSetup:
    code: str
    label: str
    webhook_source: str
    production_url_note: str
    setup_steps: tuple[str, ...]


_PROVIDER_SETUPS: tuple[AutomationProviderSetup, ...] = (
    AutomationProviderSetup(
        code="zapier",
        label="Zapier",
        webhook_source="Webhooks by Zapier — Catch Hook",
        production_url_note="Use the complete Catch Hook URL from the live Zap.",
        setup_steps=(
            "Create a Catch Hook trigger in the Zap.",
            "Copy its complete HTTPS URL into InsightOS.",
            "Save the one-time InsightOS signing secret in a private Zap field or secret store.",
            "Send an InsightOS test and confirm the Zap received the event before turning on later steps.",
        ),
    ),
    AutomationProviderSetup(
        code="make",
        label="Make",
        webhook_source="Webhooks — Custom webhook",
        production_url_note="Use the complete Custom webhook URL from the active scenario.",
        setup_steps=(
            "Add a Custom webhook trigger to the scenario.",
            "Copy its complete HTTPS URL into InsightOS.",
            "Store the one-time InsightOS signing secret privately for request verification.",
            "Send an InsightOS test and confirm the scenario received it before enabling later modules.",
        ),
    ),
    AutomationProviderSetup(
        code="pipedream",
        label="Pipedream",
        webhook_source="HTTP / Webhook trigger",
        production_url_note="Use the complete production endpoint from the deployed workflow.",
        setup_steps=(
            "Create an HTTP / Webhook trigger in the workflow.",
            "Copy its complete HTTPS endpoint into InsightOS.",
            "Store the one-time InsightOS signing secret as a private environment secret.",
            "Send an InsightOS test and confirm the deployed workflow accepted it before adding later steps.",
        ),
    ),
    AutomationProviderSetup(
        code="n8n",
        label="n8n Cloud",
        webhook_source="Published Webhook node — Production URL",
        production_url_note="Publish the workflow and use its Production URL, not the temporary test URL.",
        setup_steps=(
            "Add a Webhook node and publish the n8n Cloud workflow.",
            "Copy the node's Production URL into InsightOS.",
            "Store the one-time InsightOS signing secret as a private workflow credential or variable.",
            "Send an InsightOS test and confirm the published workflow accepted it before adding later nodes.",
        ),
    ),
)


def automation_provider_setup_catalog(
    *, supported_provider_codes: frozenset[str]
) -> list[dict[str, object]]:
    catalog_codes = {item.code for item in _PROVIDER_SETUPS}
    if catalog_codes != set(supported_provider_codes):
        raise RuntimeError("Automation provider setup catalog is out of sync.")
    return [
        {
            "code": item.code,
            "version": AUTOMATION_PROVIDER_SETUP_VERSION,
            "label": item.label,
            "webhook_source": item.webhook_source,
            "production_url_note": item.production_url_note,
            "setup_steps": list(item.setup_steps),
            "template_status": "setup_guide_only",
            "signed_events_required": True,
            "inbound_actions_enabled": False,
        }
        for item in _PROVIDER_SETUPS
    ]
