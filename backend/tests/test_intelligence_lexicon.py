from __future__ import annotations

from copy import deepcopy

import httpx
import pytest
from pydantic import ValidationError

from app.intelligence.lexicon.ai_context import build_ai_decision_context
from app.intelligence.lexicon.evaluator import evaluate_core_web_vitals, evaluate_metric
from app.intelligence.lexicon.loader import get_builtin_lexicon, load_lexicon_payload
from app.intelligence.lexicon.standards import (
    compare_crux_thresholds,
    extract_crux_thresholds,
    latest_crux_standards_check,
    run_and_record_crux_standards_check,
)


def test_builtin_lexicon_is_complete_and_cross_referenced() -> None:
    lexicon = get_builtin_lexicon()

    assert lexicon.meta.lexicon_id == "verix.seo.intelligence"
    assert lexicon.meta.version == "1.0.0"
    assert len(lexicon.signals) >= 40
    assert len(lexicon.metrics) >= 15
    assert len(lexicon.diagnostics) == 15
    assert len(lexicon.actions) >= 35
    assert set(lexicon.policy_index) == {
        "prioritize_internal_linking",
        "stabilize_visibility_with_content_refresh",
        "accelerate_content_velocity",
    }
    assert {item.metric_id for item in lexicon.metrics if item.kind == "core_web_vital"} == {
        "cwv.lcp",
        "cwv.inp",
        "cwv.cls",
    }


def test_lexicon_rejects_dangling_action_reference() -> None:
    payload = get_builtin_lexicon().model_dump(mode="json")
    invalid = deepcopy(payload)
    invalid["diagnostics"][0]["action_ids"].append("missing.action")

    with pytest.raises(ValidationError, match="Unknown diagnostic"):
        load_lexicon_payload(invalid)


@pytest.mark.parametrize(
    ("metric_id", "value", "expected"),
    [
        ("cwv.lcp", 2500, "good"),
        ("cwv.lcp", 2500.01, "needs_improvement"),
        ("cwv.lcp", 4000, "needs_improvement"),
        ("cwv.lcp", 4000.01, "poor"),
        ("cwv.inp", 200, "good"),
        ("cwv.inp", 500.01, "poor"),
        ("cwv.cls", 0.1, "good"),
        ("cwv.cls", 0.2501, "poor"),
    ],
)
def test_metric_boundaries_are_deterministic(
    metric_id: str,
    value: float,
    expected: str,
) -> None:
    metric = get_builtin_lexicon().metric_index[metric_id]
    assert evaluate_metric(metric, value)["status"] == expected


def test_core_web_vitals_requires_all_three_good_metrics() -> None:
    lexicon = get_builtin_lexicon()

    passing = evaluate_core_web_vitals(
        lexicon,
        {"lcp": 2100, "inp": 180, "cls": "0.08", "ttfb": 700},
        form_factor="PHONE",
    )
    assert passing["assessment"]["passes_core_web_vitals"] is True
    assert passing["assessment"]["status"] == "good"
    assert passing["supporting_metrics"][0]["metric_id"] == "web_vital.ttfb"

    incomplete = evaluate_core_web_vitals(
        lexicon,
        {"lcp": 2100, "cls": 0.08},
    )
    assert incomplete["assessment"]["passes_core_web_vitals"] is None
    assert incomplete["assessment"]["status"] == "insufficient_data"
    assert incomplete["assessment"]["missing_metric_ids"] == ["cwv.inp"]


def test_core_web_vitals_returns_only_allowed_actions_for_failed_metrics() -> None:
    result = evaluate_core_web_vitals(
        get_builtin_lexicon(),
        {"lcp": 4100, "inp": 150, "cls": 0.05},
    )

    assert result["assessment"]["status"] == "poor"
    assert {item["action_id"] for item in result["recommended_actions"]} == {
        "technical.reduce_render_blocking",
        "technical.optimize_server_response",
        "technical.optimize_lcp_resource",
    }


def test_ai_context_is_an_allow_list_not_an_open_ended_prompt() -> None:
    lexicon = get_builtin_lexicon()
    context = build_ai_decision_context(
        lexicon,
        facts={"location_id": "loc-1"},
        deterministic_assessments=[{"metric_id": "cwv.lcp", "status": "poor"}],
        diagnostic_ids=["core_web_vitals_failure"],
        action_ids=["not.in.lexicon"],
    )

    assert context["contract"]["decision_authority"] == "deterministic_engine"
    assert context["contract"]["ai_role"] == "explain_prioritize_and_format_only"
    assert "not.in.lexicon" not in {item["action_id"] for item in context["allowed_actions"]}
    assert all(item["action_id"] for item in context["allowed_actions"])


def test_crux_histograms_validate_current_thresholds_and_detect_drift() -> None:
    lexicon = get_builtin_lexicon()
    payload = {
        "record": {
            "metrics": {
                "largest_contentful_paint": {
                    "histogram": [
                        {"start": 0, "end": 2500},
                        {"start": 2500, "end": 4000},
                        {"start": 4000},
                    ]
                },
                "interaction_to_next_paint": {
                    "histogram": [
                        {"start": 0, "end": 200},
                        {"start": 200, "end": 500},
                        {"start": 500},
                    ]
                },
                "cumulative_layout_shift": {
                    "histogram": [
                        {"start": "0.00", "end": "0.10"},
                        {"start": "0.10", "end": "0.25"},
                        {"start": "0.25"},
                    ]
                },
            }
        }
    }

    observed = extract_crux_thresholds(payload)
    current = compare_crux_thresholds(lexicon, observed)
    assert current["status"] == "current"
    assert current["drift"] == []
    assert current["automatic_activation_allowed"] is False

    observed["cwv.inp"]["good_boundary"] = 180
    changed = compare_crux_thresholds(lexicon, observed)
    assert changed["status"] == "review_required"
    assert changed["drift"][0]["metric_id"] == "cwv.inp"


def test_crux_standard_check_persists_a_reviewable_snapshot(db_session) -> None:
    payload = {
        "record": {
            "metrics": {
                "largest_contentful_paint": {
                    "histogram": [
                        {"start": 0, "end": 2500},
                        {"start": 2500, "end": 4000},
                        {"start": 4000},
                    ]
                },
                "interaction_to_next_paint": {
                    "histogram": [
                        {"start": 0, "end": 200},
                        {"start": 200, "end": 500},
                        {"start": 500},
                    ]
                },
                "cumulative_layout_shift": {
                    "histogram": [
                        {"start": "0.00", "end": "0.10"},
                        {"start": "0.10", "end": "0.25"},
                        {"start": "0.25"},
                    ]
                },
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "chromeuxreport.googleapis.com"
        assert request.url.params["key"] == "test-key"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run_and_record_crux_standards_check(
            db_session,
            lexicon=get_builtin_lexicon(),
            api_key="test-key",
            origin="https://web.dev",
            client=client,
        )

    assert result["status"] == "current"
    assert result["automatic_activation_allowed"] is False
    latest = latest_crux_standards_check(db_session)
    assert latest is not None
    assert latest["check_id"] == result["check_id"]
    assert latest["status"] == "current"
