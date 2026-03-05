from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.strategy_memory_pattern import StrategyMemoryPattern
from app.schemas.strategy_memory import StrategyMemoryPatternOut

router = APIRouter(prefix='/strategy-memory', tags=['strategy-memory'])


@router.get('/patterns')
def list_memory_patterns(
    request: Request,
    feature_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_roles({'tenant_admin'})),
) -> dict:
    _ = user
    query = db.query(StrategyMemoryPattern).order_by(StrategyMemoryPattern.updated_at.desc(), StrategyMemoryPattern.id.desc())
    if feature_name:
        query = query.filter(StrategyMemoryPattern.feature_name == feature_name)
    rows = query.limit(200).all()
    return envelope(request, {'items': [StrategyMemoryPatternOut.model_validate(row).model_dump(mode='json') for row in rows]})


@router.get('/patterns/top')
def top_memory_patterns(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: dict = Depends(require_roles({'tenant_admin'})),
) -> dict:
    _ = user
    rows = (
        db.query(StrategyMemoryPattern)
        .order_by(
            StrategyMemoryPattern.confidence_score.desc(),
            StrategyMemoryPattern.support_count.desc(),
            StrategyMemoryPattern.updated_at.desc(),
        )
        .limit(limit)
        .all()
    )
    return envelope(request, {'items': [StrategyMemoryPatternOut.model_validate(row).model_dump(mode='json') for row in rows]})


@router.get('/patterns/{pattern_id}')
def get_memory_pattern(
    request: Request,
    pattern_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_roles({'tenant_admin'})),
) -> dict:
    _ = user
    row = db.get(StrategyMemoryPattern, pattern_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Strategy memory pattern not found')
    return envelope(request, StrategyMemoryPatternOut.model_validate(row).model_dump(mode='json'))
