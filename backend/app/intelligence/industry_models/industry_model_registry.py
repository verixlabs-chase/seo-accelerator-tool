from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.intelligence.industry_models.industry_schema import IndustryModel
from app.models.industry_intelligence import IndustryIntelligenceModel


class IndustryModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, IndustryModel] = {}
        self._pattern_counts: dict[str, dict[str, int]] = {}
        self._strategy_successes: dict[str, dict[str, float]] = {}
        self._strategy_support: dict[str, dict[str, float]] = {}

    def register_industry_model(
        self,
        industry_id: str,
        industry_name: str | None = None,
        session: Session | None = None,
    ) -> IndustryModel:
        del session
        key = _normalize_industry(industry_id)
        existing = self._models.get(key)
        if existing is not None:
            return existing

        model = IndustryModel(
            industry_id=key,
            industry_name=industry_name or key,
            pattern_distribution={},
            strategy_success_rates={},
            avg_rank_delta=0.0,
            avg_traffic_delta=0.0,
            confidence_score=0.0,
            sample_size=0,
        )
        self._models[key] = model
        self._pattern_counts.setdefault(key, {})
        self._strategy_successes.setdefault(key, {})
        self._strategy_support.setdefault(key, {})
        return model

    def get_industry_model(self, industry_id: str, session: Session | None = None) -> IndustryModel | None:
        del session
        return self._models.get(_normalize_industry(industry_id))

    def update_industry_model(self, industry_id: str, session: Session | None = None, **updates: object) -> IndustryModel:
        del session
        model = self.register_industry_model(industry_id)
        for field_name, value in updates.items():
            if hasattr(model, field_name):
                setattr(model, field_name, value)
        model.last_updated = datetime.now(UTC).isoformat()
        return model

    def list_industries(self, session: Session | None = None) -> list[str]:
        del session
        return sorted(self._models.keys())

    def increment_pattern(self, industry_id: str, pattern_key: str, session: Session | None = None) -> IndustryModel:
        del session
        model = self.register_industry_model(industry_id)
        counts = self._pattern_counts.setdefault(model.industry_id, {})
        key = str(pattern_key).strip().lower()
        counts[key] = counts.get(key, 0) + 1
        total = sum(counts.values())
        model.pattern_distribution = {
            item: round(count / max(total, 1), 6)
            for item, count in sorted(counts.items())
        }
        model.last_updated = datetime.now(UTC).isoformat()
        return model

    def record_strategy_outcome(
        self,
        industry_id: str,
        strategy: str,
        success_weight: float,
        support_weight: float,
        session: Session | None = None,
    ) -> IndustryModel:
        del session
        model = self.register_industry_model(industry_id)
        strategy_key = str(strategy).strip().lower()
        successes = self._strategy_successes.setdefault(model.industry_id, {})
        support = self._strategy_support.setdefault(model.industry_id, {})

        successes[strategy_key] = float(successes.get(strategy_key, 0.0)) + float(success_weight)
        support[strategy_key] = float(support.get(strategy_key, 0.0)) + float(support_weight)

        model.strategy_success_rates = {
            key: round(float(successes.get(key, 0.0)) / max(float(support.get(key, 0.0)), 1.0), 6)
            for key in sorted(support.keys())
        }
        model.last_updated = datetime.now(UTC).isoformat()
        return model


class PersistentIndustryModelRegistry:
    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def register_industry_model(
        self,
        industry_id: str,
        industry_name: str | None = None,
        session: Session | None = None,
    ) -> IndustryModel:
        if session is not None:
            return self._register(session, industry_id, industry_name)
        with self.session_scope() as managed:
            return self._register(managed, industry_id, industry_name)

    def get_industry_model(self, industry_id: str, session: Session | None = None) -> IndustryModel | None:
        if session is not None:
            return self._get(session, industry_id)
        with self.session_scope() as managed:
            return self._get(managed, industry_id)

    def update_industry_model(self, industry_id: str, session: Session | None = None, **updates: object) -> IndustryModel:
        if session is not None:
            return self._update(session, industry_id, **updates)
        with self.session_scope() as managed:
            return self._update(managed, industry_id, **updates)

    def list_industries(self, session: Session | None = None) -> list[str]:
        if session is not None:
            return self._list(session)
        with self.session_scope() as managed:
            return self._list(managed)

    def increment_pattern(self, industry_id: str, pattern_key: str, session: Session | None = None) -> IndustryModel:
        if session is not None:
            return self._increment_pattern(session, industry_id, pattern_key)
        with self.session_scope() as managed:
            return self._increment_pattern(managed, industry_id, pattern_key)

    def record_strategy_outcome(
        self,
        industry_id: str,
        strategy: str,
        success_weight: float,
        support_weight: float,
        session: Session | None = None,
    ) -> IndustryModel:
        if session is not None:
            return self._record_strategy_outcome(session, industry_id, strategy, success_weight, support_weight)
        with self.session_scope() as managed:
            return self._record_strategy_outcome(managed, industry_id, strategy, success_weight, support_weight)

    def _register(self, session: Session, industry_id: str, industry_name: str | None = None) -> IndustryModel:
        key = _normalize_industry(industry_id)
        row = session.get(IndustryIntelligenceModel, key)
        if row is None:
            row = IndustryIntelligenceModel(
                industry_id=key,
                industry_name=industry_name or key,
                pattern_distribution={},
                strategy_success_rates={},
                avg_rank_delta=0.0,
                avg_traffic_delta=0.0,
                confidence_score=0.0,
                sample_size=0,
                support_state={},
                last_updated=datetime.now(UTC),
            )
            session.add(row)
            session.flush()
        return _row_to_model(row)

    def _get(self, session: Session, industry_id: str) -> IndustryModel | None:
        row = session.get(IndustryIntelligenceModel, _normalize_industry(industry_id))
        return _row_to_model(row) if row is not None else None

    def _update(self, session: Session, industry_id: str, **updates: object) -> IndustryModel:
        key = _normalize_industry(industry_id)
        row = session.get(IndustryIntelligenceModel, key)
        if row is None:
            self._register(session, key, None)
            row = session.get(IndustryIntelligenceModel, key)
        assert row is not None
        for field_name, value in updates.items():
            if hasattr(row, field_name):
                setattr(row, field_name, value)
        row.last_updated = datetime.now(UTC)
        session.flush()
        return _row_to_model(row)

    def _list(self, session: Session) -> list[str]:
        rows = session.query(IndustryIntelligenceModel.industry_id).order_by(IndustryIntelligenceModel.industry_id.asc()).all()
        return [str(row.industry_id) for row in rows]

    def _increment_pattern(self, session: Session, industry_id: str, pattern_key: str) -> IndustryModel:
        key = _normalize_industry(industry_id)
        row = session.get(IndustryIntelligenceModel, key)
        if row is None:
            self._register(session, key, None)
            row = session.get(IndustryIntelligenceModel, key)
        assert row is not None

        support_state = dict(row.support_state or {})
        pattern_counts = dict(support_state.get('pattern_counts') or {})
        normalized_pattern = str(pattern_key).strip().lower()
        pattern_counts[normalized_pattern] = int(pattern_counts.get(normalized_pattern, 0)) + 1
        total = sum(int(value) for value in pattern_counts.values())
        row.pattern_distribution = {
            name: round(int(count) / max(total, 1), 6)
            for name, count in sorted(pattern_counts.items())
        }
        support_state['pattern_counts'] = pattern_counts
        row.support_state = support_state
        row.last_updated = datetime.now(UTC)
        session.flush()
        return _row_to_model(row)

    def _record_strategy_outcome(
        self,
        session: Session,
        industry_id: str,
        strategy: str,
        success_weight: float,
        support_weight: float,
    ) -> IndustryModel:
        key = _normalize_industry(industry_id)
        row = session.get(IndustryIntelligenceModel, key)
        if row is None:
            self._register(session, key, None)
            row = session.get(IndustryIntelligenceModel, key)
        assert row is not None

        support_state = dict(row.support_state or {})
        strategy_successes = dict(support_state.get('strategy_successes') or {})
        strategy_support = dict(support_state.get('strategy_support') or {})
        strategy_key = str(strategy).strip().lower()

        strategy_successes[strategy_key] = float(strategy_successes.get(strategy_key, 0.0)) + float(success_weight)
        strategy_support[strategy_key] = float(strategy_support.get(strategy_key, 0.0)) + float(support_weight)

        row.strategy_success_rates = {
            name: round(float(strategy_successes.get(name, 0.0)) / max(float(strategy_support.get(name, 0.0)), 1.0), 6)
            for name in sorted(strategy_support.keys())
        }
        support_state['strategy_successes'] = strategy_successes
        support_state['strategy_support'] = strategy_support
        row.support_state = support_state
        row.last_updated = datetime.now(UTC)
        session.flush()
        return _row_to_model(row)


_REGISTRY = PersistentIndustryModelRegistry()


def register_industry_model(industry_id: str, industry_name: str | None = None) -> IndustryModel:
    return _REGISTRY.register_industry_model(industry_id, industry_name)


def get_industry_model(industry_id: str) -> IndustryModel | None:
    return _REGISTRY.get_industry_model(industry_id)


def update_industry_model(industry_id: str, **updates: object) -> IndustryModel:
    return _REGISTRY.update_industry_model(industry_id, **updates)


def list_industries() -> list[str]:
    return _REGISTRY.list_industries()


def get_registry() -> Any:
    return _REGISTRY


def _normalize_industry(industry_id: str) -> str:
    normalized = str(industry_id or '').strip().lower().replace(' ', '_')
    return normalized or 'unknown'


def _row_to_model(row: IndustryIntelligenceModel) -> IndustryModel:
    return IndustryModel(
        industry_id=row.industry_id,
        industry_name=row.industry_name,
        pattern_distribution=dict(row.pattern_distribution or {}),
        strategy_success_rates=dict(row.strategy_success_rates or {}),
        avg_rank_delta=float(row.avg_rank_delta or 0.0),
        avg_traffic_delta=float(row.avg_traffic_delta or 0.0),
        confidence_score=float(row.confidence_score or 0.0),
        sample_size=int(row.sample_size or 0),
        last_updated=row.last_updated.astimezone(UTC).isoformat(),
    )
