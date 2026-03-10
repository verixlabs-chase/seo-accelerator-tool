from __future__ import annotations

import logging
import time

from app.db.session import SessionLocal
from app.intelligence.cohort_pattern_engine import discover_cohort_patterns as discover_learning_cohort_patterns
from app.intelligence.digital_twin.models.training_pipeline import train_prediction_models
from app.intelligence.intelligence_metrics_aggregator import compute_system_metrics
from app.intelligence.intelligence_orchestrator import run_campaign_cycle, run_system_cycle
from app.intelligence.workers import run_worker
from app.tasks.celery_app import celery_app


logger = logging.getLogger('lsos.intelligence.tasks')
_WORKER_RETRY_BACKOFF_SECONDS = (0.1, 0.2, 0.4)


@celery_app.task(name='intelligence.run_campaign_cycle')
def run_campaign_intelligence_cycle(campaign_id: str) -> dict:
    db = SessionLocal()
    try:
        return run_campaign_cycle(campaign_id, db=db)
    finally:
        db.close()


@celery_app.task(name='intelligence.run_system_cycle')
def run_system_intelligence_cycle() -> dict:
    db = SessionLocal()
    try:
        return run_system_cycle(db=db)
    finally:
        db.close()


@celery_app.task(name='intelligence.recompute_system_metrics')
def recompute_system_intelligence_metrics() -> dict:
    db = SessionLocal()
    try:
        return compute_system_metrics(db=db)
    finally:
        db.close()


@celery_app.task(name='intelligence.discover_weekly_cohort_patterns')
def run_weekly_cohort_pattern_discovery() -> dict:
    db = SessionLocal()
    try:
        rows = discover_learning_cohort_patterns(db, persist=True)
        return {
            'patterns_discovered': len(rows),
            'pattern_ids': sorted([row.id for row in rows]),
        }
    finally:
        db.close()


@celery_app.task(name='intelligence.train_digital_twin_models')
def train_digital_twin_models_task() -> dict:
    db = SessionLocal()
    try:
        return train_prediction_models(db)
    finally:
        db.close()


@celery_app.task(name='intelligence.run_worker')
def run_intelligence_worker_task(worker_name: str, payload: dict) -> dict:
    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0, *_WORKER_RETRY_BACKOFF_SECONDS), start=1):
        if delay:
            time.sleep(delay)
        try:
            return run_worker(worker_name, payload)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.exception(
                'intelligence_worker_failure',
                extra={'worker_name': worker_name, 'attempt': attempt},
            )
    if last_error is not None:
        raise last_error
    raise RuntimeError(f'Worker failed without error: {worker_name}')
