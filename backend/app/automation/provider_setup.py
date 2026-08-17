from __future__ import annotations

from dataclasses import dataclass


AUTOMATION_PROVIDER_SETUP_VERSION = "insightos.automation.provider-setup.v2"


@dataclass(frozen=True)
class AutomationProviderSetup:
    code: str
    label: str
    webhook_source: str
    production_url_note: str
    setup_steps: tuple[str, ...]
    official_docs_url: str
    account_note: str
    payload_path: str
    headers_path: str
    route_field: str
    workflow_steps: tuple[str, ...]


_PROVIDER_SETUPS: tuple[AutomationProviderSetup, ...] = (
    AutomationProviderSetup(
        code="zapier",
        label="Zapier",
        webhook_source="Webhooks by Zapier — Catch Hook",
        production_url_note="Use the complete Catch Hook URL from the live Zap.",
        setup_steps=(
            "Create a Catch Hook trigger in the Zap. Use Catch Raw Hook when the workflow will verify the signature itself.",
            "Copy its complete HTTPS URL into InsightOS.",
            "Save the one-time InsightOS signing secret in a private Zap field or secret store.",
            "Send an InsightOS test and confirm the Zap received the event before turning on later steps.",
        ),
        official_docs_url=(
            "https://help.zapier.com/hc/en-us/articles/"
            "8496083355661-How-to-get-started-with-Webhooks-by-Zapier"
        ),
        account_note="The customer supplies a Zapier account with Webhooks by Zapier available.",
        payload_path="Catch Hook trigger payload",
        headers_path="Catch Raw Hook request headers",
        route_field="event_type",
        workflow_steps=(
            "Receive the signed InsightOS POST in Webhooks by Zapier.",
            "Filter or branch on event_type and truth_state.",
            "Use event_id as the duplicate-protection key.",
            "Map data.summary and resource.href into the customer's chosen Zap action.",
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
        official_docs_url="https://help.make.com/webhooks",
        account_note="The customer supplies a Make account; Free-plan usage limits may apply.",
        payload_path="Custom webhook bundle",
        headers_path="Webhook request headers",
        route_field="event_type",
        workflow_steps=(
            "Receive the signed InsightOS POST in a Custom webhook module.",
            "Use a router and filters for event_type and truth_state.",
            "Use event_id as the duplicate-protection key.",
            "Map data.summary and resource.href into the customer's chosen Make module.",
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
        official_docs_url=(
            "https://pipedream.com/docs/workflows/building-workflows/triggers"
        ),
        account_note="The customer supplies a Pipedream account; Free-plan limits may apply.",
        payload_path="steps.trigger.event.body",
        headers_path="steps.trigger.event.headers",
        route_field="steps.trigger.event.body.event_type",
        workflow_steps=(
            "Receive the signed InsightOS POST in an HTTP / Webhook trigger.",
            "Branch on steps.trigger.event.body.event_type and truth_state.",
            "Use event_id as the duplicate-protection key.",
            "Map data.summary and resource.href into the customer's chosen action or code step.",
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
        official_docs_url=(
            "https://docs.n8n.io/integrations/builtin/core-nodes/"
            "n8n-nodes-base.webhook/"
        ),
        account_note="The customer supplies an n8n Cloud account or trial and publishes the workflow.",
        payload_path="$json.body",
        headers_path="$json.headers",
        route_field="$json.body.event_type",
        workflow_steps=(
            "Receive the signed InsightOS POST in a published Webhook node.",
            "Use a Switch node for $json.body.event_type and truth_state.",
            "Use event_id as the duplicate-protection key.",
            "Map data.summary and resource.href into the customer's chosen n8n node.",
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
            "official_docs_url": item.official_docs_url,
            "account_note": item.account_note,
            "payload_path": item.payload_path,
            "headers_path": item.headers_path,
            "route_field": item.route_field,
            "workflow_steps": list(item.workflow_steps),
            "field_map": [
                {
                    "source": "event_id",
                    "purpose": "Use as the duplicate-protection key.",
                },
                {
                    "source": "event_type",
                    "purpose": "Route the workflow to the correct branch.",
                },
                {
                    "source": "truth_state",
                    "purpose": "Show whether the saved result is ready, completed, failed, or blocked.",
                },
                {
                    "source": "data.summary",
                    "purpose": "Use as the customer-facing message or task description.",
                },
                {
                    "source": "resource.href",
                    "purpose": "Append to the InsightOS origin for a link back to the saved record.",
                },
            ],
            "signature_contract": {
                "algorithm": "HMAC-SHA256",
                "signature_header": "X-InsightOS-Signature",
                "timestamp_header": "X-InsightOS-Timestamp",
                "event_id_header": "X-InsightOS-Event-ID",
                "signed_input": "{timestamp}.{exact_raw_request_body}",
                "signature_prefix": "v1=",
                "replay_window_seconds": 300,
            },
            "template_status": "connection_kit_ready",
            "customer_account_required": True,
            "customer_supplies_webhook_url": True,
            "signed_events_required": True,
            "inbound_actions_enabled": False,
        }
        for item in _PROVIDER_SETUPS
    ]
