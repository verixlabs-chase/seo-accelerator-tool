from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LaunchExperienceReview(Base):
    """Append-only route or moderated-session evidence for launch usability."""

    __tablename__ = "launch_experience_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_kind in ('route_audit','moderated_session')",
            name="ck_launch_experience_reviews_kind",
        ),
        CheckConstraint(
            "viewport in ('desktop','mobile','not_applicable')",
            name="ck_launch_experience_reviews_viewport",
        ),
        CheckConstraint(
            "result in ('passed','failed')",
            name="ck_launch_experience_reviews_result",
        ),
        CheckConstraint(
            "issue_count >= 0 and blocking_issue_count >= 0 "
            "and blocking_issue_count <= issue_count",
            name="ck_launch_experience_reviews_issue_counts",
        ),
        CheckConstraint(
            "result <> 'passed' or blocking_issue_count = 0",
            name="ck_launch_experience_reviews_passed_clear",
        ),
        CheckConstraint(
            "expires_at > observed_at",
            name="ck_launch_experience_reviews_expiry",
        ),
        UniqueConstraint("evidence_digest", name="uq_launch_experience_reviews_digest"),
        Index(
            "ix_launch_experience_subject_view_observed",
            "subject_code",
            "viewport",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ops1-experience-review-v1"
    )
    review_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    subject_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    viewport: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    session_reference: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
