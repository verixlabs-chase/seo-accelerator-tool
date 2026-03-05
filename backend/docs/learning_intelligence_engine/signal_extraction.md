# Signal Extraction Architecture

## Objective
Transform source telemetry into canonical and versioned SEO signals.

## Sources
- crawl and technical issue outputs
- ranking snapshots and deltas
- content lifecycle and QC
- local profile and review velocity snapshots
- campaign daily KPI rollups
- automation result events

## Extraction pipeline
1. Source collector jobs per domain.
2. Canonical mapping to signal_type and metric_name.
3. Normalization and validation.
4. Confidence assignment and version stamping.
5. Temporal signal persistence.

## Data flow

Source services and tables
      |
      +--> crawl collector
      +--> rank collector
      +--> content collector
      +--> local collector
      +--> kpi collector
      +--> automation collector
                |
                v
         Canonical mapper
                |
                v
         Validation layer
                |
                v
        Temporal signal store

## Pseudocode

    def extract_signals(campaign_id, observed_at):
        rows = []

        issues = count_technical_issues(campaign_id)
        rows.append(make_signal('crawl', 'technical_issue_count', issues, observed_at, 0.95))

        avg_rank = compute_average_rank(campaign_id)
        rows.append(make_signal('rank', 'avg_position', avg_rank, observed_at, 0.90))

        published = count_published_content(campaign_id)
        rows.append(make_signal('content', 'published_assets_count', published, observed_at, 0.92))

        local_health = get_latest_local_health(campaign_id)
        if local_health is not None:
            rows.append(make_signal('review', 'local_health_score', local_health, observed_at, 0.85))

        kpi = get_latest_campaign_daily_metric(campaign_id)
        if kpi is not None:
            rows.append(make_signal('traffic', 'clicks', kpi.clicks or 0, observed_at, 0.97))
            rows.append(make_signal('traffic', 'impressions', kpi.impressions or 0, observed_at, 0.97))
            rows.append(make_signal('conversion', 'conversions', kpi.conversions or 0, observed_at, 0.93))

        upsert_temporal_signals(campaign_id, rows)

## Normalization rules
- ratios stored as decimal fractions
- unknown metric names rejected in strict mode
- confidence clamped to range 0 through 1
- null preserved for unavailable metrics

## Idempotency
Recommended uniqueness tuple:
- campaign_id
- signal_type
- metric_name
- observed_at
- version_hash

Same inputs and extractor version must produce identical outputs.
