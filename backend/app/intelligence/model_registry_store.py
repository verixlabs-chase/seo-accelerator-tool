from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.intelligence_model_registry import IntelligenceModelRegistryState


def get_registry_payload(registry_name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    session = SessionLocal()
    try:
        row = session.get(IntelligenceModelRegistryState, registry_name)
        if row is None:
            return deepcopy(defaults)
        payload = row.payload if isinstance(row.payload, dict) else {}
        return _merge_dicts(deepcopy(defaults), payload)
    finally:
        session.close()


def replace_registry_payload(registry_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = SessionLocal()
    try:
        _replace_registry_payload(session, registry_name, payload)
        session.commit()
        row = session.get(IntelligenceModelRegistryState, registry_name)
        return deepcopy(row.payload if row is not None and isinstance(row.payload, dict) else {})
    finally:
        session.close()


def update_registry_payload(registry_name: str, updates: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    session = SessionLocal()
    try:
        current = _get_or_create_payload(session, registry_name, defaults)
        _merge_in_place(current, updates)
        _replace_registry_payload(session, registry_name, current)
        session.commit()
        return deepcopy(current)
    finally:
        session.close()


def reset_registry_payload(registry_name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    return replace_registry_payload(registry_name, deepcopy(defaults))


def get_registry_state(registry_name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    return get_registry_payload(registry_name, defaults)


def _get_or_create_payload(session: Session, registry_name: str, defaults: dict[str, Any]) -> dict[str, Any]:
    row = session.get(IntelligenceModelRegistryState, registry_name)
    if row is None:
        return deepcopy(defaults)
    payload = row.payload if isinstance(row.payload, dict) else {}
    return _merge_dicts(deepcopy(defaults), payload)


def _replace_registry_payload(session: Session, registry_name: str, payload: dict[str, Any]) -> None:
    row = session.get(IntelligenceModelRegistryState, registry_name)
    if row is None:
        row = IntelligenceModelRegistryState(registry_name=registry_name, payload=deepcopy(payload))
        session.add(row)
        session.flush()
        return
    row.payload = deepcopy(payload)
    session.flush()


def _merge_dicts(target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    _merge_in_place(target, updates)
    return target


def _merge_in_place(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_in_place(target[key], value)
            continue
        target[key] = deepcopy(value)
