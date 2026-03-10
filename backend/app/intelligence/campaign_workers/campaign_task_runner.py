from __future__ import annotations

from app.db.session import SessionLocal
from app.tasks.celery_app import celery_app


@celery_app.task(name='intelligence.process_campaign')
def process_campaign(campaign_id: str) -> dict:
    from app.intelligence.intelligence_orchestrator import run_campaign_cycle

    db = SessionLocal()
    try:
        return run_campaign_cycle(campaign_id, db=db)
    finally:
        db.close()
