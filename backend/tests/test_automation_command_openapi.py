from __future__ import annotations

import json

import pytest

from app.automation.command_openapi import build_automation_command_openapi


def test_openapi_builder_is_scoped_importable_and_secret_free() -> None:
    kit = {
        "request": {
            "url": "https://insightos.example/api/v1/automation/commands",
            "verification_url": "https://insightos.example/api/v1/automation/command-access",
            "status_url_template": "https://insightos.example/api/v1/automation/commands/{receipt_id}",
            "artifact_url_template": "https://insightos.example/api/v1/automation/commands/{receipt_id}/artifacts/{artifact_id}",
        },
        "scope": {
            "organization_id": "org-1",
            "primary_location_id": "location-1",
        },
        "allowed_actions": [{"code": "report.retrieve"}],
        "safety": {"publishing_allowed": False},
    }
    schema = {
        "type": "object",
        "properties": {
            "command_type": {
                "type": "string",
                "enum": ["report.retrieve", "listing.check_public"],
            },
            "target": {"$ref": "#/components/schemas/Target"},
        },
        "$defs": {"Target": {"type": "object"}},
    }
    document = build_automation_command_openapi(
        client_kit=kit,
        command_schema=schema,
    )

    assert document["servers"] == [{"url": "https://insightos.example"}]
    operation = document["paths"]["/api/v1/automation/commands"]["post"]
    assert operation["x-insightos-allowed-actions"] == ["report.retrieve"]
    assert operation["x-insightos-human-review-required"] is True
    assert document["components"]["schemas"]["Target"] == {"type": "object"}
    assert document["components"]["schemas"]["AutomationCommand"]["properties"][
        "command_type"
    ]["enum"] == ["report.retrieve"]
    variants = document["components"]["schemas"]["AutomationCommand"]["oneOf"]
    assert len(variants) == 1
    assert variants[0]["properties"]["command_type"] == {
        "const": "report.retrieve"
    }
    assert variants[0]["properties"]["target"]["required"] == ["report_id"]
    assert variants[0]["properties"]["target"]["properties"] == {
        "report_id": {"type": "string", "format": "uuid"}
    }
    assert variants[0]["properties"]["target"]["additionalProperties"] is False
    verification = document["paths"]["/api/v1/automation/command-access"]["get"]
    assert verification["x-insightos-command-executed"] is False
    assert verification["x-insightos-provider-called"] is False
    receipt = document["paths"][
        "/api/v1/automation/commands/{receipt_id}"
    ]["get"]
    assert receipt["x-insightos-read-only"] is True
    assert receipt["parameters"][0]["name"] == "receipt_id"
    artifact = document["paths"][
        "/api/v1/automation/commands/{receipt_id}/artifacts/{artifact_id}"
    ]["get"]
    assert artifact["x-insightos-read-only"] is True
    assert artifact["x-insightos-receipt-bound"] is True
    assert [item["name"] for item in artifact["parameters"]] == [
        "receipt_id",
        "artifact_id",
    ]
    assert "$defs" not in document["components"]["schemas"]["AutomationCommand"]
    serialized = json.dumps(document).lower()
    assert "workflow key" in serialized
    assert "token_value" not in serialized
    assert "customer_email" not in serialized


def test_openapi_builder_rejects_non_absolute_endpoint() -> None:
    with pytest.raises(ValueError):
        build_automation_command_openapi(
            client_kit={
                "request": {
                    "url": "/api/v1/automation/commands",
                    "verification_url": "/api/v1/automation/command-access",
                    "status_url_template": "/api/v1/automation/commands/{receipt_id}",
                    "artifact_url_template": "/api/v1/automation/commands/{receipt_id}/artifacts/{artifact_id}",
                },
                "scope": {},
                "allowed_actions": [],
                "safety": {},
            },
            command_schema={
                "type": "object",
                "properties": {
                    "command_type": {
                        "type": "string",
                        "enum": ["report.retrieve"],
                    }
                },
            },
        )


def test_openapi_builder_rejects_permission_outside_schema() -> None:
    with pytest.raises(ValueError):
        build_automation_command_openapi(
            client_kit={
                "request": {
                    "url": "https://insightos.example/api/v1/automation/commands",
                    "verification_url": "https://insightos.example/api/v1/automation/command-access",
                    "status_url_template": "https://insightos.example/api/v1/automation/commands/{receipt_id}",
                    "artifact_url_template": "https://insightos.example/api/v1/automation/commands/{receipt_id}/artifacts/{artifact_id}",
                },
                "scope": {},
                "allowed_actions": [{"code": "database.query"}],
                "safety": {},
            },
            command_schema={
                "type": "object",
                "properties": {
                    "command_type": {
                        "type": "string",
                        "enum": ["report.retrieve"],
                    }
                },
            },
        )


def test_openapi_builder_requires_fixed_target_for_every_canonical_action() -> None:
    with pytest.raises(ValueError):
        build_automation_command_openapi(
            client_kit={
                "request": {
                    "url": "https://insightos.example/api/v1/automation/commands",
                    "verification_url": "https://insightos.example/api/v1/automation/command-access",
                    "status_url_template": "https://insightos.example/api/v1/automation/commands/{receipt_id}",
                    "artifact_url_template": "https://insightos.example/api/v1/automation/commands/{receipt_id}/artifacts/{artifact_id}",
                },
                "scope": {},
                "allowed_actions": [{"code": "report.retrieve"}],
                "safety": {},
            },
            command_schema={
                "type": "object",
                "properties": {
                    "command_type": {
                        "type": "string",
                        "enum": ["report.retrieve", "future.unmapped_action"],
                    }
                },
            },
        )
