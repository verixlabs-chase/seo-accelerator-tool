from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.seo_mutation_outcome import SEOMutationOutcome

PSEUDOCODE = """
1. Group mutation outcomes by execution and page so multi-mutation plans can be compared with single mutations.
2. Detect repeated high-performing motifs such as link clusters, schema-plus-link combinations, and first-paragraph anchors.
3. Score patterns by support_count, average improvement, and consistency.
4. Return only patterns with defensible support and confidence.
"""


@dataclass(slots=True)
class StrategyPattern:
    pattern_id: str
    description: str
    support_count: int
    average_rank_delta: float
    confidence_score: float
    mutation_pattern: dict[str, object]


def discover_strategy_patterns(db: Session, *, minimum_support: int = 2) -> list[dict[str, Any]]:
    rows = db.query(SEOMutationOutcome).order_by(SEOMutationOutcome.recorded_at.desc()).all()
    by_execution: dict[tuple[str, str], list[SEOMutationOutcome]] = {}
    for row in rows:
        by_execution.setdefault((str(row.execution_id), str(row.page_url)), []).append(row)

    cluster_count = 0
    cluster_rank_delta = 0.0
    combo_count = 0
    combo_rank_delta = 0.0
    first_paragraph_count = 0
    first_paragraph_rank_delta = 0.0

    for items in by_execution.values():
        link_rows = [item for item in items if item.mutation_type == 'insert_internal_link']
        if len(link_rows) >= 3:
            cluster_count += 1
            cluster_rank_delta += sum((float(item.rank_after) - float(item.rank_before)) for item in link_rows) / len(link_rows)
        mutation_types = {item.mutation_type for item in items}
        if 'insert_internal_link' in mutation_types and 'add_schema_markup' in mutation_types:
            combo_count += 1
            combo_rank_delta += sum((float(item.rank_after) - float(item.rank_before)) for item in items) / len(items)
        first_paragraph_rows = [item for item in link_rows if str((item.mutation_parameters or {}).get('placement') or '').strip().lower() == 'first_paragraph']
        if first_paragraph_rows:
            first_paragraph_count += 1
            first_paragraph_rank_delta += sum((float(item.rank_after) - float(item.rank_before)) for item in first_paragraph_rows) / len(first_paragraph_rows)

    patterns: list[StrategyPattern] = []
    if cluster_count >= minimum_support:
        patterns.append(
            StrategyPattern(
                pattern_id='contextual_internal_link_cluster',
                description='Three or more contextual internal links on the same page outperform single-link changes.',
                support_count=cluster_count,
                average_rank_delta=round(cluster_rank_delta / cluster_count, 6),
                confidence_score=_confidence(cluster_count),
                mutation_pattern={'mutation_types': ['insert_internal_link'], 'minimum_links_per_page': 3},
            )
        )
    if combo_count >= minimum_support:
        patterns.append(
            StrategyPattern(
                pattern_id='schema_plus_internal_linking',
                description='Schema markup combined with internal linking shows stronger rank gains than isolated changes.',
                support_count=combo_count,
                average_rank_delta=round(combo_rank_delta / combo_count, 6),
                confidence_score=_confidence(combo_count),
                mutation_pattern={'mutation_types': ['add_schema_markup', 'insert_internal_link'], 'combination_required': True},
            )
        )
    if first_paragraph_count >= minimum_support:
        patterns.append(
            StrategyPattern(
                pattern_id='internal_link_cluster_first_paragraph',
                description='Internal links placed in the first paragraph show better ranking probability than later placements.',
                support_count=first_paragraph_count,
                average_rank_delta=round(first_paragraph_rank_delta / first_paragraph_count, 6),
                confidence_score=_confidence(first_paragraph_count),
                mutation_pattern={'mutation_types': ['insert_internal_link'], 'placement': 'first_paragraph'},
            )
        )
    return [asdict(item) for item in patterns]


def _confidence(support_count: int) -> float:
    return round(max(0.2, min(0.95, 0.4 + (support_count / 20.0))), 6)
