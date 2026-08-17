from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AISearchEngineRegistry(Base):
    """Immutable, provider-neutral description of an evidence collection surface."""

    __tablename__ = "ai_search_engine_registry"
    __table_args__ = (
        CheckConstraint(
            "status in ('candidate','active','paused','retired')",
            name="ck_ai_search_engine_registry_status",
        ),
        CheckConstraint(
            "customer_visible = false",
            name="ck_ai_search_engine_registry_customer_visibility_disabled",
        ),
        CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_ai_search_engine_registry_automatic_activation_disabled",
        ),
        UniqueConstraint(
            "engine_code",
            "registry_version",
            name="uq_ai_search_engine_registry_code_version",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    engine_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    public_name: Mapped[str] = mapped_column(String(120), nullable=False)
    registry_version: Mapped[str] = mapped_column(String(40), nullable=False)
    collection_method: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate", index=True
    )
    customer_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    evidence_qa_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cost_qa_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    comparison_qa_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    supported_geographies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    supported_languages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    supported_devices: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    supported_personalization_policies: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    supported_evidence_facts: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    limitations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    qa_approval_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    production_proof_reference: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    supersedes_engine_registry_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_search_engine_registry.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AISearchProviderContractRegistry(Base):
    """Immutable internal contract for a future evidence supplier adapter."""

    __tablename__ = "ai_search_provider_contract_registry"
    __table_args__ = (
        CheckConstraint(
            "status = 'candidate'",
            name="ck_ai_search_provider_contract_candidate_only",
        ),
        CheckConstraint(
            "production_qa_passed = false AND pricing_qa_passed = false",
            name="ck_ai_search_provider_contract_qa_disabled",
        ),
        CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_ai_search_provider_contract_automatic_activation_disabled",
        ),
        UniqueConstraint(
            "provider_key",
            "contract_code",
            "contract_version",
            name="uq_ai_search_provider_contract_identity",
        ),
        Index(
            "ix_ai_search_provider_contract_supersedes",
            "supersedes_provider_contract_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    contract_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    collection_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    request_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    response_schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_mappings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_inputs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    guaranteed_evidence_facts: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    optional_evidence_facts: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    unsupported_evidence_facts: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    raw_response_retention_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    billable_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate", index=True
    )
    production_qa_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    pricing_qa_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    qa_approval_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    production_proof_reference: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    supersedes_provider_contract_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_search_provider_contract_registry.id", ondelete="RESTRICT"),
        nullable=True,
    )
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AISearchQuestionSet(Base):
    """Frozen questions derived only from owner-confirmed business context."""

    __tablename__ = "ai_search_question_sets"
    __table_args__ = (
        CheckConstraint(
            "status = 'frozen'",
            name="ck_ai_search_question_sets_frozen",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "campaign_id",
            "version",
            name="uq_ai_search_question_sets_scope_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "campaign_id",
            "question_set_hash",
            name="uq_ai_search_question_sets_scope_hash",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            name="uq_ai_search_question_sets_scoped_identity",
        ),
        ForeignKeyConstraint(
            [
                "campaign_id",
                "tenant_id",
                "organization_id",
                "business_location_id",
            ],
            [
                "campaigns.id",
                "campaigns.tenant_id",
                "campaigns.organization_id",
                "campaigns.business_location_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_question_sets_scoped_campaign",
        ),
        ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            ondelete="RESTRICT",
            name="fk_ai_search_question_sets_scoped_location",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            ondelete="RESTRICT",
            name="fk_ai_search_question_sets_scoped_creator",
        ),
        Index(
            "ix_ai_search_question_sets_campaign_created",
            "campaign_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    context_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question_set_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="frozen", index=True
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AISearchCollectionRun(Base):
    """Provider-neutral collection lifecycle reserved for a later execution sprint."""

    __tablename__ = "ai_search_collection_runs"
    __table_args__ = (
        CheckConstraint(
            "status in "
            "('queued','submitted','collecting','complete','partial','failed',"
            "'expired','unsupported','unavailable')",
            name="ck_ai_search_collection_runs_status",
        ),
        CheckConstraint(
            "requested_observation_count >= 0 AND collected_observation_count >= 0 "
            "AND collected_observation_count <= requested_observation_count",
            name="ck_ai_search_collection_runs_observation_counts",
        ),
        CheckConstraint(
            "credential_owner IS NULL OR credential_owner in ('platform','organization')",
            name="ck_ai_search_collection_runs_credential_owner",
        ),
        CheckConstraint(
            "(price_card_id IS NULL AND cost_reservation_id IS NULL "
            "AND credential_owner IS NULL) OR "
            "(price_card_id IS NOT NULL AND cost_reservation_id IS NOT NULL "
            "AND credential_owner IS NOT NULL)",
            name="ck_ai_search_collection_runs_cost_provenance_complete",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_search_collection_runs_scope_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "question_set_id",
            "engine_registry_id",
            "provider_contract_id",
            name="uq_ai_search_collection_runs_scoped_identity",
        ),
        ForeignKeyConstraint(
            [
                "question_set_id",
                "tenant_id",
                "organization_id",
                "campaign_id",
                "business_location_id",
            ],
            [
                "ai_search_question_sets.id",
                "ai_search_question_sets.tenant_id",
                "ai_search_question_sets.organization_id",
                "ai_search_question_sets.campaign_id",
                "ai_search_question_sets.business_location_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_collection_runs_scoped_question_set",
        ),
        ForeignKeyConstraint(
            [
                "prior_comparable_run_id",
                "tenant_id",
                "organization_id",
                "campaign_id",
                "business_location_id",
                "question_set_id",
                "engine_registry_id",
                "provider_contract_id",
            ],
            [
                "ai_search_collection_runs.id",
                "ai_search_collection_runs.tenant_id",
                "ai_search_collection_runs.organization_id",
                "ai_search_collection_runs.campaign_id",
                "ai_search_collection_runs.business_location_id",
                "ai_search_collection_runs.question_set_id",
                "ai_search_collection_runs.engine_registry_id",
                "ai_search_collection_runs.provider_contract_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_collection_runs_scoped_prior_run",
        ),
        Index(
            "ix_ai_search_collection_runs_campaign_requested",
            "campaign_id",
            "requested_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    question_set_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    engine_registry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_search_engine_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_search_provider_contract_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    comparison_version: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    personalization_policy: Mapped[str] = mapped_column(String(80), nullable=False)
    comparison_scope_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    prior_comparable_run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    location_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    device: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", index=True
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_observation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    collected_observation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    coverage_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    price_card_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("provider_price_cards.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    cost_reservation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("cost_ledger_entries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    credential_owner: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AISearchObservation(Base):
    """Append-only normalized evidence from one exact question and engine version."""

    __tablename__ = "ai_search_observations"
    __table_args__ = (
        CheckConstraint(
            "mention_state in "
            "('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_mention_state",
        ),
        CheckConstraint(
            "recommendation_state in "
            "('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_recommendation_state",
        ),
        CheckConstraint(
            "citation_state in "
            "('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_citation_state",
        ),
        CheckConstraint(
            "link_state in ('observed','not_observed','not_measured','unavailable')",
            name="ck_ai_search_observations_link_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "run_id",
            "question_id",
            name="uq_ai_search_observations_run_question",
        ),
        ForeignKeyConstraint(
            [
                "run_id",
                "tenant_id",
                "organization_id",
                "campaign_id",
                "business_location_id",
                "question_set_id",
                "engine_registry_id",
                "provider_contract_id",
            ],
            [
                "ai_search_collection_runs.id",
                "ai_search_collection_runs.tenant_id",
                "ai_search_collection_runs.organization_id",
                "ai_search_collection_runs.campaign_id",
                "ai_search_collection_runs.business_location_id",
                "ai_search_collection_runs.question_set_id",
                "ai_search_collection_runs.engine_registry_id",
                "ai_search_collection_runs.provider_contract_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_search_observations_scoped_run",
        ),
        Index(
            "ix_ai_search_observations_campaign_observed",
            "campaign_id",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    question_set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_search_question_sets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    engine_registry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_search_engine_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_contract_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_search_provider_contract_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    personalization_policy: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    device: Mapped[str] = mapped_column(String(24), nullable=False)
    mention_state: Mapped[str] = mapped_column(String(24), nullable=False)
    recommendation_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_measured"
    )
    citation_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_measured"
    )
    link_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="not_measured"
    )
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    cited_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    competitor_entities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
