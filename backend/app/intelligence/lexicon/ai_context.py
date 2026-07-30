from __future__ import annotations

from typing import Any

from app.intelligence.lexicon.schema import IntelligenceLexicon


def build_ai_decision_context(
    lexicon: IntelligenceLexicon,
    *,
    facts: dict[str, Any],
    deterministic_assessments: list[dict[str, Any]],
    diagnostic_ids: list[str] | None = None,
    action_ids: list[str] | None = None,
) -> dict[str, Any]:
    diagnostics = [
        lexicon.diagnostic_index[item]
        for item in sorted(set(diagnostic_ids or []))
        if item in lexicon.diagnostic_index
    ]
    allowed_action_ids = set(action_ids or [])
    for diagnostic in diagnostics:
        allowed_action_ids.update(diagnostic.action_ids)
    actions = [
        lexicon.action_index[item]
        for item in sorted(allowed_action_ids)
        if item in lexicon.action_index and lexicon.action_index[item].ai_allowed
    ]

    return {
        "contract": {
            "name": "deterministic_seo_intelligence_context",
            "version": "1.0",
            "lexicon_id": lexicon.meta.lexicon_id,
            "lexicon_version": lexicon.meta.version,
            "decision_authority": "deterministic_engine",
            "ai_role": "explain_prioritize_and_format_only",
        },
        "non_negotiable_rules": [
            "Use only supplied facts, assessments, diagnostics, actions, and sources.",
            "Never invent a metric, threshold, diagnosis, action, causal claim, or business outcome.",
            "Never replace an insufficient_data state with an estimate.",
            "Do not claim that Core Web Vitals guarantee rankings.",
            "Do not select an action outside allowed_actions.",
            "Preserve risk tier, approval requirement, evidence, and lexicon version.",
            "State uncertainty in plain language when evidence is incomplete or stale.",
        ],
        "facts": facts,
        "deterministic_assessments": deterministic_assessments,
        "diagnostics": [
            {
                "diagnostic_id": item.diagnostic_id,
                "business_label": item.business_label,
                "diagnosis": item.diagnosis,
                "root_cause_hypotheses": list(item.root_cause_hypotheses),
                "expected_outcome": item.expected_outcome,
                "impact_level": item.impact_level,
                "source_ids": list(item.source_ids),
            }
            for item in diagnostics
        ],
        "allowed_actions": [
            {
                "action_id": item.action_id,
                "display_name": item.display_name,
                "why_it_matters": item.why_it_matters,
                "steps": list(item.steps),
                "risk_tier": item.risk_tier,
                "effort": item.effort,
                "owner_role": item.owner_role,
                "success_metric_ids": list(item.success_metric_ids),
                "observation_window_days": item.observation_window_days,
            }
            for item in actions
        ],
        "sources": {
            source_id: {
                "publisher": source.publisher,
                "title": source.title,
                "url": str(source.url),
                "last_verified_at": source.last_verified_at.isoformat(),
            }
            for source_id, source in lexicon.source_index.items()
            if source_id in {referenced for item in diagnostics for referenced in item.source_ids}
            or source_id in {referenced for item in actions for referenced in item.source_ids}
        },
        "required_output": {
            "summary": "plain-language statement grounded in supplied facts",
            "why_now": "evidence-backed urgency without unsupported causal language",
            "selected_action_id": "one ID from allowed_actions or null",
            "evidence_used": ["fact or deterministic assessment identifiers"],
            "uncertainties": ["missing, stale, or insufficient evidence"],
            "approval_required": "true when selected action risk_tier is 2 or higher",
        },
    }
