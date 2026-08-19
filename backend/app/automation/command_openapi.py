from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit


COMMAND_OPENAPI_VERSION = "insightos.automation.command-openapi.v1"

_COMMAND_TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "report.retrieve": ("report_id",),
    "report.generate_saved": ("campaign_id",),
    "recommendation.retrieve": ("recommendation_id",),
    "recommendation.request_review": ("recommendation_id",),
    "connection.refresh_saved": ("connection_id",),
    "listing.check_public": ("campaign_id",),
    "content.create_working_draft": ("campaign_id", "brief_id"),
    "content.request_draft_review": ("campaign_id", "draft_id"),
    "review.retrieve": ("review_id",),
    "review.create_response_draft": ("review_id",),
}


def build_automation_command_openapi(
    *,
    client_kit: dict[str, Any],
    command_schema: dict[str, Any],
) -> dict[str, Any]:
    """Build an importable OpenAPI document from the bounded command contract."""
    endpoint = str(client_kit["request"]["url"])
    verification_endpoint = str(client_kit["request"]["verification_url"])
    status_endpoint = str(client_kit["request"]["status_url_template"])
    artifact_endpoint = str(client_kit["request"]["artifact_url_template"])
    parsed = urlsplit(endpoint)
    verification = urlsplit(verification_endpoint)
    status = urlsplit(status_endpoint)
    artifact = urlsplit(artifact_endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path:
        raise ValueError("Automation command endpoint must be an absolute HTTP URL.")
    if (
        verification.scheme != parsed.scheme
        or verification.netloc != parsed.netloc
        or not verification.path
    ):
        raise ValueError("Automation verification endpoint must use the command server.")
    for follow_up in (status, artifact):
        if (
            follow_up.scheme != parsed.scheme
            or follow_up.netloc != parsed.netloc
            or not follow_up.path
        ):
            raise ValueError("Automation follow-up endpoints must use the command server.")

    root_schema = deepcopy(command_schema)
    definitions = root_schema.pop("$defs", {})
    allowed_actions = [
        str(item["code"]) for item in client_kit["allowed_actions"]
    ]
    command_type = root_schema.get("properties", {}).get("command_type")
    schema_actions = (
        command_type.get("enum") if isinstance(command_type, dict) else None
    )
    if not isinstance(schema_actions, list) or not schema_actions:
        raise ValueError("Automation command schema must declare a command enum.")
    if not allowed_actions or not set(allowed_actions).issubset(set(schema_actions)):
        raise ValueError("Enabled automation actions must be part of the command schema.")
    if any(action not in _COMMAND_TARGET_FIELDS for action in schema_actions):
        raise ValueError("Every automation command must have a fixed target contract.")
    command_type["enum"] = allowed_actions
    command_type["description"] = (
        "Only actions explicitly enabled for this saved workflow key."
    )
    root_schema["oneOf"] = [
        _action_target_variant(action) for action in allowed_actions
    ]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "InsightOS governed automation commands",
            "version": COMMAND_OPENAPI_VERSION,
            "description": (
                "A bounded command API for the saved InsightOS workflow key. "
                "Native scope, plan, allowance, safety, approval, and idempotency "
                "rules remain authoritative."
            ),
        },
        "servers": [{"url": f"{parsed.scheme}://{parsed.netloc}"}],
        "paths": {
            verification.path: {
                "get": {
                    "operationId": "verifyInsightOSWorkflowKey",
                    "summary": "Verify the scoped workflow key without running work",
                    "security": [{"workflowKey": []}],
                    "responses": {
                        "200": {
                            "description": "Credential and bounded scope are available",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AutomationAccessEnvelope"}
                                }
                            },
                        },
                        "401": _error_response("Workflow key invalid, expired, or revoked"),
                        "403": _error_response("Workspace or plan is unavailable"),
                        "409": _error_response("Primary location is unavailable"),
                    },
                    "x-insightos-command-executed": False,
                    "x-insightos-provider-called": False,
                }
            },
            parsed.path: {
                "post": {
                    "operationId": "requestInsightOSAutomationCommand",
                    "summary": "Request one allowed InsightOS workflow action",
                    "security": [{"workflowKey": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AutomationCommand"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Durable command receipt or saved result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AutomationReceiptEnvelope"}
                                }
                            },
                        },
                        "401": _error_response("Workflow key invalid, expired, or revoked"),
                        "409": _error_response("Command safely declined or conflicts"),
                        "422": _error_response("Command body does not match the fixed schema"),
                    },
                    "x-insightos-allowed-actions": allowed_actions,
                    "x-insightos-human-review-required": True,
                    "x-insightos-publishing-allowed": False,
                }
            },
            status.path: {
                "get": {
                    "operationId": "getInsightOSAutomationCommandReceipt",
                    "summary": "Read one durable command receipt",
                    "security": [{"workflowKey": []}],
                    "parameters": [
                        {
                            "name": "receipt_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Current durable command status or result",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/AutomationReceiptEnvelope"}
                                }
                            },
                        },
                        "401": _error_response("Workflow key invalid, expired, or revoked"),
                        "404": _error_response("Receipt is outside this workflow key's scope"),
                    },
                    "x-insightos-read-only": True,
                }
            },
            artifact.path: {
                "get": {
                    "operationId": "downloadInsightOSAutomationArtifact",
                    "summary": "Download one ready artifact from the exact receipt",
                    "security": [{"workflowKey": []}],
                    "parameters": [
                        {
                            "name": "receipt_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                        {
                            "name": "artifact_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "format": "uuid"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Private ready report artifact",
                            "content": {
                                "application/octet-stream": {
                                    "schema": {"type": "string", "format": "binary"}
                                }
                            },
                        },
                        "401": _error_response("Workflow key invalid, expired, or revoked"),
                        "404": _error_response("Artifact is not ready or outside this receipt"),
                    },
                    "x-insightos-read-only": True,
                    "x-insightos-receipt-bound": True,
                }
            },
        },
        "components": {
            "securitySchemes": {
                "workflowKey": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "Save the one-time InsightOS workflow key in the client's "
                        "private credential store. This file never contains it."
                    ),
                }
            },
            "schemas": {
                "AutomationCommand": root_schema,
                **definitions,
                **_response_schemas(),
            },
        },
        "x-insightos-contract-version": COMMAND_OPENAPI_VERSION,
        "x-insightos-scope": client_kit["scope"],
        "x-insightos-safety": client_kit["safety"],
    }


def _action_target_variant(action: str) -> dict[str, Any]:
    target_fields = _COMMAND_TARGET_FIELDS[action]
    return {
        "title": f"{action} request",
        "type": "object",
        "properties": {
            "command_type": {"const": action},
            "target": {
                "type": "object",
                "properties": {
                    field: {"type": "string", "format": "uuid"}
                    for field in target_fields
                },
                "required": list(target_fields),
                "additionalProperties": False,
            },
        },
        "required": ["command_type", "target"],
    }


def _response_schemas() -> dict[str, Any]:
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    receipt = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "id",
            "schema_version",
            "command_type",
            "idempotency_key",
            "correlation_id",
            "location_id",
            "status",
            "denial_reason_code",
            "result",
            "artifact_hash",
            "created_at",
            "completed_at",
        ],
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "schema_version": {"type": "string"},
            "command_type": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "correlation_id": {"type": "string"},
            "location_id": {"type": "string", "format": "uuid"},
            "status": {"type": "string", "enum": ["succeeded", "denied"]},
            "denial_reason_code": nullable_string,
            "result": {
                "type": "object",
                "description": "Minimized command-specific result facts.",
                "additionalProperties": True,
            },
            "artifact_hash": {"type": "string"},
            "created_at": {"type": "string", "format": "date-time"},
            "completed_at": {"type": "string", "format": "date-time"},
        },
    }
    envelope_meta = {
        "type": "object",
        "required": ["request_id"],
        "properties": {
            "request_id": {"type": "string"},
            "tenant_id": nullable_string,
        },
        "additionalProperties": False,
    }
    safety = {
        "type": "object",
        "additionalProperties": {"type": "boolean"},
    }
    return {
        "AutomationReceipt": receipt,
        "AutomationSafety": safety,
        "AutomationEnvelopeMeta": envelope_meta,
        "AutomationReceiptEnvelope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["data", "meta", "error"],
            "properties": {
                "data": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["created", "receipt", "safety"],
                    "properties": {
                        "created": {"type": "boolean"},
                        "receipt": {"$ref": "#/components/schemas/AutomationReceipt"},
                        "safety": {"$ref": "#/components/schemas/AutomationSafety"},
                    },
                },
                "meta": {"$ref": "#/components/schemas/AutomationEnvelopeMeta"},
                "error": {"type": "null"},
            },
        },
        "AutomationAccessEnvelope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["data", "meta", "error"],
            "properties": {
                "data": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": [
                        "connected",
                        "schema_version",
                        "service_account_id",
                        "organization_id",
                        "primary_location_id",
                        "allowed_location_ids",
                        "allowed_actions",
                        "expires_at",
                        "truth",
                        "safety",
                    ],
                    "properties": {
                        "connected": {"const": True},
                        "schema_version": {"type": "string"},
                        "service_account_id": {"type": "string", "format": "uuid"},
                        "organization_id": {"type": "string", "format": "uuid"},
                        "primary_location_id": {"type": "string", "format": "uuid"},
                        "allowed_location_ids": {
                            "type": "array",
                            "items": {"type": "string", "format": "uuid"},
                        },
                        "allowed_actions": {"type": "array", "items": {"type": "object"}},
                        "expires_at": {"type": "string", "format": "date-time"},
                        "truth": {"type": "object", "additionalProperties": {"type": "boolean"}},
                        "safety": {"$ref": "#/components/schemas/AutomationSafety"},
                    },
                },
                "meta": {"$ref": "#/components/schemas/AutomationEnvelopeMeta"},
                "error": {"type": "null"},
            },
        },
        "AutomationErrorEnvelope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["success", "errors", "meta"],
            "properties": {
                "success": {"const": False},
                "errors": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["code", "message", "details"],
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "details": {
                                "type": "object",
                                "description": (
                                    "Customer-safe details. Command failures place the "
                                    "stable reason code in details.reason_code."
                                ),
                                "additionalProperties": True,
                                "properties": {
                                    "reason_code": {"type": "string"}
                                },
                            },
                        },
                    },
                },
                "meta": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["request_id", "tenant_id", "status_code"],
                    "properties": {
                        "request_id": {"type": "string"},
                        "tenant_id": nullable_string,
                        "status_code": {"type": "integer"},
                    },
                },
            },
        },
    }


def _error_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/AutomationErrorEnvelope"}
            }
        },
    }
