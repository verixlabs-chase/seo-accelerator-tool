from app.events import EventType, publish_event, subscribe
from app.events.subscriber_registry import register_default_subscribers, reset_registry
from app.models.temporal import TemporalSignalSnapshot
from tests.conftest import create_test_campaign


def test_event_pipeline_signal_to_recommendation(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Event Pipeline Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Event Pipeline Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Event Pipeline Campaign',
        domain='event-pipeline.example',
    )
    db_session.commit()

    reset_registry()
    register_default_subscribers()

    seen: dict[str, int] = {'feature': 0, 'pattern': 0, 'recommendation': 0}

    subscribe(EventType.FEATURE_UPDATED.value, lambda _payload: seen.__setitem__('feature', seen['feature'] + 1))
    subscribe(EventType.PATTERN_DISCOVERED.value, lambda _payload: seen.__setitem__('pattern', seen['pattern'] + 1))
    subscribe(EventType.RECOMMENDATION_GENERATED.value, lambda _payload: seen.__setitem__('recommendation', seen['recommendation'] + 1))

    publish_event(EventType.SIGNAL_UPDATED.value, {'campaign_id': campaign.id})

    feature_rows = (
        db_session.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign.id,
            TemporalSignalSnapshot.source == 'feature_store_v1',
        )
        .count()
    )

    assert seen['feature'] >= 1
    assert seen['pattern'] >= 1
    assert seen['recommendation'] >= 1
    assert feature_rows > 0

    reset_registry()
