from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.intelligence.recommendation_execution_engine import (
    approve_execution,
    cancel_execution,
    execute_recommendation,
    reject_execution,
    retry_execution,
)
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.schemas.executions import ExecutionApprovalIn, ExecutionOut, ExecutionRunIn

router = APIRouter(prefix='/executions', tags=['executions'])


def _tenant_scoped_execution(db: Session, execution_id: str, tenant_id: str) -> RecommendationExecution | None:
    return (
        db.query(RecommendationExecution)
        .join(StrategyRecommendation, StrategyRecommendation.id == RecommendationExecution.recommendation_id)
        .filter(
            RecommendationExecution.id == execution_id,
            StrategyRecommendation.tenant_id == tenant_id,
        )
        .first()
    )


@router.get('')
def list_executions(
    request: Request,
    campaign_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    query = (
        db.query(RecommendationExecution)
        .join(StrategyRecommendation, StrategyRecommendation.id == RecommendationExecution.recommendation_id)
        .filter(StrategyRecommendation.tenant_id == user['tenant_id'])
        .order_by(RecommendationExecution.created_at.desc(), RecommendationExecution.id.desc())
    )
    if campaign_id:
        query = query.filter(RecommendationExecution.campaign_id == campaign_id)
    if status:
        query = query.filter(RecommendationExecution.status == status)

    rows = query.limit(200).all()
    return envelope(request, {'items': [ExecutionOut.model_validate(row).model_dump(mode='json') for row in rows]})


@router.get('/{execution_id}')
def get_execution(
    request: Request,
    execution_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    row = _tenant_scoped_execution(db, execution_id, user['tenant_id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    return envelope(request, ExecutionOut.model_validate(row).model_dump(mode='json'))


@router.post('/{execution_id}/run')
def run_execution(
    request: Request,
    execution_id: str,
    body: ExecutionRunIn,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    row = _tenant_scoped_execution(db, execution_id, user['tenant_id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Execution not found')

    result = execute_recommendation(execution_id, db=db, dry_run=body.dry_run)
    if result is None:
        raise HTTPException(status_code=404, detail='Execution not found')

    refreshed = db.get(RecommendationExecution, execution_id)
    if body.dry_run:
        return envelope(
            request,
            {
                'execution': ExecutionOut.model_validate(refreshed or row).model_dump(mode='json'),
                'dry_run': True,
                'result': result,
            },
        )

    if not isinstance(result, RecommendationExecution):
        raise HTTPException(status_code=500, detail='Unexpected execution response')

    return envelope(request, ExecutionOut.model_validate(result).model_dump(mode='json'))


@router.post('/{execution_id}/retry')
def retry_execution_endpoint(
    request: Request,
    execution_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    row = _tenant_scoped_execution(db, execution_id, user['tenant_id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Execution not found')

    retried = retry_execution(execution_id, db=db)
    if retried is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    if retried.status != 'scheduled':
        return envelope(request, ExecutionOut.model_validate(retried).model_dump(mode='json'))

    executed = execute_recommendation(execution_id, db=db, dry_run=False)
    if isinstance(executed, RecommendationExecution):
        return envelope(request, ExecutionOut.model_validate(executed).model_dump(mode='json'))
    latest = db.get(RecommendationExecution, execution_id)
    if latest is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    return envelope(request, ExecutionOut.model_validate(latest).model_dump(mode='json'))


@router.post('/{execution_id}/cancel')
def cancel_execution_endpoint(
    request: Request,
    execution_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    row = _tenant_scoped_execution(db, execution_id, user['tenant_id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Execution not found')

    if row.status not in {'pending', 'scheduled'}:
        raise HTTPException(status_code=400, detail='Execution cannot be cancelled from current status')

    updated = cancel_execution(execution_id, db=db)
    if updated is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    return envelope(request, ExecutionOut.model_validate(updated).model_dump(mode='json'))


@router.post('/{execution_id}/approve')
def approve_execution_endpoint(
    request: Request,
    execution_id: str,
    body: ExecutionApprovalIn,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    row = _tenant_scoped_execution(db, execution_id, user['tenant_id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Execution not found')

    actor = body.approved_by or str(user.get('user_id') or user.get('id') or 'tenant_admin')
    updated = approve_execution(execution_id, approved_by=actor, db=db)
    if updated is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    return envelope(request, ExecutionOut.model_validate(updated).model_dump(mode='json'))


@router.post('/{execution_id}/reject')
def reject_execution_endpoint(
    request: Request,
    execution_id: str,
    body: ExecutionApprovalIn,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    row = _tenant_scoped_execution(db, execution_id, user['tenant_id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Execution not found')

    actor = body.approved_by or str(user.get('user_id') or user.get('id') or 'tenant_admin')
    updated = reject_execution(execution_id, rejected_by=actor, db=db)
    if updated is None:
        raise HTTPException(status_code=404, detail='Execution not found')
    return envelope(request, ExecutionOut.model_validate(updated).model_dump(mode='json'))
