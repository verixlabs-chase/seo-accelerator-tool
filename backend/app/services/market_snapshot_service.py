from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.keyword_market_snapshot import KeywordMarketSnapshot

_MONEY_QUANTIZER = Decimal("0.01")


@dataclass(frozen=True)
class KeywordMarketSnapshotInput:
    keyword_id: str
    search_volume: int
    avg_cpc: Decimal
    geo_scope: str
    device_class: str
    source_provider: str
    snapshot_date: date
    confidence_score: float


def normalize_keyword_market_snapshot(snapshot_input: KeywordMarketSnapshotInput) -> dict[str, object]:
    search_volume = max(0, int(snapshot_input.search_volume))
    avg_cpc = _quantize_money(snapshot_input.avg_cpc)
    confidence_score = round(max(0.0, min(float(snapshot_input.confidence_score), 1.0)), 6)
    payload = {
        "keyword_id": snapshot_input.keyword_id,
        "search_volume": search_volume,
        "avg_cpc": format(avg_cpc, 'f'),
        "geo_scope": str(snapshot_input.geo_scope).strip(),
        "device_class": str(snapshot_input.device_class).strip().lower(),
        "source_provider": str(snapshot_input.source_provider).strip().lower(),
        "snapshot_date": snapshot_input.snapshot_date.isoformat(),
        "confidence_score": confidence_score,
    }
    return {
        **payload,
        "deterministic_hash": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }


def upsert_keyword_market_snapshot(db: Session, snapshot_input: KeywordMarketSnapshotInput) -> KeywordMarketSnapshot:
    normalized = normalize_keyword_market_snapshot(snapshot_input)
    row = (
        db.query(KeywordMarketSnapshot)
        .filter(
            KeywordMarketSnapshot.keyword_id == snapshot_input.keyword_id,
            KeywordMarketSnapshot.geo_scope == str(normalized["geo_scope"]),
            KeywordMarketSnapshot.device_class == str(normalized["device_class"]),
            KeywordMarketSnapshot.snapshot_date == snapshot_input.snapshot_date,
        )
        .first()
    )
    if row is None:
        row = KeywordMarketSnapshot(
            keyword_id=snapshot_input.keyword_id,
            search_volume=int(normalized["search_volume"]),
            avg_cpc=Decimal(str(normalized["avg_cpc"])),
            geo_scope=str(normalized["geo_scope"]),
            device_class=str(normalized["device_class"]),
            source_provider=str(normalized["source_provider"]),
            snapshot_date=snapshot_input.snapshot_date,
            confidence_score=float(normalized["confidence_score"]),
            deterministic_hash=str(normalized["deterministic_hash"]),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    if row.deterministic_hash == normalized["deterministic_hash"]:
        return row

    row.search_volume = int(normalized["search_volume"])
    row.avg_cpc = Decimal(str(normalized["avg_cpc"]))
    row.geo_scope = str(normalized["geo_scope"])
    row.device_class = str(normalized["device_class"])
    row.source_provider = str(normalized["source_provider"])
    row.confidence_score = float(normalized["confidence_score"])
    row.deterministic_hash = str(normalized["deterministic_hash"])
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


def get_latest_keyword_market_snapshot(
    db: Session,
    *,
    keyword_id: str,
    geo_scope: str,
    device_class: str,
    on_or_before: date,
) -> KeywordMarketSnapshot | None:
    return (
        db.query(KeywordMarketSnapshot)
        .filter(
            KeywordMarketSnapshot.keyword_id == keyword_id,
            KeywordMarketSnapshot.geo_scope == str(geo_scope).strip(),
            KeywordMarketSnapshot.device_class == str(device_class).strip().lower(),
            KeywordMarketSnapshot.snapshot_date <= on_or_before,
        )
        .order_by(KeywordMarketSnapshot.snapshot_date.desc(), KeywordMarketSnapshot.id.desc())
        .first()
    )


def replay_mode_enabled() -> bool:
    return os.getenv("LSOS_REPLAY_MODE", "").strip() == "1" or os.getenv("REPLAY_MODE", "").strip() == "1"


def _quantize_money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP)
