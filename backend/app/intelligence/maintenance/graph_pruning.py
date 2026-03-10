from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.experiment import ExperimentOutcome
from app.models.knowledge_graph import KnowledgeEdge
from app.models.strategy_evolution_log import StrategyEvolutionLog

_ARCHIVE_ROOT = Path(__file__).resolve().parents[3] / 'artifacts' / 'maintenance_archives'


def _archive_rows(name: str, rows: list[dict[str, object]]) -> str | None:
    if not rows:
        return None
    _ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime('%Y%m%d%H%M%S')
    path = _ARCHIVE_ROOT / f'{name}_{timestamp}.jsonl'
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str))
            handle.write('\n')
    return str(path)


def prune_graph_history(db: Session, *, now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(UTC)
    edge_cutoff = current - timedelta(days=365)
    outcome_cutoff = current - timedelta(days=548)
    evolution_cutoff = current - timedelta(days=365)

    stale_edges = (
        db.query(KnowledgeEdge)
        .filter(KnowledgeEdge.updated_at < edge_cutoff)
        .all()
    )
    stale_outcomes = (
        db.query(ExperimentOutcome)
        .filter(ExperimentOutcome.measured_at < outcome_cutoff)
        .all()
    )
    stale_evolution = (
        db.query(StrategyEvolutionLog)
        .filter(StrategyEvolutionLog.created_at < evolution_cutoff)
        .all()
    )

    archived = {
        'knowledge_edges': _archive_rows(
            'knowledge_edges',
            [
                {
                    'id': row.id,
                    'source_node_id': row.source_node_id,
                    'target_node_id': row.target_node_id,
                    'edge_type': row.edge_type,
                    'industry': row.industry,
                    'updated_at': row.updated_at,
                }
                for row in stale_edges
            ],
        ),
        'experiment_outcomes': _archive_rows(
            'experiment_outcomes',
            [
                {
                    'id': row.id,
                    'experiment_id': row.experiment_id,
                    'campaign_id': row.campaign_id,
                    'measured_at': row.measured_at,
                }
                for row in stale_outcomes
            ],
        ),
        'strategy_evolution_logs': _archive_rows(
            'strategy_evolution_logs',
            [
                {
                    'id': row.id,
                    'parent_policy': row.parent_policy,
                    'new_policy': row.new_policy,
                    'created_at': row.created_at,
                }
                for row in stale_evolution
            ],
        ),
    }

    for row in stale_edges:
        db.delete(row)
    for row in stale_outcomes:
        db.delete(row)
    for row in stale_evolution:
        db.delete(row)
    db.flush()

    return {
        'archived_files': archived,
        'deleted': {
            'knowledge_edges': len(stale_edges),
            'experiment_outcomes': len(stale_outcomes),
            'strategy_evolution_logs': len(stale_evolution),
        },
        'cutoffs': {
            'knowledge_edges': edge_cutoff.isoformat(),
            'experiment_outcomes': outcome_cutoff.isoformat(),
            'strategy_evolution_logs': evolution_cutoff.isoformat(),
        },
    }
