from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from types import SimpleNamespace

import httpx
import pytest

from app.intelligence.contracts.governed_ai import GovernedBaselineNarrative
from app.models.business_location import BusinessLocation
from app.models.governed_ai import GovernedAIRun
from app.services import onboarding_baseline_ai_service
from app.services.governed_ai_provider import GovernedAIProviderResponse
from app.services.governed_ai_provider import MistralGovernedAIProvider
from tests.conftest import create_test_campaign


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider_backend="mistral",
        mistral_api_key="configured-key",
        mistral_api_endpoint="https://api.mistral.ai/v1/chat/completions",
        mistral_model="mistral-small-2603",
        ai_provider_timeout_seconds=30.0,
        ai_provider_max_attempts=2,
        ai_max_input_tokens=12_000,
        ai_max_output_tokens=800,
    )


class BaselineProvider:
    name = "mistral"
    model_name = "mistral-small-2603"

    def __init__(self, *, priority_order: list[str] | None = None) -> None:
        self.priority_order = priority_order
        self.calls = 0
        self.last_context = None

    def summarize_baseline(
        self,
        *,
        context,
        output_schema,
        prompt_template_version,
    ) -> GovernedAIProviderResponse:
        del output_schema, prompt_template_version
        self.calls += 1
        self.last_context = context
        return GovernedAIProviderResponse(
            payload={
                "headline": "Start with the website problems found in the scan",
                "summary": (
                    "The scan found two pages that need clearer search descriptions. "
                    "The saved search connection has too little history for a trend. "
                    "Work through the saved fixes in the order shown."
                ),
                "themes": [
                    {
                        "title": "Website descriptions need attention",
                        "explanation": (
                            "Two pages were saved with the same measured problem."
                        ),
                        "evidence_used": ["website:summary"],
                    }
                ],
                "priority_order": (
                    self.priority_order
                    if self.priority_order is not None
                    else context["deterministic_fix_ids"]
                ),
                "evidence_used": [
                    "website:summary",
                    "source:search_console",
                ],
                "uncertainties": [
                    "There is not enough saved search history for a trend yet."
                ],
            },
            provider_request_id="baseline-request-1",
            model_name=self.model_name,
            input_tokens=600,
            output_tokens=140,
        )


def _campaign(db_session, create_test_org):
    organization = create_test_org(name="Baseline AI org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        name="Baseline AI campaign",
        domain="baseline-ai.example",
    )
    location = BusinessLocation(
        organization_id=organization.id,
        name="Baseline AI location",
        domain=campaign.domain,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(location)
    db_session.flush()
    campaign.business_location_id = location.id
    db_session.commit()
    return campaign


def _baseline_inputs() -> tuple[dict, dict, dict, list[dict]]:
    evidence = {
        "window": {"start": "2026-07-19", "end": "2026-08-15", "days": 28},
        "website": {
            "crawl_run_id": "crawl-1",
            "pages_discovered": 10,
            "issue_count": 2,
            "severity_counts": {"high": 2},
            "issue_groups": [
                {
                    "issue_code": "missing_meta_description",
                    "count": 2,
                    "severity": "high",
                }
            ],
            "performance": [],
        },
        "organic_search": {"observed_days": 0, "clicks": None},
        "traffic": {"observed_days": 0, "sessions": None},
        "rank_tracking": {"observed": 0, "average_position": None},
    }
    scores = {
        "overall": 72,
        "coverage_weight": 1,
        "components": {"website_health": 72, "organic_visibility": None},
    }
    diagnosis = {
        "headline": "A workable foundation with clear priorities",
        "summary": "The first baseline found two website issues.",
        "fixes": [
            {
                "key": "crawl:missing_meta_description",
                "priority": "high",
                "title": "Add clear search descriptions",
                "why": "The scan found two affected pages.",
                "steps": ["Write one clear description for each page."],
                "evidence": [],
                "measurement": {"metric_id": "crawl_issue_count"},
            }
        ],
    }
    source_states = [
        {
            "key": "search_console",
            "label": "Google Search data",
            "state": "not_enough_history",
            "observed": 0,
            "optional": False,
            "last_updated": "2026-08-15T12:00:00+00:00",
        }
    ]
    return evidence, scores, diagnosis, source_states


def _stub_cost_controls(monkeypatch) -> None:
    reservation = SimpleNamespace(
        id=None,
        price_card_version="test-baseline-v1",
        estimated_cost=Decimal("0.00100000"),
    )
    terminal = SimpleNamespace(provider_reported_cost=Decimal("0.00017400"))
    monkeypatch.setattr(
        onboarding_baseline_ai_service.cost_economics_service,
        "reserve_provider_cost",
        lambda *args, **kwargs: reservation,
    )
    monkeypatch.setattr(
        onboarding_baseline_ai_service.cost_economics_service,
        "authorize_reserved_provider_dispatch",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        onboarding_baseline_ai_service.cost_economics_service,
        "calculate_provider_cost",
        lambda *args, **kwargs: Decimal("0.00017400"),
    )
    monkeypatch.setattr(
        onboarding_baseline_ai_service.cost_economics_service,
        "reconcile_provider_cost",
        lambda *args, **kwargs: terminal,
    )


def test_baseline_narrative_is_validated_metered_and_idempotent(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(onboarding_baseline_ai_service, "get_settings", _settings)
    _stub_cost_controls(monkeypatch)
    campaign = _campaign(db_session, create_test_org)
    evidence, scores, diagnosis, source_states = _baseline_inputs()
    provider = BaselineProvider()

    first = onboarding_baseline_ai_service.generate_baseline_narrative(
        db_session,
        campaign=campaign,
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
        requested_by_user_id=None,
        provider=provider,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )
    replay = onboarding_baseline_ai_service.generate_baseline_narrative(
        db_session,
        campaign=campaign,
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
        requested_by_user_id=None,
        provider=provider,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert first["state"] == "validated"
    assert first["narrative"]["priority_order"] == [
        "crawl:missing_meta_description"
    ]
    assert replay["run_id"] == first["run_id"]
    assert replay["idempotent_replay"] is True
    assert provider.calls == 1
    assert provider.last_context["allowed_evidence_ids"]
    assert "raw_url" not in str(provider.last_context).lower()
    row = db_session.get(GovernedAIRun, first["run_id"])
    assert row.status == "validated"
    assert row.provider_request_id == "baseline-request-1"
    assert row.input_tokens == 600
    assert row.output_tokens == 140


def test_baseline_narrative_cannot_change_the_deterministic_fix_order(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(onboarding_baseline_ai_service, "get_settings", _settings)
    _stub_cost_controls(monkeypatch)
    campaign = _campaign(db_session, create_test_org)
    evidence, scores, diagnosis, source_states = _baseline_inputs()

    result = onboarding_baseline_ai_service.generate_baseline_narrative(
        db_session,
        campaign=campaign,
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
        requested_by_user_id=None,
        provider=BaselineProvider(priority_order=["invented:fix"]),
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
    )

    assert result["state"] == "invalid_output"
    assert result["narrative"] is None
    row = db_session.get(GovernedAIRun, result["run_id"])
    assert row.status == "rejected"
    assert row.output_payload == {}
    assert row.error_code == "ai_output_validation_failed"


def test_baseline_contract_rejects_unknown_evidence() -> None:
    narrative = GovernedBaselineNarrative.model_validate(
        {
            "headline": "Start with the measured website problems",
            "summary": "Review the saved findings in the order shown.",
            "themes": [],
            "priority_order": ["crawl:known"],
            "evidence_used": ["invented:evidence"],
            "uncertainties": [],
        }
    )

    with pytest.raises(ValueError, match="outside the frozen baseline"):
        narrative.validate_against_context(
            evidence_ids={"website:summary"},
            deterministic_fix_ids=["crawl:known"],
        )


def test_mistral_baseline_request_uses_the_strict_explanation_schema() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "baseline-request-2",
                "model": "mistral-small-2603",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "headline": "Start with the saved website problem",
                                    "summary": "Review the measured issue in the order shown.",
                                    "themes": [],
                                    "priority_order": ["crawl:known"],
                                    "evidence_used": ["website:summary"],
                                    "uncertainties": [],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
        )

    provider = MistralGovernedAIProvider(
        api_key="test-key",
        endpoint="https://api.mistral.ai/v1/chat/completions",
        model_name="mistral-small-2603",
        timeout_seconds=10,
        max_output_tokens=500,
        max_attempts=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = provider.summarize_baseline(
        context={
            "deterministic_fix_ids": ["crawl:known"],
            "allowed_evidence_ids": ["website:summary"],
        },
        output_schema=GovernedBaselineNarrative.model_json_schema(),
        prompt_template_version="baseline-v1",
    )

    assert response.provider_request_id == "baseline-request-2"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["name"] == (
        "governed_onboarding_baseline_narrative"
    )
    system_copy = captured["messages"][0]["content"]
    assert "Preserve priority_order exactly" in system_copy
    assert "Do not invent causes" in system_copy
