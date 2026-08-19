from __future__ import annotations

import uuid
from typing import Any


N8N_REPORT_READY_TEMPLATE_VERSION = "insightos.n8n.report-ready.v1"
N8N_RECOMMENDATION_READY_TEMPLATE_VERSION = (
    "insightos.n8n.recommendation-ready.v1"
)
N8N_SAVED_REPORT_SCHEDULE_TEMPLATE_VERSION = (
    "insightos.n8n.saved-report-schedule.v1"
)
N8N_CONTENT_DRAFT_REVIEW_TEMPLATE_VERSION = (
    "insightos.n8n.content-draft-review.v1"
)

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


def build_n8n_recommendation_ready_workflow(
    *,
    service_account_id: str,
    organization_id: str,
    location_id: str,
    location_name: str,
    api_base_url: str,
) -> dict[str, Any]:
    """Return an inactive n8n workflow for saved recommendation retrieval."""
    workflow_key = (
        f"{service_account_id}:{N8N_RECOMMENDATION_READY_TEMPLATE_VERSION}"
    )

    def node_id(name: str) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:{name}"))

    webhook_name = "Receive a recommendation update"
    filter_name = "Use only this location's recommendations"
    retrieve_name = "Retrieve the saved recommendation"
    request_name = "Ask the owner to review it in InsightOS"
    ready_name = "Add your email, CRM, or task step here"
    ignored_name = "Ignore unrelated updates safely"
    nodes: list[dict[str, Any]] = [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": f"insightos-recommendation-ready-{service_account_id[:8]}",
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
                        _equals_condition(node_id("schema"), "={{ $json.body.schema_version }}", "insightos.automation.event.v1"),
                        _equals_condition(node_id("type"), "={{ $json.body.event_type }}", "recommendation.ready"),
                        _equals_condition(node_id("truth"), "={{ $json.body.truth_state }}", "ready"),
                        _equals_condition(node_id("resource"), "={{ $json.body.resource.type }}", "recommendation"),
                        _equals_condition(node_id("organization"), "={{ $json.body.organization_id }}", organization_id),
                        _equals_condition(node_id("location"), "={{ $json.body.location_id }}", location_id),
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
                "url": f"{api_base_url.rstrip('/')}/automation/commands",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpBearerAuth",
                "sendBody": True,
                "contentType": "json",
                "specifyBody": "json",
                "jsonBody": (
                    "={{ { schema_version: 'insightos.automation.command.v1',"
                    " command_type: 'recommendation.retrieve',"
                    f" organization_id: '{organization_id}', location_id: '{location_id}',"
                    " correlation_id: 'n8n:' + $json.body.event_id,"
                    " idempotency_key: 'recommendation-ready:' + $json.body.event_id,"
                    " reason: 'Retrieve the saved recommendation announced by InsightOS',"
                    " target: { recommendation_id: $json.body.resource.id } } }}"
                ),
                "options": {"timeout": 30000},
            },
            "id": node_id("retrieve"),
            "name": retrieve_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.3,
            "position": [0, 64],
            "notesInFlow": True,
            "notes": "Select the Bearer Auth credential containing the current InsightOS workflow key.",
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{api_base_url.rstrip('/')}/automation/commands",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpBearerAuth",
                "sendBody": True,
                "contentType": "json",
                "specifyBody": "json",
                "jsonBody": (
                    "={{ { schema_version: 'insightos.automation.command.v1',"
                    " command_type: 'recommendation.request_review',"
                    f" organization_id: '{organization_id}', location_id: '{location_id}',"
                    " correlation_id: 'n8n-review:' + $json.data.receipt.result.resource.id,"
                    " idempotency_key: 'recommendation-review:' + $json.data.receipt.result.resource.id,"
                    " reason: 'Ask the InsightOS owner to review this saved recommendation',"
                    " target: { recommendation_id: $json.data.receipt.result.resource.id } } }}"
                ),
                "options": {"timeout": 30000},
            },
            "id": node_id("request-review"),
            "name": request_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.3,
            "position": [288, 64],
            "notesInFlow": True,
            "notes": "This creates a review request only. The owner still approves or declines inside InsightOS.",
        },
        {"parameters": {}, "id": node_id("ready"), "name": ready_name, "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [576, 64]},
        {"parameters": {}, "id": node_id("ignored"), "name": ignored_name, "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [0, 256]},
        {
            "parameters": {
                "content": (
                    "## Saved recommendation helper\n\n"
                    f"Limited to **{location_name}**. It retrieves a saved recommendation for owner review.\n\n"
                    "It cannot approve, schedule, execute, publish, buy checks, or change a website or Business Profile."
                ),
                "height": 250,
                "width": 520,
                "color": 5,
            },
            "id": node_id("purpose-note"),
            "name": "What this workflow does",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-592, -176],
        },
    ]
    return {
        "name": f"InsightOS - Retrieve saved recommendations - {location_name}",
        "nodes": nodes,
        "connections": {
            webhook_name: {"main": [[{"node": filter_name, "type": "main", "index": 0}]]},
            filter_name: {"main": [[{"node": retrieve_name, "type": "main", "index": 0}], [{"node": ignored_name, "type": "main", "index": 0}]]},
            retrieve_name: {"main": [[{"node": request_name, "type": "main", "index": 0}]]},
            request_name: {"main": [[{"node": ready_name, "type": "main", "index": 0}]]},
        },
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "active": False,
        "versionId": str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:version")),
        "meta": {"templateCredsSetupCompleted": False, "insightosTemplateVersion": N8N_RECOMMENDATION_READY_TEMPLATE_VERSION},
        "tags": [],
    }


def build_n8n_content_draft_review_workflow(
    *,
    service_account_id: str,
    organization_id: str,
    location_id: str,
    location_name: str,
    campaign_id: str,
    api_base_url: str,
) -> dict[str, Any]:
    """Return an inactive n8n workflow for a private draft and owner review."""
    workflow_key = f"{service_account_id}:{N8N_CONTENT_DRAFT_REVIEW_TEMPLATE_VERSION}"

    def node_id(name: str) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:{name}"))

    start_name = "Start only after accepting a brief in InsightOS"
    input_name = "Enter the accepted brief ID"
    create_name = "Create the private working draft"
    review_name = "Ask the owner to review the exact draft"
    done_name = "Add your notification or task step here"
    nodes = [
        {
            "parameters": {},
            "id": node_id("manual-trigger"),
            "name": start_name,
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [-520, 120],
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": node_id("brief-field"),
                            "name": "accepted_brief_id",
                            "value": "REPLACE-WITH-ACCEPTED-BRIEF-ID",
                            "type": "string",
                        }
                    ]
                },
                "options": {},
            },
            "id": node_id("brief-input"),
            "name": input_name,
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [-288, 120],
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{api_base_url.rstrip('/')}/automation/commands",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpBearerAuth",
                "sendBody": True,
                "contentType": "json",
                "specifyBody": "json",
                "jsonBody": (
                    "={{ { schema_version: 'insightos.automation.command.v1',"
                    " command_type: 'content.create_working_draft',"
                    f" organization_id: '{organization_id}', location_id: '{location_id}',"
                    " correlation_id: 'n8n-content-draft:' + $json.accepted_brief_id,"
                    " idempotency_key: 'content-draft:' + $json.accepted_brief_id,"
                    " reason: 'Start the owner-accepted content brief',"
                    f" target: {{ campaign_id: '{campaign_id}', brief_id: $json.accepted_brief_id }} }} }}"
                ),
                "options": {"timeout": 30000},
            },
            "id": node_id("create-draft"),
            "name": create_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.3,
            "position": [-32, 120],
            "notesInFlow": True,
            "notes": "Select the Bearer Auth credential containing the current InsightOS workflow key.",
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{api_base_url.rstrip('/')}/automation/commands",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpBearerAuth",
                "sendBody": True,
                "contentType": "json",
                "specifyBody": "json",
                "jsonBody": (
                    "={{ { schema_version: 'insightos.automation.command.v1',"
                    " command_type: 'content.request_draft_review',"
                    f" organization_id: '{organization_id}', location_id: '{location_id}',"
                    " correlation_id: 'n8n-content-review:' + $json.data.receipt.result.resource.id,"
                    " idempotency_key: 'content-review:' + $json.data.receipt.result.resource.id,"
                    " reason: 'Ask the owner to review the private draft',"
                    f" target: {{ campaign_id: '{campaign_id}', draft_id: $json.data.receipt.result.resource.id }} }} }}"
                ),
                "options": {"timeout": 30000},
            },
            "id": node_id("request-review"),
            "name": review_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.3,
            "position": [240, 120],
            "notesInFlow": True,
            "notes": "This requests review only. It cannot approve, schedule, publish, or change the website.",
        },
        {"parameters": {}, "id": node_id("done"), "name": done_name, "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [512, 120]},
        {
            "parameters": {
                "content": (
                    "## Private content draft helper\n\n"
                    f"Limited to **{location_name}**. Replace the accepted brief ID, select the current InsightOS Bearer credential, and test manually.\n\n"
                    "This workflow starts inactive. It creates only a private outline and an owner-review request. It cannot write AI copy, approve, schedule, publish, or change the website."
                ),
                "height": 270,
                "width": 540,
                "color": 5,
            },
            "id": node_id("purpose-note"),
            "name": "What this workflow does",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-552, -208],
        },
    ]
    return {
        "name": f"InsightOS - Private draft review - {location_name}",
        "nodes": nodes,
        "connections": {
            start_name: {"main": [[{"node": input_name, "type": "main", "index": 0}]]},
            input_name: {"main": [[{"node": create_name, "type": "main", "index": 0}]]},
            create_name: {"main": [[{"node": review_name, "type": "main", "index": 0}]]},
            review_name: {"main": [[{"node": done_name, "type": "main", "index": 0}]]},
        },
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "active": False,
        "versionId": str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:version")),
        "meta": {"templateCredsSetupCompleted": False, "insightosTemplateVersion": N8N_CONTENT_DRAFT_REVIEW_TEMPLATE_VERSION},
        "tags": [],
    }


def build_n8n_saved_report_schedule_workflow(
    *,
    service_account_id: str,
    organization_id: str,
    location_id: str,
    location_name: str,
    campaign_id: str,
    api_base_url: str,
) -> dict[str, Any]:
    """Return an inactive monthly n8n workflow for saved-data report creation."""

    workflow_key = (
        f"{service_account_id}:{campaign_id}:"
        f"{N8N_SAVED_REPORT_SCHEDULE_TEMPLATE_VERSION}"
    )

    def node_id(name: str) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:{name}"))

    trigger_name = "Once a month"
    create_name = "Create a private report from saved results"
    ready_name = "Private report created in InsightOS"
    command_url = f"{api_base_url.rstrip('/')}/automation/commands"
    json_body = (
        "={{ {"
        " schema_version: 'insightos.automation.command.v1',"
        " command_type: 'report.generate_saved',"
        f" organization_id: '{organization_id}',"
        f" location_id: '{location_id}',"
        f" correlation_id: 'n8n-monthly:{campaign_id}:' + $now.toFormat('yyyy-MM'),"
        f" idempotency_key: 'saved-report:{campaign_id}:' + $now.toFormat('yyyy-MM'),"
        " reason: 'Create the monthly private report from saved InsightOS results',"
        f" target: {{ campaign_id: '{campaign_id}' }}"
        " } }}"
    )
    nodes: list[dict[str, Any]] = [
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "months",
                            "monthsInterval": 1,
                            "triggerAtDayOfMonth": 1,
                            "triggerAtHour": 9,
                            "triggerAtMinute": 0,
                        }
                    ]
                }
            },
            "id": node_id("schedule"),
            "name": trigger_name,
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.4,
            "position": [-320, 80],
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
                "options": {"timeout": 120000},
            },
            "id": node_id("create-report"),
            "name": create_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.3,
            "position": [-32, 80],
            "notesInFlow": True,
            "notes": (
                "Select the same Bearer Auth credential used for the one-time "
                "InsightOS workflow key. Report-creation access must be on."
            ),
        },
        {
            "parameters": {},
            "id": node_id("ready"),
            "name": ready_name,
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [272, 80],
        },
        {
            "parameters": {
                "content": (
                    "## Monthly private report\n\n"
                    f"This workflow is fixed to **{location_name}**. It creates a "
                    "private report from results InsightOS has already saved.\n\n"
                    "It does not collect fresh data, buy a check, email the report, "
                    "publish content, or change a website or Business Profile."
                ),
                "height": 250,
                "width": 500,
                "color": 5,
            },
            "id": node_id("purpose-note"),
            "name": "What this workflow does",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [-352, -240],
        },
        {
            "parameters": {
                "content": (
                    "## Finish setup\n\n"
                    "1. Open **Create a private report from saved results**.\n"
                    "2. Select the Bearer Auth credential containing the current "
                    "InsightOS workflow key.\n"
                    "3. Review the day, time, and workflow timezone.\n"
                    "4. Test manually. The same month safely returns one result.\n"
                    "5. Publish only when you want the monthly schedule to run."
                ),
                "height": 290,
                "width": 500,
                "color": 4,
            },
            "id": node_id("setup-note"),
            "name": "Finish setup before publishing",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [176, -240],
        },
    ]
    return {
        "name": f"InsightOS - Monthly private report - {location_name}",
        "nodes": nodes,
        "connections": {
            trigger_name: {
                "main": [[{"node": create_name, "type": "main", "index": 0}]]
            },
            create_name: {
                "main": [[{"node": ready_name, "type": "main", "index": 0}]]
            },
        },
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "active": False,
        "versionId": str(uuid.uuid5(_NAMESPACE, f"{workflow_key}:version")),
        "meta": {
            "templateCredsSetupCompleted": False,
            "insightosTemplateVersion": (
                N8N_SAVED_REPORT_SCHEDULE_TEMPLATE_VERSION
            ),
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
