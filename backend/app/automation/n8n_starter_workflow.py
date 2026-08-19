from __future__ import annotations

import uuid
from typing import Any


N8N_REPORT_READY_TEMPLATE_VERSION = "insightos.n8n.report-ready.v1"

_NAMESPACE = uuid.UUID("4f69a953-f298-4d02-9d86-2ec21b2754ef")


def build_n8n_report_ready_workflow(
    *,
    service_account_id: str,
    organization_id: str,
    location_id: str,
    location_name: str,
    api_base_url: str,
) -> dict[str, Any]:
    """Return an inactive, credential-free n8n workflow for saved report retrieval."""

    workflow_key = f"{service_account_id}:{N8N_REPORT_READY_TEMPLATE_VERSION}"

    def node_id(name: str) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:{name}"))

    webhook_name = "Receive a saved report update"
    filter_name = "Use only this location's reports"
    retrieve_name = "Retrieve the saved report"
    ready_name = "Add your email, CRM, or storage step here"
    ignored_name = "Ignore unrelated updates safely"
    command_url = f"{api_base_url.rstrip('/')}/automation/commands"
    json_body = (
        "={{ {"
        " schema_version: 'insightos.automation.command.v1',"
        " command_type: 'report.retrieve',"
        f" organization_id: '{organization_id}',"
        f" location_id: '{location_id}',"
        " correlation_id: 'n8n:' + $json.body.event_id,"
        " idempotency_key: 'report-ready:' + $json.body.event_id,"
        " reason: 'Retrieve the saved report announced by InsightOS',"
        " target: { report_id: $json.body.resource.id }"
        " } }}"
    )

    nodes: list[dict[str, Any]] = [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": f"insightos-report-ready-{service_account_id[:8]}",
                "responseMode": "onReceived",
                "options": {},
            },
            "id": node_id("webhook"),
            "name": webhook_name,
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1,
            "position": [-560, 160],
            "webhookId": str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:webhook-id")),
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict",
                        "version": 3,
                    },
                    "conditions": [
                        _equals_condition(
                            node_id("condition-schema"),
                            "={{ $json.body.schema_version }}",
                            "insightos.automation.event.v1",
                        ),
                        _equals_condition(
                            node_id("condition-type"),
                            "={{ $json.body.event_type }}",
                            "report.ready",
                        ),
                        _equals_condition(
                            node_id("condition-truth"),
                            "={{ $json.body.truth_state }}",
                            "ready",
                        ),
                        _equals_condition(
                            node_id("condition-resource"),
                            "={{ $json.body.resource.type }}",
                            "report",
                        ),
                        _equals_condition(
                            node_id("condition-organization"),
                            "={{ $json.body.organization_id }}",
                            organization_id,
                        ),
                        _equals_condition(
                            node_id("condition-location"),
                            "={{ $json.body.location_id }}",
                            location_id,
                        ),
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "id": node_id("filter"),
            "name": filter_name,
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [-288, 160],
        },
        {
            "parameters": {
                "method": "POST",
                "url": command_url,
                "authentication": "genericCredentialType",
                "genericAuthType": "httpBearerAuth",
                "sendBody": True,
                "contentType": "json",
                "specifyBody": "json",
                "jsonBody": json_body,
                "options": {
                    "timeout": 30000,
                },
            },
            "id": node_id("retrieve"),
            "name": retrieve_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.3,
            "position": [0, 64],
            "notesInFlow": True,
            "notes": (
                "Before publishing, create a Bearer Auth credential in n8n, paste the "
                "one-time InsightOS workflow key as the token, and select it here."
            ),
        },
        {
            "parameters": {},
            "id": node_id("ready"),
            "name": ready_name,
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [288, 64],
        },
        {
            "parameters": {},
            "id": node_id("ignored"),
            "name": ignored_name,
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [0, 256],
        },
        {
            "parameters": {
                "content": (
                    "## InsightOS saved report helper\n\n"
                    f"This workflow is limited to **{location_name}**. It receives a "
                    "`report.ready` update and retrieves only that already-saved report.\n\n"
                    "It cannot start paid checks, approve work, publish content, change a "
                    "website, or update a Google Business Profile."
                ),
                "height": 260,
                "width": 520,
                "color": 5,
            },
            "id": node_id("purpose-note"),
            "name": "What this workflow does",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-592, -176],
        },
        {
            "parameters": {
                "content": (
                    "## Finish setup\n\n"
                    "1. Open **Retrieve the saved report**.\n"
                    "2. Create a **Bearer Auth** credential and paste the one-time "
                    "InsightOS workflow key as its token.\n"
                    "3. Save and publish this workflow.\n"
                    "4. Copy the Webhook node's **Production URL** into InsightOS and "
                    "choose only **Report ready**.\n"
                    "5. Add your own email, CRM, or storage node after the final step."
                ),
                "height": 300,
                "width": 520,
                "color": 4,
            },
            "id": node_id("setup-note"),
            "name": "Finish setup before publishing",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [0, -272],
        },
    ]

    return {
        "name": f"InsightOS - Retrieve saved reports - {location_name}",
        "nodes": nodes,
        "connections": {
            webhook_name: {
                "main": [[{"node": filter_name, "type": "main", "index": 0}]]
            },
            filter_name: {
                "main": [
                    [{"node": retrieve_name, "type": "main", "index": 0}],
                    [{"node": ignored_name, "type": "main", "index": 0}],
                ]
            },
            retrieve_name: {
                "main": [[{"node": ready_name, "type": "main", "index": 0}]]
            },
        },
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "active": False,
        "versionId": str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:version")),
        "meta": {
            "templateCredsSetupCompleted": False,
            "insightosTemplateVersion": N8N_REPORT_READY_TEMPLATE_VERSION,
        },
        "tags": [],
    }


def _equals_condition(
    condition_id: str,
    left_value: str,
    right_value: str,
) -> dict[str, Any]:
    return {
        "id": condition_id,
        "leftValue": left_value,
        "rightValue": right_value,
        "operator": {"type": "string", "operation": "equals"},
    }
