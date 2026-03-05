from app.intelligence.executors.registry import get_executor, list_execution_types


EXPECTED_TYPES = {
    'create_content_brief',
    'improve_internal_links',
    'fix_missing_title',
    'optimize_gbp_profile',
    'publish_schema_markup',
}


def test_registry_lists_supported_execution_types() -> None:
    assert set(list_execution_types()) == EXPECTED_TYPES


def test_registry_returns_executor_for_each_type() -> None:
    for execution_type in EXPECTED_TYPES:
        executor = get_executor(execution_type)
        assert executor.execution_type == execution_type


def test_registry_rejects_unknown_execution_type() -> None:
    try:
        get_executor('unknown_execution_type')
    except ValueError as exc:
        assert 'Unsupported execution_type' in str(exc)
    else:
        raise AssertionError('Expected ValueError for unknown execution type')
