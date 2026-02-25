from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScenarioDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    version_id: str
    category: str
    diagnosis: str
    root_cause: str
    recommended_actions: list[str] = Field(default_factory=list)
    expected_outcome: str
    authoritative_sources: list[str] = Field(default_factory=list)
    confidence_weight: float = Field(ge=0, le=1)
    impact_weight: float = Field(ge=0, le=1)
    impact_level: str
    deprecated: bool = False


SCENARIOS: list[ScenarioDefinition] = [
    ScenarioDefinition(
        scenario_id="high_visibility_low_ctr",
        version_id="v1.0.0",
        category="organic",
        diagnosis="High SERP visibility with underperforming click-through rate.",
        root_cause="Snippet and intent alignment are weaker than ranking position suggests.",
        recommended_actions=[
            "Rewrite title and meta description for intent clarity.",
            "Align snippet language with high-converting query modifiers.",
        ],
        expected_outcome="Improved CTR at existing ranking positions.",
        authoritative_sources=["https://developers.google.com/search/docs/appearance/title-link"],
        confidence_weight=0.8,
        impact_weight=0.8,
        impact_level="high",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="competitive_snippet_disadvantage",
        version_id="v1.0.0",
        category="organic",
        diagnosis="Competitor snippets outperform campaign CTR at comparable visibility.",
        root_cause="Competitive snippet structure is stronger for target queries.",
        recommended_actions=[
            "Benchmark top competitor snippets and adjust copy structure.",
            "Introduce stronger value proposition language in metadata.",
        ],
        expected_outcome="Reduced CTR gap versus competitors.",
        authoritative_sources=["https://developers.google.com/search/docs/appearance/title-link"],
        confidence_weight=0.7,
        impact_weight=0.7,
        impact_level="medium",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="core_web_vitals_failure",
        version_id="v1.0.0",
        category="technical",
        diagnosis="Core Web Vitals exceed acceptable thresholds.",
        root_cause="Page performance bottlenecks are degrading UX metrics.",
        recommended_actions=[
            "Reduce render-blocking resources.",
            "Optimize server response and critical rendering path.",
        ],
        expected_outcome="CWV compliance and improved technical quality.",
        authoritative_sources=["https://web.dev/articles/vitals"],
        confidence_weight=0.8,
        impact_weight=0.8,
        impact_level="high",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="ranking_decline_detected",
        version_id="v1.0.0",
        category="organic",
        diagnosis="Ranking decline detected with supporting performance loss.",
        root_cause="Visibility erosion is impacting organic traffic trends.",
        recommended_actions=[
            "Audit recently declining pages and query clusters.",
            "Prioritize on-page refresh for affected assets.",
        ],
        expected_outcome="Stabilized or recovered rankings and traffic.",
        authoritative_sources=["https://developers.google.com/search/docs/appearance/title-link"],
        confidence_weight=0.75,
        impact_weight=0.75,
        impact_level="high",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="gbp_low_review_velocity",
        version_id="v1.0.0",
        category="gbp",
        diagnosis="Google Business Profile review acquisition velocity is low.",
        root_cause="Insufficient review request cadence and follow-up.",
        recommended_actions=[
            "Implement post-service review request workflow.",
            "Increase review request coverage across touchpoints.",
        ],
        expected_outcome="Improved review growth velocity.",
        authoritative_sources=["https://support.google.com/business/answer/3474122"],
        confidence_weight=0.7,
        impact_weight=0.7,
        impact_level="medium",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="gbp_low_review_response_rate",
        version_id="v1.0.0",
        category="gbp",
        diagnosis="Review response rate is below target.",
        root_cause="Reputation operations are not consistently responding to reviews.",
        recommended_actions=[
            "Create review-response SLA and ownership.",
            "Use weekly response backlog reviews.",
        ],
        expected_outcome="Higher response coverage and trust signals.",
        authoritative_sources=["https://support.google.com/business/answer/3474122"],
        confidence_weight=0.7,
        impact_weight=0.65,
        impact_level="medium",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="low_review_velocity_vs_competitors",
        version_id="v1.0.0",
        category="gbp",
        diagnosis="Review footprint lags competitor baseline.",
        root_cause="Competitors are accumulating social proof faster.",
        recommended_actions=[
            "Increase review request volume for completed jobs.",
            "Prioritize reputation campaigns in high-value locations.",
        ],
        expected_outcome="Narrowed review-count and visibility disadvantage.",
        authoritative_sources=["https://support.google.com/business/answer/3474122"],
        confidence_weight=0.7,
        impact_weight=0.7,
        impact_level="medium",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="competitor_data_unavailable",
        version_id="v1.0.0",
        category="system",
        diagnosis="Competitor data is unavailable for enterprise diagnostics.",
        root_cause="Required competitor signals were not present in the analysis window.",
        recommended_actions=[
            "Verify competitor data ingestion coverage.",
            "Backfill missing competitor signal sources.",
        ],
        expected_outcome="Competitor diagnostic coverage restored.",
        authoritative_sources=["https://support.google.com/business/answer/3474122"],
        confidence_weight=0.55,
        impact_weight=0.3,
        impact_level="low",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="competitor_reputation_gap",
        version_id="v1.0.0",
        category="competitive",
        diagnosis="Competitors hold a stronger rating profile.",
        root_cause="Average rating performance trails local competitive baseline.",
        recommended_actions=[
            "Improve review quality workflows.",
            "Address recurring negative feedback themes.",
        ],
        expected_outcome="Improved rating parity versus competitors.",
        authoritative_sources=["https://support.google.com/business/answer/3474122"],
        confidence_weight=0.7,
        impact_weight=0.6,
        impact_level="medium",
        deprecated=False,
    ),
    ScenarioDefinition(
        scenario_id="competitive_position_gap",
        version_id="v1.0.0",
        category="competitive",
        diagnosis="Competitors hold a stronger average ranking position.",
        root_cause="Competitive content/authority signals are outperforming target pages.",
        recommended_actions=[
            "Prioritize pages with largest position gaps for refresh.",
            "Tighten SERP intent match and internal linking support.",
        ],
        expected_outcome="Reduced competitive ranking gap.",
        authoritative_sources=["https://developers.google.com/search/docs/appearance/title-link"],
        confidence_weight=0.7,
        impact_weight=0.7,
        impact_level="medium",
        deprecated=False,
    ),
]

SCENARIO_INDEX: dict[str, ScenarioDefinition] = {scenario.scenario_id: scenario for scenario in SCENARIOS}

