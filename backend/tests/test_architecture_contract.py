from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / 'app'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_portfolio_reads_from_knowledge_graph_query_engine() -> None:
    text = _read(APP_ROOT / 'intelligence' / 'portfolio' / 'portfolio_engine.py')
    assert 'from app.intelligence.knowledge_graph.query_engine import get_policy_preference_map' in text
    assert 'get_policy_preference_map(db, updated.industry)' in text


def test_causal_learning_writes_through_knowledge_graph_update_engine() -> None:
    text = _read(APP_ROOT / 'intelligence' / 'causal' / 'causal_learning_engine.py')
    assert 'update_global_knowledge_graph' in text
    assert 'update_global_knowledge_graph(' in text


def test_no_module_outside_knowledge_graph_writes_knowledge_edges_directly() -> None:
    violations: list[str] = []
    graph_root = APP_ROOT / 'intelligence' / 'knowledge_graph'
    direct_patterns = (
        'db.add(KnowledgeEdge',
        'session.add(KnowledgeEdge',
        'insert(KnowledgeEdge',
        'db.execute(insert(KnowledgeEdge',
    )
    for path in APP_ROOT.rglob('*.py'):
        if graph_root in path.parents:
            continue
        text = _read(path)
        if any(pattern in text for pattern in direct_patterns):
            violations.append(str(path.relative_to(APP_ROOT)))
    assert violations == []


def test_legacy_learning_modules_are_not_executed_by_runtime_hooks() -> None:
    outbox_worker = _read(APP_ROOT / 'intelligence' / 'workers' / 'outbox_worker.py')
    learning_worker = _read(APP_ROOT / 'intelligence' / 'workers' / 'learning_worker.py')
    event_integration = _read(APP_ROOT / 'intelligence' / 'event_integration.py')
    outcome_processor = _read(APP_ROOT / 'intelligence' / 'event_processors' / 'outcome_processor.py')

    assert 'app.intelligence.event_integration' not in outbox_worker
    assert 'policy_update_engine' not in learning_worker
    assert 'network_learning' not in learning_worker
    assert 'strategy_evolution' not in learning_worker
    assert 'return None' in event_integration
    assert 'network_learning' not in outcome_processor
    assert 'get_graph_update_pipeline' not in outcome_processor
    assert 'get_industry_learning_pipeline' not in outcome_processor
    assert 'publish_event(EventType.OUTCOME_RECORDED.value' not in outcome_processor

