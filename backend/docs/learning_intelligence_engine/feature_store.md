# Feature Store Design

## Purpose
The feature store converts temporal signals into reusable, versioned features for pattern discovery and recommendation policy scoring.

## Feature categories
- snapshot features
- aggregation features
- trend features
- interaction features

## Example features
- technical_issue_density
- internal_link_ratio
- ranking_velocity_14d
- content_growth_rate_30d
- crawl_health_score
- review_velocity_slope_30d

## Feature construction examples
- technical_issue_density equals technical_issue_count divided by crawled_pages
- ranking_velocity_14d equals negative slope of avg_position over 14 days
- content_growth_rate_30d equals delta of published_assets_count over 30 days

## Proposed feature row schema

    {
      feature_id: feat_1001,
      campaign_id: cmp_001,
      feature_name: ranking_velocity_14d,
      feature_value: 0.23,
      window_start: 2026-02-20T00:00:00Z,
      window_end: 2026-03-05T00:00:00Z,
      feature_version: feature_defs_v1,
      source_signal_versions: [rank_v1, kpi_v1],
      computed_at: 2026-03-05T03:00:00Z
    }

## Computation flow
Temporal signal store
  -> window loader
  -> transform functions
  -> feature validator
  -> feature persistence

## Pseudocode

    def compute_features(campaign_id, window):
        sig = load_signals(campaign_id, window)

        out = {}
        out['technical_issue_density'] = safe_ratio(sig['technical_issue_count'], max(sig.get('crawled_pages', 1), 1))
        out['ranking_velocity_14d'] = velocity(sig.series('avg_position', 14))
        out['content_growth_rate_30d'] = growth(sig.series('published_assets_count', 30))
        out['review_velocity_slope_30d'] = slope(sig.series('reviews_last_30d', 30))

        validate_features(out)
        persist_feature_rows(campaign_id, window, out, 'feature_defs_v1')

## Point in time correctness
- read only values available at or before window_end
- store window_start and window_end with every feature row
- preserve version identifiers for replay and audit
