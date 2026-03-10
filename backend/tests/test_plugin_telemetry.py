import pytest

from app.intelligence.executors.plugin_telemetry import (
    PluginTelemetryError,
    block_execution_if_plugin_unhealthy,
    detect_plugin_failure,
    track_plugin_health,
    validate_mutation_batch,
    verify_plugin_version,
    verify_rollback_payloads,
)


def test_plugin_health_tracking_blocks_unhealthy_sites(db_session) -> None:
    track_plugin_health(db_session, tenant_id='tenant-1', site_id='site-1', plugin_version='1.2.0', healthy=True)
    block_execution_if_plugin_unhealthy(db_session, tenant_id='tenant-1', site_id='site-1')

    detect_plugin_failure(db_session, tenant_id='tenant-1', site_id='site-1', reason_code='timeout', plugin_version='1.2.0')
    with pytest.raises(PluginTelemetryError):
        block_execution_if_plugin_unhealthy(db_session, tenant_id='tenant-1', site_id='site-1')


def test_plugin_mutation_guards_validate_batches() -> None:
    validate_mutation_batch(
        [
            {'target_url': '/services/roof-repair', 'payload': {'selector': '.content'}, 'action': 'insert_internal_link'},
        ]
    )
    with pytest.raises(PluginTelemetryError):
        validate_mutation_batch([{'target_url': '/checkout', 'payload': {}, 'action': 'insert_internal_link'}])

    assert verify_plugin_version({'plugin_version': '1.3.0'})

    verify_rollback_payloads(
        [
            {
                'rollback_payload': {'restore': True},
                'before_state': {'title': 'before'},
                'after_state': {'title': 'after'},
            }
        ]
    )
