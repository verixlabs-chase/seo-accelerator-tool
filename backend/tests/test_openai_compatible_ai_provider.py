from __future__ import annotations

import json

import httpx
import pytest

from app.intelligence.contracts.governed_ai import GovernedIntelligenceBrief
from app.services.governed_ai_provider import GovernedAIProviderError
from app.services.governed_ai_provider import OpenAICompatibleGovernedAIProvider


def _provider(
    *,
    endpoint: str = "https://models.example.com/v1/chat/completions",
    api_key: str = "customer-key",
    client: httpx.Client | None = None,
) -> OpenAICompatibleGovernedAIProvider:
    return OpenAICompatibleGovernedAIProvider(
        provider_name="customer_model",
        display_name="Customer model",
        api_key=api_key,
        endpoint=endpoint,
        model_name="local-instruct-v1",
        timeout_seconds=10,
        max_output_tokens=500,
        max_attempts=1,
        client=client,
    )


def test_openai_compatible_adapter_preserves_governed_contract() -> None:
    captured: dict = {}
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            200,
            json={
                "id": "compatible-request-1",
                "model": "local-instruct-v1",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Review the saved evidence.",
                                    "why_now": "The current measurements need attention.",
                                    "selected_action_id": "provider-cannot-own-this",
                                    "daily_action_ids": ["provider-cannot-own-this"],
                                    "evidence_used": ["campaign:1"],
                                    "uncertainties": [],
                                    "approval_required": False,
                                }
                            )
                        }
                    }
                ],
                "usage": {"input_tokens": 120, "output_tokens": 30},
            },
        )

    provider = _provider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    response = provider.generate(
        context={
            "facts": {"campaign": {"evidence_id": "campaign:1"}},
            "deterministic_selection": {
                "selected_action_id": "action-allowed",
                "approval_required": True,
                "daily_action_ids": ["action-allowed"],
            },
        },
        output_schema=GovernedIntelligenceBrief.model_json_schema(),
        prompt_template_version="test-compatible-contract-v1",
    )

    assert provider.name == "customer_model"
    assert provider.adapter_type == "openai_compatible"
    assert captured_headers["authorization"] == "Bearer customer-key"
    assert captured["model"] == "local-instruct-v1"
    assert captured["temperature"] == 0
    assert captured["seed"] == 7
    assert captured["max_tokens"] == 500
    assert "random_seed" not in captured
    assert "safe_prompt" not in captured
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert response.provider_request_id == "compatible-request-1"
    assert response.input_tokens == 120
    assert response.output_tokens == 30
    assert response.payload["selected_action_id"] == "action-allowed"
    assert response.payload["daily_action_ids"] == ["action-allowed"]
    assert response.payload["approval_required"] is True


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://models.example.com/v1/chat/completions",
        "https://localhost/v1/chat/completions",
        "https://worker.localhost/v1/chat/completions",
        "https://model.internal/v1/chat/completions",
        "https://router.home.arpa/v1/chat/completions",
        "https://127.0.0.1/v1/chat/completions",
        "https://[::1]/v1/chat/completions",
        "https://user:password@models.example.com/v1/chat/completions",
        "https://models.example.com:8443/v1/chat/completions",
        "https://models.example.com/v1/chat/completions?token=value",
        "https://models.example.com/v1/chat/completions#fragment",
    ],
)
def test_openai_compatible_adapter_rejects_unsafe_endpoint_syntax(
    endpoint: str,
) -> None:
    with pytest.raises(GovernedAIProviderError) as raised:
        _provider(endpoint=endpoint)

    assert raised.value.code == "ai_provider_endpoint_invalid"


def test_openai_compatible_adapter_accepts_default_https_port() -> None:
    provider = _provider(
        endpoint="https://models.example.com:443/v1/chat/completions"
    )

    assert provider.endpoint == "https://models.example.com:443/v1/chat/completions"


def test_openai_compatible_adapter_fails_closed_without_server_credential() -> None:
    provider = _provider(api_key="")

    with pytest.raises(GovernedAIProviderError) as raised:
        provider.generate(
            context={},
            output_schema={"type": "object"},
            prompt_template_version="test-compatible-contract-v1",
        )

    assert raised.value.code == "ai_provider_not_configured"
    assert str(raised.value) == "Customer model is not configured."


@pytest.mark.parametrize(
    ("provider_name", "display_name", "model_name", "reason_code"),
    [
        ("Customer Model", "Customer model", "model-v1", "ai_provider_identity_invalid"),
        ("customer_model", "", "model-v1", "ai_provider_identity_invalid"),
        ("customer_model", "Customer model", "", "ai_provider_model_invalid"),
    ],
)
def test_openai_compatible_adapter_rejects_invalid_identity(
    provider_name: str,
    display_name: str,
    model_name: str,
    reason_code: str,
) -> None:
    with pytest.raises(GovernedAIProviderError) as raised:
        OpenAICompatibleGovernedAIProvider(
            provider_name=provider_name,
            display_name=display_name,
            api_key="customer-key",
            endpoint="https://models.example.com/v1/chat/completions",
            model_name=model_name,
            timeout_seconds=10,
            max_output_tokens=500,
            max_attempts=1,
        )

    assert raised.value.code == reason_code
