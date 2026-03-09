# Current Platform Signal Inventory

## Crawl and technical signals
Signals:
- technical_issue_count
- issue severity and issue_code distributions
- indexability and metadata quality derived from crawl parsing

Origins:
- app/services/crawl_service.py
- app/services/crawl_parser.py
- app/models/crawl.py

Current usage:
- intelligence score in app/services/intelligence_service.py
- reporting KPI aggregation in app/services/reporting_service.py
- daily rollups in app/services/analytics_service.py

## Ranking signals
Signals:
- current_position
- previous_position
- delta
- ranking snapshots across time

Origins:
- app/services/rank_service.py
- app/models/rank.py

Current usage:
- intelligence composite score
- campaign performance summary and trend
- report rank snapshot counts

## Content signals
Signals:
- content lifecycle state
- published content count
- quality check outcomes

Origins:
- app/services/content_service.py
- app/models/content.py

Current usage:
- intelligence score published_count contribution

## Local and review signals
Signals:
- map_pack_position
- local health_score
- reviews_last_30d
- avg_rating_last_30d

Origins:
- app/services/local_service.py
- app/models/local.py

Current usage:
- intelligence score local health component
- reporting KPI summaries

## Intelligence stack signals
Signals:
- intelligence score snapshots
- anomaly events
- recommendation lifecycle state

Origins:
- app/services/intelligence_service.py
- app/models/intelligence.py

Current usage:
- intelligence APIs
- anomaly detection and recommendation transitions

## KPI and traffic signals
Signals:
- clicks, impressions, avg_position
- sessions, conversions
- technical_issue_count, intelligence_score, reviews_last_30d

Origins:
- app/services/traffic_fact_service.py
- app/services/analytics_service.py
- app/models/campaign_daily_metric.py

Current usage:
- campaign performance APIs
- reporting pipelines

## Temporal strategy signals
Signals:
- temporal snapshots by metric
- momentum slope, acceleration, volatility
- strategy phase history

Origins:
- app/models/temporal.py
- app/services/strategy_engine/temporal_integration.py
- app/services/strategy_engine/modules/temporal_diagnostics.py

Current usage:
- strategy temporal visibility
- automation phase transitions

## Automation outcome signals
Signals:
- triggered_rules
- momentum_snapshot
- action_summary
- decision_hash
- trace_payload

Origins:
- app/services/strategy_engine/automation_engine.py
- app/models/strategy_automation_event.py

Current usage:
- automation timeline and export APIs

## Known signal gaps
- strategy endpoint currently sends empty raw_signals payload in app/api/v1/campaigns.py
- dedicated temporal ingestion writers are not yet present
- recommendation outcomes are not persisted as explicit learning labels
