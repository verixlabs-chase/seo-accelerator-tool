from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit


COMMAND_OPENAPI_VERSION = "insightos.automation.command-openapi.v1"


def build_automation_command_openapi(
    *,
    client_kit: dict[str, Any],
    command_schema: dict[str, Any],
) -> dict[str, Any]:
    """Build an importable OpenAPI document from the bounded command contract."""
    endpoint = str(client_kit["request"]["url"])
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path:
        raise ValueError("Automation command endpoint must be an absolute HTTP URL.")

    root_schema = deepcopy(command_schema)
    definitions = root_schema.pop("$defs", {})
    allowed_actions = [
        str(item["code"]) for item in client_kit["allowed_actions"]
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
                        "200": {"description": "Durable command receipt or saved result"},
                        "401": {"description": "Workflow key invalid, expired, or revoked"},
                        "409": {"description": "Command safely declined or conflicts"},
                        "422": {"description": "Command body does not match the fixed schema"},
                    },
                    "x-insightos-allowed-actions": allowed_actions,
                    "x-insightos-human-review-required": True,
                    "x-insightos-publishing-allowed": False,
                }
            }
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
            "schemas": {"AutomationCommand": root_schema, **definitions},
        },
        "x-insightos-contract-version": COMMAND_OPENAPI_VERSION,
        "x-insightos-scope": client_kit["scope"],
        "x-insightos-safety": client_kit["safety"],
    }
