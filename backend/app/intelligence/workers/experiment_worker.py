from __future__ import annotations

from app.db.session import SessionLocal
from app.intelligence.workers.causal_worker import process as process_causal_worker
from app.intelligence.workers.evolution_worker import process as process_evolution_worker


def process(payload: dict[str, object]) -> dict[str, object]:
    session = SessionLocal()
    try:
        causal = process_causal_worker(session, payload)
        evolution = process_evolution_worker(session, payload)
        session.commit()
        return {
            'causal': causal,
            'evolution': evolution,
        }
    finally:
        session.close()
