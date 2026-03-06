from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.enums import StrategyRecommendationStatus
from app.events import EventType, publish_event, subscribe
from app.events.subscriber_registry import register_default_subscribers, reset_registry
from app.intelligence.intelligence_metrics_aggregator import compute_campaign_metrics
from app.intelligence.outcome_tracker import record_outcome
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, TechnicalIssue
from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_metrics_snapshot import IntelligenceMetricsSnapshot
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.reporting import MonthlyReport
from app.models.tenant import Tenant
from app.services import onboarding_service, reporting_service
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_crawl_run, create_test_page

MASTER_KEY_B64 = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='


def _print_step(message: str) -> None:
    print(f'\u2714 {message}', flush=True)


def test_full_platform_lifecycle(db_session, monkeypatch) -> None:
    monkeypatch.setenv('PLATFORM_MASTER_KEY', MASTER_KEY_B64)
    monkeypatch.setattr('app.services.onboarding_service._dispatch_crawl_task', lambda *_args, **_kwargs: 'task-system-lifecycle')

    payload = {
        'tenant_name': f'System Tenant {uuid.uuid4().hex[:8]}',
        'organization_name': 'System Org',
        'campaign_name': 'System Campaign',
        'campaign_domain': 'system-lifecycle.example',
        'provider_name': 'google',
        'provider_auth_mode': 'api_key',
        'provider_credentials': {'api_key': 'test-key'},
        'crawl_type': 'deep',
        'crawl_seed_url': 'https://example.com',
        'report_month_number': 1,
        'automation_override': True,
    }

    session = onboarding_service.start_onboarding(db_session, payload)
    assert session.status == 'COMPLETED'
    _print_step('onboarding complete')

    tenant = db_session.get(Tenant, session.tenant_id)
    campaign = db_session.get(Campaign, session.campaign_id)
    assert tenant is not None
    assert campaign is not None

    crawl_run_id = create_test_crawl_run(db_session, campaign.id, tenant.id)
    assert crawl_run_id

    page_id = create_test_page(db_session, tenant.id, campaign.id, url='https://system-lifecycle.example/page-1')
    db_session.add(
        CrawlPageResult(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            status_code=200,
            is_indexable=1,
            title='Lifecycle Page',
            crawled_at=datetime.now(UTC),
        )
    )
    db_session.add_all(
        [
            TechnicalIssue(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                crawl_run_id=crawl_run_id,
                page_id=page_id,
                issue_code='no_internal_links',
                severity='high',
                details_json='{}',
            ),
            TechnicalIssue(
                tenant_id=tenant.id,
                campaign_id=campaign.id,
                crawl_run_id=crawl_run_id,
                page_id=page_id,
                issue_code='missing_title',
                severity='high',
                details_json='{}',
            ),
        ]
    )
    db_session.commit()
    _print_step('crawl signals ingested')

    reset_registry()
    register_default_subscribers()

    counters: dict[str, int] = {
        'feature_updated': 0,
        'pattern_discovered': 0,
        'recommendation_generated': 0,
        'simulation_completed': 0,
        'policy_updated': 0,
    }

    subscribe(EventType.FEATURE_UPDATED.value, lambda _payload: counters.__setitem__('feature_updated', counters['feature_updated'] + 1))
    subscribe(EventType.PATTERN_DISCOVERED.value, lambda _payload: counters.__setitem__('pattern_discovered', counters['pattern_discovered'] + 1))
    subscribe(
        EventType.RECOMMENDATION_GENERATED.value,
        lambda _payload: counters.__setitem__('recommendation_generated', counters['recommendation_generated'] + 1),
    )
    subscribe(
        EventType.SIMULATION_COMPLETED.value,
        lambda _payload: counters.__setitem__('simulation_completed', counters['simulation_completed'] + 1),
    )
    subscribe(EventType.POLICY_UPDATED.value, lambda _payload: counters.__setitem__('policy_updated', counters['policy_updated'] + 1))

    publish_event(EventType.SIGNAL_UPDATED.value, {'campaign_id': campaign.id})

    assert counters['feature_updated'] >= 1
    assert counters['pattern_discovered'] >= 1
    assert counters['recommendation_generated'] >= 1
    _print_step('features computed')
    _print_step('patterns detected')
    _print_step('recommendation generated')

    simulation_count = (
        db_session.query(DigitalTwinSimulation)
        .filter(DigitalTwinSimulation.campaign_id == campaign.id)
        .count()
    )
    assert simulation_count >= 1
    _print_step('digital twin simulation executed')

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='content_strategy',
        rationale='system lifecycle execution test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
        idempotency_key=f'system-lifecycle-{uuid.uuid4().hex}',
    )
    db_session.add(recommendation)
    db_session.commit()

    publish_event(
        EventType.RECOMMENDATION_GENERATED.value,
        {
            'campaign_id': campaign.id,
            'candidate_strategies': [
                {
                    'strategy_id': 'lifecycle-strategy',
                    'recommendation_id': recommendation.id,
                    'strategy_actions': [
                        {'type': 'publish_content', 'pages': 2},
                        {'type': 'fix_technical_issues', 'count': 2},
                    ],
                }
            ],
        },
    )

    execution = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.recommendation_id == recommendation.id)
        .order_by(RecommendationExecution.created_at.desc(), RecommendationExecution.id.desc())
        .first()
    )
    assert execution is not None
    _print_step('execution scheduled')

    execution.status = 'completed'
    execution.executed_at = datetime.now(UTC)
    db_session.commit()
    _print_step('execution completed')

    selected_simulation = (
        db_session.query(DigitalTwinSimulation)
        .filter(DigitalTwinSimulation.campaign_id == campaign.id, DigitalTwinSimulation.selected_strategy.is_(True))
        .order_by(DigitalTwinSimulation.created_at.desc(), DigitalTwinSimulation.id.desc())
        .first()
    )
    assert selected_simulation is not None

    outcome = record_outcome(
        db_session,
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        simulation_id=selected_simulation.id,
        metric_before=10.0,
        metric_after=12.0,
    )
    assert outcome is not None
    _print_step('outcome recorded')

    snapshot = compute_campaign_metrics(campaign.id, db=db_session)
    assert snapshot is not None
    assert snapshot.prediction_accuracy_score >= 0.0
    _print_step('prediction accuracy computed')

    assert counters['policy_updated'] >= 1
    _print_step('policy learning updated')

    metrics_row = (
        db_session.query(IntelligenceMetricsSnapshot)
        .filter(IntelligenceMetricsSnapshot.campaign_id == campaign.id)
        .order_by(IntelligenceMetricsSnapshot.metric_date.desc(), IntelligenceMetricsSnapshot.id.desc())
        .first()
    )
    assert metrics_row is not None
    _print_step('metrics snapshot created')

    report = reporting_service.generate_report(db_session, tenant.id, campaign.id, month_number=1)
    assert report is not None
    assert isinstance(report, MonthlyReport)
    assert report.report_status == 'generated'
    _print_step('report generation works')

    assert tenant is not None
    assert campaign is not None
    assert crawl_run_id
    assert simulation_count >= 1

    linked_outcome = db_session.get(RecommendationOutcome, outcome.id)
    assert linked_outcome is not None
    assert linked_outcome.simulation_id == selected_simulation.id

    reset_registry()
