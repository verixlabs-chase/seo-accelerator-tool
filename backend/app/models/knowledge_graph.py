from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeNode(Base):
    __tablename__ = 'knowledge_nodes'
    __table_args__ = (
        UniqueConstraint('node_type', 'node_key', name='uq_knowledge_nodes_type_key'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True)


class KnowledgeEdge(Base):
    __tablename__ = 'knowledge_edges'
    __table_args__ = (
        UniqueConstraint('source_node_id', 'target_node_id', 'edge_type', 'industry', name='uq_knowledge_edges_identity'),
        Index('ix_knowledge_edges_industry_confidence', 'industry', 'confidence'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_node_id: Mapped[str] = mapped_column(String(36), ForeignKey('knowledge_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    target_node_id: Mapped[str] = mapped_column(String(36), ForeignKey('knowledge_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    industry: Mapped[str] = mapped_column(String(120), nullable=False, default='unknown', index=True)
    effect_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), index=True)
