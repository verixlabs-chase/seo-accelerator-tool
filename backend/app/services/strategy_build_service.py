from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.governance.replay.hashing import build_hash, input_hash, output_hash, version_fingerprint
from app.intelligence.feature_store import compute_features
from app.intelligence.pattern_engine import detect_patterns, discover_cohort_patterns
from app.intelligence.policy_engine import derive_policy, generate_recommendations, score_policy
from app.intelligence.signal_assembler import assemble_signals
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.organization import Organization
from app.models.strategy_execution_key import StrategyExecutionKey
from app.services.idempotency_service import (
    claim_pending_execution,
    get_or_create_execution,
    mark_execution_failed,
    persist_execution_result,
)
from app.services.strategy_engine.engine import build_campaign_strategy
from app.services.strategy_engine.profile import resolve_strategy_profile
from app.services.strategy_engine.schemas import CampaignStrategyOut, StrategyWindow
from app.services.strategy_engine.temporal_integration import integrate_temporal_state
from app.services.strategy_engine.thresholds import version_id as threshold_version
from app.enums import StrategyRecommendationStatus
from app.utils.enum_guard import ensure_enum

_REGISTRY_VERSION = 'scenario-registry-v1'
_SIGNAL_SCHEMA_VERSION = 'signals-v1'
_TERMINAL_RECOMMENDATION_STATUS = StrategyRecommendationStatus.ARCHIVED


def build_campaign_strategy_idempotent(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    window: StrategyWindow,
    raw_signals: dict[str, Any],
    tier: str,
) -> CampaignStrategyOut:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Campaign not found')
    if campaign.organization_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Campaign organization is not configured')

    organization = db.get(Organization, campaign.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Organization not found')
    if organization.status.strip().lower() != 'active':
        return CampaignStrategyOut(
            campaign_id=campaign_id,
            window=window,
            detected_scenarios=[],
            recommendations=[],
            strategic_scores=None,
            executive_summary=None,
            meta={'status': 'failed', 'reason_code': 'ORG_INACTIVE'},
        )

    assembled_signals = assemble_signals(campaign_id, db=db)
    if raw_signals:
        assembled_signals.update(raw_signals)

    learning_context = _build_learning_pipeline_context(db=db, campaign_id=campaign_id)

    request_payload = {
        'campaign_id': campaign_id,
        'window': {'date_from': window.date_from.isoformat(), 'date_to': window.date_to.isoformat()},
        'raw_signals': assembled_signals,
        'tier': tier,
        'learning_context': {
            'feature_fingerprint': learning_context['feature_fingerprint'],
            'pattern_keys': learning_context['pattern_keys'],
            'policy_ids': learning_context['policy_ids'],
        },
    }
    in_hash = input_hash(request_payload)
    profile = resolve_strategy_profile(tier)
    profile_hash = profile.version_hash()
    version_tuple = {
        'engine_version': 'phase3-deterministic-policy-pipeline',
        'threshold_bundle_version': threshold_version,
        'registry_version': _REGISTRY_VERSION,
        'signal_schema_version': _SIGNAL_SCHEMA_VERSION,
        'profile_version_hash': profile_hash,
    }
    version_hash = version_fingerprint(version_tuple)
    idem_key = f'{campaign_id}:{window.date_from.isoformat()}:{window.date_to.isoformat()}:{tier}'

    execution, _ = get_or_create_execution(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        operation_type='strategy_build',
        idempotency_key=idem_key,
        input_hash=in_hash,
        version_fingerprint=version_hash,
    )

    if execution.status == 'completed' and execution.output_payload_json:
        payload = json.loads(execution.output_payload_json)
        return CampaignStrategyOut.model_validate(payload)

    if execution.status == 'running':
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Strategy build already running for this idempotency key')

    if execution.status == 'failed':
        _reset_failed_to_pending(db, execution.id)

    claimed = claim_pending_execution(db, execution_id=execution.id)
    if claimed is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Strategy build execution is locked by another worker')

    try:
        output = build_campaign_strategy(
            campaign_id=campaign_id,
            window=window,
            raw_signals=assembled_signals,
            tier=tier,
            db=db,
        )
        payload = output.model_dump(mode='json')
        temporal_visibility = integrate_temporal_state(
            db,
            campaign_id=campaign_id,
            window=window,
            profile=profile,
            payload=payload,
        )
        out_hash = output_hash(payload)
        meta = payload.setdefault('meta', {})
        meta['threshold_bundle_version'] = threshold_version
        meta['registry_version'] = _REGISTRY_VERSION
        meta['signal_schema_version'] = _SIGNAL_SCHEMA_VERSION
        meta['input_hash'] = in_hash
        meta['output_hash'] = out_hash
        meta['version_fingerprint'] = version_hash
        meta['profile_version_hash'] = profile_hash
        meta['build_hash'] = build_hash(input_digest=in_hash, output_digest=out_hash, version_digest=version_hash)
        meta['learning_pipeline'] = {
            'features': learning_context['features'],
            'patterns': learning_context['patterns'],
            'policies': learning_context['policies'],
            'policy_recommendations': learning_context['policy_recommendations'],
        }
        if temporal_visibility is not None:
            meta['temporal'] = temporal_visibility

        persist_execution_result(db, execution_id=execution.id, output_hash=out_hash, output_payload=payload)
        _persist_strategy_recommendation_metadata(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            idempotency_key=idem_key,
            input_hash=in_hash,
            output_hash=out_hash,
            version_tuple=version_tuple,
            build_hash_value=payload['meta']['build_hash'],
        )

        return CampaignStrategyOut.model_validate(payload)
    except Exception as exc:
        mark_execution_failed(db, execution_id=execution.id, error_message=str(exc))
        raise


def _build_learning_pipeline_context(db: Session, *, campaign_id: str) -> dict[str, Any]:
    features = compute_features(campaign_id, db=db, persist=False)
    pattern_matches = [
        {
            'pattern_key': item.pattern_key,
            'confidence': item.confidence,
            'evidence': item.evidence,
        }
        for item in detect_patterns(features)
    ]
    pattern_matches.extend(discover_cohort_patterns(db, campaign_id=campaign_id, features=features))

    policies = [score_policy(policy, features) for policy in derive_policy(pattern_matches)]
    policy_recommendations = [
        recommendation
        for policy in policies
        for recommendation in generate_recommendations(policy)
    ]

    feature_fingerprint = {
        key: round(float(value), 6)
        for key, value in sorted(features.items())
        if isinstance(value, (int, float))
    }

    return {
        'features': feature_fingerprint,
        'patterns': pattern_matches,
        'pattern_keys': sorted({str(item['pattern_key']) for item in pattern_matches}),
        'policies': policies,
        'policy_ids': sorted({str(item['policy_id']) for item in policies}),
        'policy_recommendations': policy_recommendations,
        'feature_fingerprint': feature_fingerprint,
    }


def _reset_failed_to_pending(db: Session, execution_id: str) -> None:
    from datetime import UTC, datetime

    row = db.get(StrategyExecutionKey, execution_id)
    if row is None or row.status != 'failed':
        return
    row.status = 'pending'
    row.updated_at = datetime.now(UTC)
    db.commit()


def _persist_strategy_recommendation_metadata(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    idempotency_key: str,
    input_hash: str,
    output_hash: str,
    version_tuple: dict[str, str],
    build_hash_value: str,
) -> None:
    existing = (
        db.query(StrategyRecommendation)
        .filter(
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
            StrategyRecommendation.idempotency_key == idempotency_key,
        )
        .order_by(StrategyRecommendation.created_at.desc())
        .first()
    )

    rollback_payload = {
        'steps': [
            'rebuild_strategy_with_prior_tuple',
            'invalidate_conflicting_cached_payloads',
        ]
    }

    if existing is None:
        existing = StrategyRecommendation(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            recommendation_type='strategy_bundle_record',
            rationale='Deterministic strategy build artifact record',
            confidence=1.0,
            confidence_score=1.0,
            evidence_json=json.dumps(['deterministic_strategy_build']),
            risk_tier=0,
            rollback_plan_json=json.dumps(rollback_payload),
            status=ensure_enum(_TERMINAL_RECOMMENDATION_STATUS, StrategyRecommendationStatus),
            idempotency_key=idempotency_key,
        )
        db.add(existing)

    existing.engine_version = version_tuple['engine_version']
    existing.threshold_bundle_version = version_tuple['threshold_bundle_version']
    existing.registry_version = version_tuple['registry_version']
    existing.signal_schema_version = version_tuple['signal_schema_version']
    existing.input_hash = input_hash
    existing.output_hash = output_hash
    existing.build_hash = build_hash_value
    db.commit()
