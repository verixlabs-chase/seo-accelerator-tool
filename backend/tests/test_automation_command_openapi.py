from __future__ import annotations

import json

import pytest

from app.automation.command_openapi import build_automation_command_openapi


def test_openapi_builder_is_scoped_importable_and_secret_free() -> None:
    kit = {
        "request": {"url": "https://insightos.example/api/v1/automation/commands"},
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
    assert "$defs" not in document["components"]["schemas"]["AutomationCommand"]
    serialized = json.dumps(document).lower()
    assert "workflow key" in serialized
    assert "token_value" not in serialized
    assert "customer_email" not in serialized


def test_openapi_builder_rejects_non_absolute_endpoint() -> None:
    with pytest.raises(ValueError):
        build_automation_command_openapi(
            client_kit={
                "request": {"url": "/api/v1/automation/commands"},
                "scope": {},
                "allowed_actions": [],
                "safety": {},
            },
            command_schema={"type": "object"},
        )
