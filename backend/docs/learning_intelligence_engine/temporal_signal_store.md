# Temporal Signal Store

## Purpose
The temporal signal store is the historical backbone for trend detection, feature computation, pattern discovery, and replay.

## Existing model foundation
Current platform model:
- app/models/temporal.py
- class TemporalSignalSnapshot

Core fields already present:
- signal_type
- metric_name
- metric_value
- observed_at
- source
- confidence
- version_hash

## Field semantics
- signal_type: domain bucket such as rank, review, content, traffic.
- metric_name: canonical signal key.
- metric_value: numeric payload for analytics and learning.
- observed_at: business timestamp for point in time correctness.
- source: extractor identity.
- confidence: reliability estimate for metric quality.
- version_hash: lineage identifier for schema and transform version.

## Why historical persistence matters
- slope and volatility need ordered history
- outcomes need baseline and evaluation windows
- policy updates need repeatable evidence sets
- replay and governance require deterministic reconstruction

## Query patterns
- latest N values for campaign and metric
- window range query for feature generation
- cross campaign cohort query by metric_name
- lineage query by source and version_hash

## Suggested ingestion behavior
- append facts, avoid silent in place mutation
- idempotent upsert by unique tuple
- preserve all versions needed for replay

## Example rows

    {
      campaign_id: cmp_001,
      signal_type: rank,
      metric_name: avg_position,
      metric_value: 8.4,
      observed_at: 2026-03-05T00:00:00Z,
      source: signal_extractor_rank_v1,
      confidence: 0.91,
      version_hash: abcd1234
    }

    {
      campaign_id: cmp_001,
      signal_type: content,
      metric_name: published_assets_count,
      metric_value: 37,
      observed_at: 2026-03-05T00:00:00Z,
      source: signal_extractor_content_v1,
      confidence: 0.95,
      version_hash: efgh5678
    }

## Data quality controls
- reject invalid numeric values
- enforce known metric_name catalog
- emit quality warnings for expected but missing metrics
- track extraction delay and completeness
