from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntelligenceGraphNode(Base):
    __tablename__ = 'intelligence_graph_nodes'
    __table_args__ = (
        Index('ix_intelligence_graph_nodes_node_type', 'node_type'),
        Index('ix_intelligence_graph_nodes_updated_at', 'updated_at'),
    )

    node_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class IntelligenceGraphEdge(Base):
    __tablename__ = 'intelligence_graph_edges'
    __table_args__ = (
        Index('ix_intelligence_graph_edges_source_id', 'source_id'),
        Index('ix_intelligence_graph_edges_target_id', 'target_id'),
        Index('ix_intelligence_graph_edges_edge_type', 'edge_type'),
        Index('ix_intelligence_graph_edges_updated_at', 'updated_at'),
    )

    edge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey('intelligence_graph_nodes.node_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    target_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey('intelligence_graph_nodes.node_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
