from __future__ import annotations

from app.db.session import SessionLocal
from app.intelligence.workers.evolution_worker import process as process_evolution_worker


def process(payload: dict[str, object]) -> dict[str, object]:
    session = SessionLocal()
    try:
        result = process_evolution_worker(session, payload)
        session.commit()
        return result
    finally:
        session.close()
