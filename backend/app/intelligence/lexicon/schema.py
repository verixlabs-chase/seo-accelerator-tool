from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


MachineId = str
MetricDirection = Literal["lower_is_better", "higher_is_better"]
MetricKind = Literal[
    "core_web_vital",
    "supporting_web_vital",
    "organic",
    "local",
    "reputation",
    "technical",
    "content",
    "competitive",
    "business",
]
DataScope = Literal["page", "origin", "location", "campaign", "organization", "portfolio"]
MissingDataBehavior = Literal["unknown", "not_applicable", "zero_is_valid", "block_decision"]
ImpactLevel = Literal["low", "medium", "high", "critical"]
EffortLevel = Literal["low", "medium", "high"]


class LexiconMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    lexicon_id: MachineId = Field(min_length=1)
    version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    status: Literal["draft", "validated", "active"]
    effective_date: date
    generated_at: datetime
    standards_reviewed_at: datetime
    scope: str = Field(min_length=1)


class EvidenceSourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: MachineId = Field(min_length=1)
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    authority: Literal["primary", "secondary", "internal"]
    last_verified_at: datetime
    review_interval_days: int = Field(ge=1, le=366)
    change_detection: Literal[
        "crux_histogram", "release_notes", "document_review", "internal_governance"
    ]
    notes: str = ""


class TermDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    term_id: MachineId = Field(min_length=1)
    category: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    plain_language: str = Field(min_length=1)
    technical_definition: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    avoid_phrases: list[str] = Field(default_factory=list)


class SignalDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    signal_id: MachineId = Field(min_length=1)
    category: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    plain_language: str = Field(min_length=1)
    data_type: Literal["number", "integer", "ratio", "boolean", "string"]
    unit: str = Field(min_length=1)
    scope: DataScope
    source_provider: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    freshness_days: int = Field(ge=0, le=366)
    missing_data_behavior: MissingDataBehavior
    aliases: list[str] = Field(default_factory=list)


class ThresholdDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: MetricDirection
    good_boundary: float
    poor_boundary: float
    percentile: int | None = Field(default=None, ge=1, le=100)
    boundary_semantics: Literal[
        "good_lte_poor_gt",
        "good_gte_poor_lt",
    ]

    @model_validator(mode="after")
    def validate_order(self) -> "ThresholdDefinition":
        if self.direction == "lower_is_better":
            if self.boundary_semantics != "good_lte_poor_gt":
                raise ValueError("lower_is_better requires good_lte_poor_gt")
            if self.good_boundary >= self.poor_boundary:
                raise ValueError("lower_is_better requires good_boundary < poor_boundary")
        else:
            if self.boundary_semantics != "good_gte_poor_lt":
                raise ValueError("higher_is_better requires good_gte_poor_lt")
            if self.good_boundary <= self.poor_boundary:
                raise ValueError("higher_is_better requires good_boundary > poor_boundary")
        return self


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    metric_id: MachineId = Field(min_length=1)
    kind: MetricKind
    display_name: str = Field(min_length=1)
    plain_language: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    aggregation: Literal["p75", "latest", "average", "sum", "count", "ratio", "slope"]
    scope: DataScope
    source_metric_keys: list[str] = Field(min_length=1)
    segment_by: list[str] = Field(default_factory=list)
    thresholds: ThresholdDefinition | None = None
    freshness_days: int = Field(ge=0, le=366)
    source_ids: list[MachineId] = Field(min_length=1)
    is_google_search_standard: bool = False
    caveat: str = ""


class ActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: MachineId = Field(min_length=1)
    category: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    risk_tier: int = Field(ge=0, le=4)
    effort: EffortLevel
    owner_role: str = Field(min_length=1)
    dependencies: list[MachineId] = Field(default_factory=list)
    success_metric_ids: list[MachineId] = Field(default_factory=list)
    observation_window_days: int = Field(ge=1, le=366)
    rollback_guidance: str = Field(min_length=1)
    source_ids: list[MachineId] = Field(default_factory=list)
    ai_allowed: bool = True


class DiagnosticDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    diagnostic_id: MachineId = Field(min_length=1)
    version: str = Field(min_length=1)
    category: str = Field(min_length=1)
    business_label: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    root_cause_hypotheses: list[str] = Field(min_length=1)
    required_signal_ids: list[MachineId] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(min_length=1)
    action_ids: list[MachineId] = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)
    source_ids: list[MachineId] = Field(default_factory=list)
    confidence_weight: float = Field(ge=0, le=1)
    impact_weight: float = Field(ge=0, le=1)
    impact_level: ImpactLevel
    deprecated: bool = False


class PolicyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    policy_id: MachineId = Field(min_length=1)
    pattern_keys: list[MachineId] = Field(min_length=1)
    action_ids: list[MachineId] = Field(min_length=1)
    priority_weight: float = Field(ge=0, le=1)
    risk_tier: int = Field(ge=0, le=4)
    rationale: str = Field(min_length=1)


class IntelligenceLexicon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: LexiconMetadata
    sources: list[EvidenceSourceDefinition] = Field(min_length=1)
    terms: list[TermDefinition] = Field(min_length=1)
    signals: list[SignalDefinition] = Field(min_length=1)
    metrics: list[MetricDefinition] = Field(min_length=1)
    actions: list[ActionDefinition] = Field(min_length=1)
    diagnostics: list[DiagnosticDefinition] = Field(min_length=1)
    policies: list[PolicyDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "IntelligenceLexicon":
        source_ids = _unique_ids("source", [item.source_id for item in self.sources])
        _unique_ids("term", [item.term_id for item in self.terms])
        signal_ids = _unique_ids("signal", [item.signal_id for item in self.signals])
        metric_ids = _unique_ids("metric", [item.metric_id for item in self.metrics])
        action_ids = _unique_ids("action", [item.action_id for item in self.actions])
        _unique_ids("diagnostic", [item.diagnostic_id for item in self.diagnostics])
        _unique_ids("policy", [item.policy_id for item in self.policies])

        for metric in self.metrics:
            _require_known(f"metric {metric.metric_id} source", metric.source_ids, source_ids)
        for action in self.actions:
            _require_known(f"action {action.action_id} source", action.source_ids, source_ids)
            _require_known(
                f"action {action.action_id} success metric",
                action.success_metric_ids,
                metric_ids,
            )
        for diagnostic in self.diagnostics:
            _require_known(
                f"diagnostic {diagnostic.diagnostic_id} signal",
                diagnostic.required_signal_ids,
                signal_ids,
            )
            _require_known(
                f"diagnostic {diagnostic.diagnostic_id} action",
                diagnostic.action_ids,
                action_ids,
            )
            _require_known(
                f"diagnostic {diagnostic.diagnostic_id} source",
                diagnostic.source_ids,
                source_ids,
            )
        for policy in self.policies:
            _require_known(f"policy {policy.policy_id} action", policy.action_ids, action_ids)

        required_cwv = {"cwv.lcp", "cwv.inp", "cwv.cls"}
        defined_cwv = {
            metric.metric_id for metric in self.metrics if metric.kind == "core_web_vital"
        }
        if defined_cwv != required_cwv:
            missing = sorted(required_cwv - defined_cwv)
            extra = sorted(defined_cwv - required_cwv)
            raise ValueError(
                f"Core Web Vitals set must be exactly {sorted(required_cwv)}; "
                f"missing={missing}, extra={extra}"
            )
        for metric in self.metrics:
            if metric.kind == "core_web_vital":
                if metric.aggregation != "p75":
                    raise ValueError(f"{metric.metric_id} must use p75 aggregation")
                if metric.thresholds is None or metric.thresholds.percentile != 75:
                    raise ValueError(f"{metric.metric_id} must define p75 thresholds")
        return self

    @property
    def source_index(self) -> dict[str, EvidenceSourceDefinition]:
        return {item.source_id: item for item in self.sources}

    @property
    def signal_index(self) -> dict[str, SignalDefinition]:
        return {item.signal_id: item for item in self.signals}

    @property
    def metric_index(self) -> dict[str, MetricDefinition]:
        return {item.metric_id: item for item in self.metrics}

    @property
    def action_index(self) -> dict[str, ActionDefinition]:
        return {item.action_id: item for item in self.actions}

    @property
    def diagnostic_index(self) -> dict[str, DiagnosticDefinition]:
        return {item.diagnostic_id: item for item in self.diagnostics}

    @property
    def policy_index(self) -> dict[str, PolicyDefinition]:
        return {item.policy_id: item for item in self.policies}


def _unique_ids(kind: str, values: list[str]) -> set[str]:
    resolved = set(values)
    if len(resolved) != len(values):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        raise ValueError(f"Duplicate {kind} ids: {duplicates}")
    return resolved


def _require_known(label: str, values: list[str], allowed: set[str]) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"Unknown {label} references: {unknown}")
