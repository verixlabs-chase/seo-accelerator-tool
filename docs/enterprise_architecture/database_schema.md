# DATABASE_SCHEMA.md

## 1) Scope

Defines the authoritative PostgreSQL 16+ schema for LSOS with multi-tenant isolation, partitioning, indexing, foreign keys, and auditability.

## 2) Global Schema Standards

- All business tables include:
  - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  - `tenant_id UUID NOT NULL`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- All tenant-scoped unique constraints include `tenant_id`.
- Time-series tables use monthly partitioning where high volume is expected.
- Soft delete pattern for business entities:
  - `deleted_at TIMESTAMPTZ NULL`
  - never hard-delete without archival workflow.

Core enums:
- `campaign_status`: `created`, `onboarding`, `active`, `paused`, `completed`, `archived`
- `priority_level`: `low`, `medium`, `high`, `critical`
- `report_status`: `queued`, `generating`, `ready`, `failed`, `delivered`

## 3) Core Identity and Access Tables

### `tenants`
- `id UUID PK`
- `name VARCHAR(255) NOT NULL`
- `slug VARCHAR(120) NOT NULL UNIQUE`
- `plan_tier VARCHAR(50) NOT NULL`
- `status VARCHAR(30) NOT NULL`
- `settings_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`

Indexes:
- `idx_tenants_status (status)`

### `users`
- `id UUID PK`
- `tenant_id UUID NOT NULL FK -> tenants(id)`
- `email CITEXT NOT NULL`
- `password_hash TEXT NOT NULL`
- `full_name VARCHAR(255) NOT NULL`
- `status VARCHAR(30) NOT NULL`
- `last_login_at TIMESTAMPTZ NULL`
- `created_at`, `updated_at`

Constraints and indexes:
- `UNIQUE (tenant_id, email)`
- `idx_users_tenant_status (tenant_id, status)`

### `roles`
- `id UUID PK`
- `tenant_id UUID NOT NULL FK -> tenants(id)`
- `name VARCHAR(80) NOT NULL`
- `permissions JSONB NOT NULL`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, name)`

### `user_roles`
- `id UUID PK`
- `tenant_id UUID NOT NULL FK -> tenants(id)`
- `user_id UUID NOT NULL FK -> users(id)`
- `role_id UUID NOT NULL FK -> roles(id)`
- `created_at`

Constraints:
- `UNIQUE (tenant_id, user_id, role_id)`

## 4) Campaign and Planning Tables

### `campaigns`
- `id UUID PK`
- `tenant_id UUID NOT NULL FK -> tenants(id)`
- `name VARCHAR(255) NOT NULL`
- `domain VARCHAR(255) NOT NULL`
- `primary_location VARCHAR(255) NOT NULL`
- `timezone VARCHAR(64) NOT NULL`
- `status campaign_status NOT NULL`
- `start_date DATE NOT NULL`
- `current_month SMALLINT NOT NULL DEFAULT 1`
- `settings_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`, `deleted_at`

Constraints and indexes:
- `UNIQUE (tenant_id, domain)`
- `idx_campaigns_tenant_status (tenant_id, status)`
- `idx_campaigns_tenant_month (tenant_id, current_month)`

### `campaign_milestones`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `month_number SMALLINT NOT NULL`
- `milestone_key VARCHAR(120) NOT NULL`
- `status VARCHAR(30) NOT NULL`
- `due_at TIMESTAMPTZ NULL`
- `completed_at TIMESTAMPTZ NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, month_number, milestone_key)`

## 5) Crawl and Technical SEO Tables

### `pages`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `url TEXT NOT NULL`
- `canonical_url TEXT NULL`
- `last_seen_at TIMESTAMPTZ NULL`
- `http_status SMALLINT NULL`
- `indexability_status VARCHAR(40) NULL`
- `title TEXT NULL`
- `meta_description TEXT NULL`
- `h1 TEXT NULL`
- `word_count INTEGER NULL`
- `created_at`, `updated_at`

Constraints and indexes:
- `UNIQUE (tenant_id, campaign_id, url)`
- `idx_pages_tenant_campaign_lastseen (tenant_id, campaign_id, last_seen_at DESC)`

### `crawl_runs`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `run_type VARCHAR(30) NOT NULL`
- `status VARCHAR(30) NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `finished_at TIMESTAMPTZ NULL`
- `stats_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_by UUID NULL FK -> users(id)`
- `created_at`, `updated_at`

Indexes:
- `idx_crawl_runs_tenant_campaign_started (tenant_id, campaign_id, started_at DESC)`

### `crawl_page_results` (partitioned by month on `snapshot_at`)
- `id UUID NOT NULL`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL`
- `crawl_run_id UUID NOT NULL FK -> crawl_runs(id)`
- `page_id UUID NOT NULL FK -> pages(id)`
- `snapshot_at TIMESTAMPTZ NOT NULL`
- `http_status SMALLINT NULL`
- `response_time_ms INTEGER NULL`
- `is_indexable BOOLEAN NULL`
- `canonical_target TEXT NULL`
- `structured_data_json JSONB NULL`
- `issues_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `(id, snapshot_at)` for partition compatibility.

Indexes (per partition):
- `(tenant_id, campaign_id, snapshot_at DESC)`
- `(tenant_id, campaign_id, page_id, snapshot_at DESC)`

### `technical_issues`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `crawl_run_id UUID NOT NULL FK -> crawl_runs(id)`
- `page_id UUID NULL FK -> pages(id)`
- `issue_code VARCHAR(120) NOT NULL`
- `severity priority_level NOT NULL`
- `status VARCHAR(30) NOT NULL DEFAULT 'open'`
- `details_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `detected_at TIMESTAMPTZ NOT NULL`
- `resolved_at TIMESTAMPTZ NULL`
- `created_at`, `updated_at`

Indexes:
- `idx_tech_issues_tenant_campaign_status (tenant_id, campaign_id, status, detected_at DESC)`

## 6) Ranking and Competitor Tables

### `keyword_clusters`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `name VARCHAR(120) NOT NULL`
- `intent VARCHAR(40) NULL`
- `priority SMALLINT NOT NULL DEFAULT 3`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, name)`

### `campaign_keywords`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `keyword_cluster_id UUID NULL FK -> keyword_clusters(id)`
- `keyword VARCHAR(255) NOT NULL`
- `locale VARCHAR(20) NOT NULL DEFAULT 'en-US'`
- `is_core BOOLEAN NOT NULL DEFAULT false`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, keyword, locale)`

### `rankings` (partitioned by month on `snapshot_date`)
- `id UUID NOT NULL`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL`
- `campaign_keyword_id UUID NOT NULL FK -> campaign_keywords(id)`
- `location_label VARCHAR(255) NOT NULL`
- `location_lat NUMERIC(9,6) NULL`
- `location_lng NUMERIC(9,6) NULL`
- `position INTEGER NULL`
- `url TEXT NULL`
- `search_engine VARCHAR(30) NOT NULL DEFAULT 'google'`
- `device_type VARCHAR(20) NOT NULL DEFAULT 'desktop'`
- `snapshot_date DATE NOT NULL`
- `captured_at TIMESTAMPTZ NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `(id, snapshot_date)`

Indexes:
- `(tenant_id, campaign_id, snapshot_date DESC)`
- `(tenant_id, campaign_id, campaign_keyword_id, snapshot_date DESC)`

### `competitors`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `domain VARCHAR(255) NOT NULL`
- `display_name VARCHAR(255) NULL`
- `is_active BOOLEAN NOT NULL DEFAULT true`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, domain)`

### `competitor_rankings` (partitioned by month on `snapshot_date`)
- `id UUID NOT NULL`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL`
- `competitor_id UUID NOT NULL FK -> competitors(id)`
- `campaign_keyword_id UUID NOT NULL FK -> campaign_keywords(id)`
- `location_label VARCHAR(255) NOT NULL`
- `position INTEGER NULL`
- `url TEXT NULL`
- `snapshot_date DATE NOT NULL`
- `captured_at TIMESTAMPTZ NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `(id, snapshot_date)`

Indexes:
- `(tenant_id, campaign_id, snapshot_date DESC)`
- `(tenant_id, campaign_id, competitor_id, snapshot_date DESC)`

## 7) Authority, Outreach, Citation Tables

### `backlinks`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `source_url TEXT NOT NULL`
- `target_url TEXT NOT NULL`
- `anchor_text TEXT NULL`
- `domain_rating NUMERIC(5,2) NULL`
- `link_type VARCHAR(30) NULL`
- `first_seen_at TIMESTAMPTZ NULL`
- `last_seen_at TIMESTAMPTZ NULL`
- `status VARCHAR(30) NOT NULL`
- `created_at`, `updated_at`

Indexes:
- `idx_backlinks_tenant_campaign_seen (tenant_id, campaign_id, last_seen_at DESC)`

### `outreach_campaigns`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `name VARCHAR(255) NOT NULL`
- `status VARCHAR(30) NOT NULL`
- `sequence_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `created_at`, `updated_at`

### `outreach_contacts`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `outreach_campaign_id UUID NULL FK -> outreach_campaigns(id)`
- `name VARCHAR(255) NULL`
- `email CITEXT NULL`
- `domain VARCHAR(255) NULL`
- `role VARCHAR(120) NULL`
- `status VARCHAR(30) NOT NULL`
- `last_contacted_at TIMESTAMPTZ NULL`
- `created_at`, `updated_at`

Indexes:
- `idx_outreach_contacts_tenant_campaign_status (tenant_id, campaign_id, status)`

### `citations`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `directory_name VARCHAR(255) NOT NULL`
- `directory_url TEXT NULL`
- `listing_url TEXT NULL`
- `status VARCHAR(30) NOT NULL`
- `submitted_at TIMESTAMPTZ NULL`
- `verified_at TIMESTAMPTZ NULL`
- `nap_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, directory_name)`

## 8) Review and Local SEO Tables

### `local_profiles`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `platform VARCHAR(50) NOT NULL DEFAULT 'google_business_profile'`
- `external_profile_id VARCHAR(255) NULL`
- `profile_name VARCHAR(255) NULL`
- `primary_category VARCHAR(255) NULL`
- `status VARCHAR(30) NOT NULL DEFAULT 'active'`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, platform, external_profile_id)`

### `local_health_snapshots`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `snapshot_date DATE NOT NULL`
- `technical_local_score NUMERIC(5,2) NOT NULL`
- `nap_consistency_score NUMERIC(5,2) NOT NULL`
- `gbp_completeness_score NUMERIC(5,2) NOT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:
- `UNIQUE (tenant_id, campaign_id, snapshot_date)`

### `reviews` (partitioned by month on `review_published_at`)
- `id UUID NOT NULL`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `external_review_id VARCHAR(255) NOT NULL`
- `platform VARCHAR(50) NOT NULL`
- `rating NUMERIC(2,1) NOT NULL`
- `review_text TEXT NULL`
- `reviewer_name VARCHAR(255) NULL`
- `sentiment_score NUMERIC(5,2) NULL`
- `review_published_at TIMESTAMPTZ NOT NULL`
- `ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Primary key:
- `(id, review_published_at)`

Constraints:
- `UNIQUE (tenant_id, campaign_id, platform, external_review_id)`

### `review_velocity_snapshots`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `snapshot_date DATE NOT NULL`
- `reviews_30d INTEGER NOT NULL`
- `avg_rating_30d NUMERIC(3,2) NOT NULL`
- `velocity_score NUMERIC(5,2) NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:
- `UNIQUE (tenant_id, campaign_id, snapshot_date)`

## 9) Content and Internal Linking Tables

### `content_assets`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `title VARCHAR(255) NOT NULL`
- `content_type VARCHAR(50) NOT NULL`
- `status VARCHAR(30) NOT NULL`
- `target_keyword VARCHAR(255) NULL`
- `target_url TEXT NULL`
- `published_at TIMESTAMPTZ NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`

### `internal_link_map`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `source_page_id UUID NOT NULL FK -> pages(id)`
- `target_page_id UUID NOT NULL FK -> pages(id)`
- `anchor_text TEXT NULL`
- `link_strength NUMERIC(5,2) NULL`
- `last_validated_at TIMESTAMPTZ NULL`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, source_page_id, target_page_id, anchor_text)`

## 10) Intelligence and Reporting Tables

### `strategy_recommendations`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `snapshot_date DATE NOT NULL`
- `category VARCHAR(80) NOT NULL`
- `priority priority_level NOT NULL`
- `title VARCHAR(255) NOT NULL`
- `description TEXT NOT NULL`
- `rationale_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `status VARCHAR(30) NOT NULL DEFAULT 'open'`
- `created_at`, `updated_at`

Indexes:
- `idx_strategy_reco_tenant_campaign_snapshot (tenant_id, campaign_id, snapshot_date DESC)`

### `monthly_reports`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `report_month DATE NOT NULL`
- `status report_status NOT NULL`
- `kpi_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `artifact_url TEXT NULL`
- `generated_at TIMESTAMPTZ NULL`
- `delivered_at TIMESTAMPTZ NULL`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, campaign_id, report_month)`

### `report_template_versions`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `template_key VARCHAR(120) NOT NULL`
- `version VARCHAR(40) NOT NULL`
- `is_active BOOLEAN NOT NULL DEFAULT true`
- `template_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at`, `updated_at`

Constraints:
- `UNIQUE (tenant_id, template_key, version)`

### `report_artifacts`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `monthly_report_id UUID NOT NULL FK -> monthly_reports(id)`
- `storage_path TEXT NOT NULL`
- `artifact_url TEXT NOT NULL`
- `artifact_sha256 VARCHAR(128) NOT NULL`
- `page_count INTEGER NULL`
- `file_size_bytes BIGINT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:
- `UNIQUE (tenant_id, monthly_report_id, artifact_sha256)`

### `report_delivery_events`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NOT NULL FK -> campaigns(id)`
- `monthly_report_id UUID NOT NULL FK -> monthly_reports(id)`
- `delivery_channel VARCHAR(40) NOT NULL DEFAULT 'email'`
- `recipient TEXT NOT NULL`
- `provider_message_id VARCHAR(255) NULL`
- `delivery_status VARCHAR(30) NOT NULL`
- `failure_reason TEXT NULL`
- `sent_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `idx_report_delivery_tenant_report (tenant_id, monthly_report_id, created_at DESC)`

## 11) Task, Operations, and Audit Tables

### `task_executions`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `campaign_id UUID NULL`
- `queue_name VARCHAR(80) NOT NULL`
- `task_name VARCHAR(120) NOT NULL`
- `correlation_id UUID NULL`
- `idempotency_key VARCHAR(255) NULL`
- `status VARCHAR(30) NOT NULL`
- `attempt SMALLINT NOT NULL DEFAULT 1`
- `started_at TIMESTAMPTZ NULL`
- `finished_at TIMESTAMPTZ NULL`
- `error_message TEXT NULL`
- `payload_json JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `idx_task_exec_tenant_queue_created (tenant_id, queue_name, created_at DESC)`
- `idx_task_exec_correlation (correlation_id)`

### `audit_logs`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `actor_user_id UUID NULL FK -> users(id)`
- `actor_service VARCHAR(120) NULL`
- `campaign_id UUID NULL FK -> campaigns(id)`
- `action VARCHAR(120) NOT NULL`
- `resource_type VARCHAR(120) NOT NULL`
- `resource_id VARCHAR(255) NULL`
- `result VARCHAR(30) NOT NULL`
- `ip_address INET NULL`
- `user_agent TEXT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `idx_audit_tenant_occurred (tenant_id, occurred_at DESC)`
- `idx_audit_action (action, occurred_at DESC)`

## 12) Required Tables Checklist from Master Spec

Included and governed in this schema:
- Campaigns
- Users
- Pages
- CrawlRuns
- Rankings
- CompetitorRankings
- Backlinks
- OutreachCampaigns
- OutreachContacts
- Citations
- Reviews
- ReviewVelocitySnapshots
- ContentAssets
- KeywordClusters
- InternalLinkMap
- StrategyRecommendations
- MonthlyReports

## 13) Partitioning Strategy

Partitioned tables:
- `crawl_page_results`: RANGE partition on month(`snapshot_at`)
- `rankings`: RANGE partition on month(`snapshot_date`)
- `competitor_rankings`: RANGE partition on month(`snapshot_date`)
- `reviews`: RANGE partition on month(`review_published_at`)

Operational policy:
- Pre-create 3 future monthly partitions.
- Retain hot data in primary partitions; archive aged partitions to cold storage.
- Reporting queries use partition-pruned predicates with tenant/campaign/time filters.

## 14) Multi-Tenant Isolation Enforcement

Application controls:
- Tenant context injected from JWT claims.
- Every query includes `tenant_id` predicate in repository layer.

Database controls:
- Optional RLS with:
  - `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;`
  - policy bound to `current_setting('app.tenant_id')::uuid`.

Integrity controls:
- All FK paths for campaign-scoped tables validate campaign ownership via joins in service layer.

## 15) Text ER Diagram

```text
tenants 1---* users
tenants 1---* roles
users   1---* user_roles
roles   1---* user_roles

tenants 1---* campaigns
campaigns 1---* pages
campaigns 1---* crawl_runs
crawl_runs 1---* crawl_page_results
pages 1---* crawl_page_results
crawl_runs 1---* technical_issues
pages 1---* technical_issues

campaigns 1---* keyword_clusters
campaigns 1---* campaign_keywords
keyword_clusters 1---* campaign_keywords
campaign_keywords 1---* rankings
campaign_keywords 1---* competitor_rankings
campaigns 1---* competitors
competitors 1---* competitor_rankings

campaigns 1---* backlinks
campaigns 1---* outreach_campaigns
outreach_campaigns 1---* outreach_contacts
campaigns 1---* citations

campaigns 1---* reviews
campaigns 1---* review_velocity_snapshots
campaigns 1---* local_profiles
campaigns 1---* local_health_snapshots

campaigns 1---* content_assets
campaigns 1---* internal_link_map
pages 1---* internal_link_map (source_page_id)
pages 1---* internal_link_map (target_page_id)

campaigns 1---* strategy_recommendations
campaigns 1---* monthly_reports
monthly_reports 1---* report_artifacts
monthly_reports 1---* report_delivery_events

tenants 1---* task_executions
tenants 1---* audit_logs
campaigns 1---* audit_logs
```

## 16) Planned Extension: Sprint 10 Reference Library Foundation

Documentation-only schema targets for the next phase (not yet implemented as migrations):

### `reference_library_versions`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `version VARCHAR(40) NOT NULL`
- `status VARCHAR(30) NOT NULL` (`draft|validated|active|archived`)
- `created_by UUID NULL FK -> users(id)`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:
- `UNIQUE (tenant_id, version)`

### `reference_library_artifacts`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `reference_library_version_id UUID NOT NULL FK -> reference_library_versions(id)`
- `artifact_type VARCHAR(40) NOT NULL` (`metrics|recommendations|diagnostics|validation_rules`)
- `artifact_uri TEXT NOT NULL`
- `artifact_sha256 VARCHAR(128) NOT NULL`
- `schema_version VARCHAR(20) NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:
- `UNIQUE (tenant_id, reference_library_version_id, artifact_type)`

### `reference_library_validation_runs`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `reference_library_version_id UUID NOT NULL FK -> reference_library_versions(id)`
- `status VARCHAR(30) NOT NULL` (`passed|failed`)
- `errors_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb`
- `executed_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `idx_ref_lib_validation_tenant_executed (tenant_id, executed_at DESC)`

### `reference_library_activations`
- `id UUID PK`
- `tenant_id UUID NOT NULL`
- `reference_library_version_id UUID NOT NULL FK -> reference_library_versions(id)`
- `activated_by UUID NULL FK -> users(id)`
- `rollback_from_version VARCHAR(40) NULL`
- `activation_status VARCHAR(30) NOT NULL` (`queued|active|rolled_back|failed`)
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Indexes:
- `idx_ref_lib_activation_tenant_created (tenant_id, created_at DESC)`

This schema is the governing relational model for LSOS.
