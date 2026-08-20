from __future__ import annotations

from dataclasses import dataclass


AUTOMATION_PROVIDER_SETUP_VERSION = "insightos.automation.provider-setup.v3"


@dataclass(frozen=True)
class AutomationProviderSetup:
    code: str
    label: str
    webhook_source: str
    production_url_note: str
    setup_steps: tuple[str, ...]
    official_docs_url: str
    account_note: str
    test_confirmation: str
    recovery_note: str
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
            "Create a Zap and choose Webhooks by Zapier as the trigger.",
            "Choose Catch Hook, continue to the Test tab, and copy the complete address Zapier shows.",
            "Paste that address into InsightOS, choose the updates you want, and save the connection.",
            "Send an InsightOS test, load the newest sample in Zapier, then turn on the Zap.",
        ),
        official_docs_url=(
            "https://help.zapier.com/hc/en-us/articles/"
            "8496083355661-How-to-get-started-with-Webhooks-by-Zapier"
        ),
        account_note="The customer supplies a Zapier account with Webhooks by Zapier available.",
        test_confirmation=(
            "In the Zap trigger's Test tab, the newest sample should show "
            "connection.health_changed."
        ),
        recovery_note=(
            "If no sample appears, confirm the Zap still uses the same Catch Hook address, "
            "then send the InsightOS test again."
        ),
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
            "Create a scenario and add Webhooks, then choose Custom webhook as the first module.",
            "Create or select the webhook and copy the complete address Make shows.",
            "Paste that address into InsightOS, choose the updates you want, and save the connection.",
            "Choose Run once in Make, send an InsightOS test, then turn on the scenario after the sample arrives.",
        ),
        official_docs_url="https://help.make.com/webhooks",
        account_note="The customer supplies a Make account; Free-plan usage limits may apply.",
        test_confirmation=(
            "Make should show a successful sample at the Custom webhook module while the "
            "scenario is listening."
        ),
        recovery_note=(
            "If nothing arrives, choose Run once again, confirm the Custom webhook is active, "
            "and retry the InsightOS test."
        ),
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
            "Create a workflow and choose New HTTP / Webhook Requests as its trigger.",
            "Save the trigger and copy the complete address Pipedream creates.",
            "Paste that address into InsightOS, choose the updates you want, and save the connection.",
            "Send an InsightOS test, confirm the event appears, then deploy the workflow.",
        ),
        official_docs_url=(
            "https://pipedream.com/docs/workflows/building-workflows/triggers"
        ),
        account_note="The customer supplies a Pipedream account; Free-plan limits may apply.",
        test_confirmation=(
            "The HTTP trigger's event list should show a new connection.health_changed sample."
        ),
        recovery_note=(
            "If no event appears, confirm the HTTP trigger address belongs to this workflow "
            "and that the workflow is deployed before retrying."
        ),
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
            "Create a workflow, add a Webhook node, and publish the workflow.",
            "Open the Webhook node and copy its Production URL, not its temporary Test URL.",
            "Paste the Production URL into InsightOS, choose the updates you want, and save the connection.",
            "Send an InsightOS test and confirm a successful execution appears before adding later nodes.",
        ),
        official_docs_url=(
            "https://docs.n8n.io/integrations/builtin/core-nodes/"
            "n8n-nodes-base.webhook/"
        ),
        account_note="The customer supplies an n8n Cloud account or trial and publishes the workflow.",
        test_confirmation=(
            "Open Executions in n8n and confirm the published workflow shows a successful new run."
        ),
        recovery_note=(
            "If no execution appears, publish the workflow again, recopy the Production URL, "
            "and replace any temporary Test URL in InsightOS."
        ),
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
            "test_confirmation": item.test_confirmation,
            "recovery_note": item.recovery_note,
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
