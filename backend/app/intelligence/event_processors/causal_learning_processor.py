from __future__ import annotations

from app.db.session import SessionLocal
from app.intelligence.workers.causal_worker import process as process_causal_worker


def process(payload: dict[str, object]) -> dict[str, object]:
    session = SessionLocal()
    try:
        result = process_causal_worker(session, payload)
        session.commit()
        return result
    finally:
        session.close()
