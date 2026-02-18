# API_SPECIFICATION.md

## 1) Scope

Defines LSOS HTTP API contracts for `/api/v1`. Every endpoint specifies method, path, request schema, response schema, status codes, background tasks, and auth requirements.

Base URL:
- `/api/v1`

Common headers:
- `Authorization: Bearer <access_token>`
- `X-Request-ID: <uuid>` (optional but recommended)
- `Idempotency-Key: <string>` (required for task-scheduling writes)

Common response envelope:

```json
{
  "data": {},
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid"
  },
  "error": null
}
```

Error envelope:

```json
{
  "data": null,
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid"
  },
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```

## 2) Authentication Routes

### 2.1 `POST /api/v1/auth/login`

Request schema:
```json
{
  "email": "user@tenant.com",
  "password": "string"
}
```

Response schema:
```json
{
  "access_token": "jwt",
  "refresh_token": "opaque-or-jwt",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "tenant_id": "uuid",
    "roles": ["tenant_admin"]
  }
}
```

Status codes:
- `200`, `401`, `429`

Background tasks:
- `audit.write_event`

Auth requirements:
- Public

### 2.2 `POST /api/v1/auth/refresh`

Request:
```json
{
  "refresh_token": "string"
}
```

Response:
```json
{
  "access_token": "jwt",
  "expires_in": 900
}
```

Status:
- `200`, `401`

Background tasks:
- `audit.write_event`

Auth:
- Public (refresh token required)

### 2.3 `GET /api/v1/auth/me`

Request: none

Response:
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "email": "user@tenant.com",
  "roles": ["campaign_manager"],
  "permissions": ["campaign.read", "report.generate"]
}
```

Status:
- `200`, `401`

Background tasks:
- none

Auth:
- Any authenticated user

## 3) Campaign Routes

### 3.1 `POST /api/v1/campaigns`

Request:
```json
{
  "name": "Client Campaign",
  "domain": "example.com",
  "primary_location": "Austin, TX",
  "timezone": "America/Chicago",
  "start_date": "2026-02-01"
}
```

Response:
```json
{
  "id": "uuid",
  "status": "onboarding",
  "current_month": 1
}
```

Status:
- `201`, `400`, `409`

Background tasks:
- `campaigns.bootstrap_month_plan`

Auth:
- `campaign.write`

### 3.2 `GET /api/v1/campaigns`

Request query:
- `status`, `page`, `page_size`

Response:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Client Campaign",
      "status": "active",
      "current_month": 4
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total": 100
  }
}
```

Status:
- `200`, `401`

Background:
- none

Auth:
- `campaign.read`

### 3.3 `POST /api/v1/campaigns/{campaign_id}/advance-month`

Request:
```json
{
  "override": false,
  "reason": null
}
```

Response:
```json
{
  "campaign_id": "uuid",
  "previous_month": 4,
  "current_month": 5,
  "status": "active"
}
```

Status:
- `200`, `400`, `403`, `409`

Background tasks:
- `campaigns.schedule_monthly_actions`

Auth:
- `campaign.write`

## 4) Crawl Routes

### 4.1 `POST /api/v1/crawl/schedule`

Request:
```json
{
  "campaign_id": "uuid",
  "run_type": "deep_crawl_monthly",
  "url_scope": ["https://example.com/"],
  "priority": "high"
}
```

Response:
```json
{
  "crawl_run_id": "uuid",
  "status": "queued"
}
```

Status:
- `202`, `400`, `404`

Background tasks:
- `crawl.schedule_campaign`

Auth:
- `campaign.write`

### 4.2 `GET /api/v1/crawl/runs`

Query:
- `campaign_id`, `status`, `from`, `to`, `page`, `page_size`

Response:
```json
{
  "items": [
    {
      "id": "uuid",
      "run_type": "delta_crawl_weekly",
      "status": "completed",
      "started_at": "2026-02-15T03:00:00Z",
      "finished_at": "2026-02-15T03:27:00Z"
    }
  ]
}
```

Status:
- `200`, `400`

Background:
- none

Auth:
- `campaign.read`

### 4.3 `GET /api/v1/crawl/issues`

Query:
- `campaign_id`, `severity`, `category`, `limit`

Response:
```json
{
  "items": [
    {
      "page_url": "https://example.com/service-a",
      "issue_code": "missing_h1",
      "severity": "high",
      "detected_at": "2026-02-15T03:10:00Z"
    }
  ]
}
```

Status:
- `200`, `400`

Background:
- none

Auth:
- `campaign.read`

## 5) Rank Routes

### 5.1 `POST /api/v1/rank/keywords`

Request:
```json
{
  "campaign_id": "uuid",
  "keywords": [
    {
      "keyword": "austin personal injury lawyer",
      "cluster": "money_terms",
      "is_core": true
    }
  ]
}
```

Response:
```json
{
  "accepted": 25,
  "rejected": 0
}
```

Status:
- `201`, `400`, `409`

Background tasks:
- none

Auth:
- `campaign.write`

### 5.2 `POST /api/v1/rank/schedule`

Request:
```json
{
  "campaign_id": "uuid",
  "mode": "daily_core",
  "locations": [
    {"label": "Austin Downtown", "lat": 30.2672, "lng": -97.7431}
  ]
}
```

Response:
```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

Status:
- `202`, `400`

Background tasks:
- `rank.schedule_window`

Auth:
- `campaign.write`

### 5.3 `GET /api/v1/rank/snapshots`

Query:
- `campaign_id`, `date_from`, `date_to`, `cluster`, `location`

Response:
```json
{
  "items": [
    {
      "keyword": "austin personal injury lawyer",
      "location_label": "Austin Downtown",
      "snapshot_date": "2026-02-16",
      "position": 7,
      "url": "https://example.com/personal-injury"
    }
  ]
}
```

Status:
- `200`, `400`

Background:
- none

Auth:
- `campaign.read`

### 5.4 `GET /api/v1/rank/trends`

Query:
- `campaign_id`, `window_days`

Response:
```json
{
  "visibility_score": 62.4,
  "avg_position_change": -1.8,
  "top_movers": []
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

## 6) Competitor Routes

### 6.1 `POST /api/v1/competitors`

Request:
```json
{
  "campaign_id": "uuid",
  "domain": "competitor.com",
  "display_name": "Competitor Inc"
}
```

Response:
```json
{
  "id": "uuid",
  "domain": "competitor.com",
  "is_active": true
}
```

Status:
- `201`, `400`, `409`

Background tasks:
- `competitor.refresh_baseline`

Auth:
- `campaign.write`

### 6.2 `GET /api/v1/competitors`

Query:
- `campaign_id`

Response:
```json
{
  "items": [
    {"id": "uuid", "domain": "competitor.com", "is_active": true}
  ]
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

### 6.3 `GET /api/v1/competitors/snapshots`

Query:
- `campaign_id`, `date_from`, `date_to`

Response:
```json
{
  "items": [
    {
      "competitor_domain": "competitor.com",
      "keyword": "austin personal injury lawyer",
      "snapshot_date": "2026-02-16",
      "position": 3
    }
  ]
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

### 6.4 `GET /api/v1/competitors/gaps`

Query:
- `campaign_id`, `window_days`

Response:
```json
{
  "items": [
    {
      "gap_type": "content_gap",
      "topic": "car accident claims",
      "confidence": 0.88
    }
  ]
}
```

Status:
- `200`

Background tasks:
- `competitor.compute_gap_scores` (if cache stale)

Auth:
- `campaign.read`

## 7) Content Routes

### 7.1 `POST /api/v1/content/assets`

Request:
```json
{
  "campaign_id": "uuid",
  "title": "Austin Bicycle Accident Lawyer",
  "content_type": "location_page",
  "target_keyword": "austin bicycle accident lawyer"
}
```

Response:
```json
{
  "id": "uuid",
  "status": "planned"
}
```

Status:
- `201`, `400`

Background:
- none

Auth:
- `campaign.write`

### 7.2 `PATCH /api/v1/content/assets/{asset_id}`

Request:
```json
{
  "status": "approved",
  "target_url": "https://example.com/austin-bicycle-accident-lawyer"
}
```

Response:
```json
{
  "id": "uuid",
  "status": "approved",
  "updated_at": "2026-02-16T15:00:00Z"
}
```

Status:
- `200`, `400`, `404`, `409`

Background tasks:
- `content.run_qc_checks`
- `links.refresh_graph` (on published state)

Auth:
- `campaign.write`

### 7.3 `GET /api/v1/content/plan`

Query:
- `campaign_id`, `month_number`

Response:
```json
{
  "month_number": 6,
  "required_location_pages": 3,
  "required_authority_articles": 2,
  "assets": []
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

## 8) Local SEO Routes

### 8.1 `GET /api/v1/local/health`

Query:
- `campaign_id`, `snapshot_date`

Response:
```json
{
  "technical_local_score": 78.2,
  "nap_consistency_score": 92.0,
  "gbp_completeness_score": 81.5
}
```

Status:
- `200`

Background tasks:
- `local.compute_health_score` (if stale)

Auth:
- `campaign.read`

### 8.2 `GET /api/v1/local/map-pack`

Query:
- `campaign_id`, `keyword`, `location`

Response:
```json
{
  "snapshot_date": "2026-02-16",
  "position": 4,
  "competitors": []
}
```

Status:
- `200`, `400`

Background:
- none

Auth:
- `campaign.read`

### 8.3 `GET /api/v1/reviews`

Query:
- `campaign_id`, `platform`, `date_from`, `date_to`

Response:
```json
{
  "items": [
    {
      "platform": "google",
      "rating": 5.0,
      "review_text": "Great service",
      "review_published_at": "2026-02-10T15:00:00Z"
    }
  ]
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

### 8.4 `GET /api/v1/reviews/velocity`

Query:
- `campaign_id`, `window_days`

Response:
```json
{
  "reviews_30d": 22,
  "avg_rating_30d": 4.7,
  "velocity_score": 74.5
}
```

Status:
- `200`

Background tasks:
- `reviews.compute_velocity` (if stale)

Auth:
- `campaign.read`

## 9) Authority Routes

### 9.1 `POST /api/v1/authority/outreach-campaigns`

Request:
```json
{
  "campaign_id": "uuid",
  "name": "Month 2 Authority Placements",
  "sequence_template_id": "uuid"
}
```

Response:
```json
{
  "id": "uuid",
  "status": "active"
}
```

Status:
- `201`, `400`

Background:
- none

Auth:
- `outreach.execute`

### 9.2 `POST /api/v1/authority/contacts`

Request:
```json
{
  "campaign_id": "uuid",
  "outreach_campaign_id": "uuid",
  "contacts": [
    {"name": "Editor", "email": "editor@site.com", "domain": "site.com"}
  ]
}
```

Response:
```json
{
  "accepted": 20,
  "duplicates": 2
}
```

Status:
- `201`, `400`

Background tasks:
- `outreach.enrich_contacts`

Auth:
- `outreach.execute`

### 9.3 `GET /api/v1/authority/backlinks`

Query:
- `campaign_id`, `status`, `date_from`, `date_to`

Response:
```json
{
  "items": [
    {
      "source_url": "https://authoritysite.com/post",
      "target_url": "https://example.com/service",
      "domain_rating": 67.0,
      "status": "live"
    }
  ]
}
```

Status:
- `200`

Background tasks:
- `authority.sync_backlinks` (if stale)

Auth:
- `campaign.read`

## 10) Citation Routes

### 10.1 `POST /api/v1/citations/submissions`

Request:
```json
{
  "campaign_id": "uuid",
  "directories": ["Yelp", "Bing Places", "Apple Maps"],
  "nap": {
    "name": "Business Name",
    "address": "123 Main St, Austin, TX",
    "phone": "+1-512-555-0100"
  }
}
```

Response:
```json
{
  "job_id": "uuid",
  "queued_count": 3
}
```

Status:
- `202`, `400`

Background tasks:
- `citation.submit_batch`

Auth:
- `campaign.write`

### 10.2 `GET /api/v1/citations/status`

Query:
- `campaign_id`, `status`

Response:
```json
{
  "items": [
    {
      "directory_name": "Yelp",
      "status": "verified",
      "listing_url": "https://yelp.com/biz/..."
    }
  ]
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

## 11) Reporting Routes

### 11.1 `POST /api/v1/reports/generate`

Request:
```json
{
  "campaign_id": "uuid",
  "report_month": "2026-02-01",
  "template_version": "v1"
}
```

Response:
```json
{
  "report_id": "uuid",
  "status": "queued"
}
```

Status:
- `202`, `400`, `409`

Background tasks:
- `reporting.freeze_window`
- `reporting.aggregate_kpis`
- `reporting.render_pdf`

Auth:
- `report.generate`

### 11.2 `GET /api/v1/reports`

Query:
- `campaign_id`, `status`, `page`, `page_size`

Response:
```json
{
  "items": [
    {
      "id": "uuid",
      "report_month": "2026-02-01",
      "status": "ready",
      "generated_at": "2026-02-02T04:00:00Z"
    }
  ]
}
```

Status:
- `200`

Background:
- none

Auth:
- `campaign.read`

### 11.3 `GET /api/v1/reports/{report_id}`

Request: none

Response:
```json
{
  "id": "uuid",
  "report_month": "2026-02-01",
  "status": "ready",
  "kpi_summary": {},
  "artifact_url": "https://signed-url"
}
```

Status:
- `200`, `404`

Background:
- none

Auth:
- `campaign.read`

### 11.4 `POST /api/v1/reports/{report_id}/deliver`

Request:
```json
{
  "recipients": ["owner@client.com"],
  "subject_override": null
}
```

Response:
```json
{
  "delivery_job_id": "uuid",
  "status": "queued"
}
```

Status:
- `202`, `400`, `404`

Background tasks:
- `reporting.send_email`

Auth:
- `report.generate`

## 12) Async Task Status Routes

### 12.1 `GET /api/v1/tasks/{task_id}`

Response:
```json
{
  "task_id": "uuid",
  "status": "running",
  "queue": "queue.serp",
  "attempt": 1,
  "started_at": "2026-02-16T10:00:00Z"
}
```

Status:
- `200`, `404`

Background:
- none

Auth:
- `campaign.read` for campaign-bound tasks, admin for global tasks

## 13) Auth and Permission Matrix

- Public:
  - `POST /auth/login`
  - `POST /auth/refresh`
- `campaign.read`:
  - all read campaign module endpoints
- `campaign.write`:
  - crawl/rank/content/citation schedule and campaign mutation endpoints
- `outreach.execute`:
  - outreach campaign/contact creation endpoints
- `report.generate`:
  - report generation and delivery endpoints
- `platform.admin`:
  - reference library validation, activation, and version management endpoints

## 14) Reference Library Routes

### 14.1 `POST /api/v1/reference-library/validate`

Request:
```json
{
  "version": "1.0.0",
  "artifacts": {
    "metrics": "object-or-uri",
    "recommendations": "object-or-uri"
  },
  "strict_mode": true
}
```

Response:
```json
{
  "validation_run_id": "uuid",
  "status": "passed",
  "errors": [],
  "warnings": []
}
```

Status:
- `200`, `400`, `403`, `422`

Background tasks:
- `reference_library.validate_artifact`

Auth:
- `platform.admin`

### 14.2 `POST /api/v1/reference-library/activate`

Request:
```json
{
  "version": "1.0.0",
  "reason": "activate validated baseline"
}
```

Response:
```json
{
  "activation_id": "uuid",
  "version": "1.0.0",
  "status": "queued"
}
```

Status:
- `202`, `400`, `403`, `409`

Background tasks:
- `reference_library.activate_version`
- `reference_library.reload_cache`

Auth:
- `platform.admin`

### 14.3 `GET /api/v1/reference-library/versions`

Query:
- `status`, `page`, `page_size`

Response:
```json
{
  "items": [
    {
      "version": "1.0.0",
      "status": "validated",
      "created_at": "2026-02-18T18:00:00Z"
    }
  ]
}
```

Status:
- `200`, `403`

Background:
- none

Auth:
- `platform.admin`

### 14.4 `GET /api/v1/reference-library/active`

Response:
```json
{
  "version": "1.0.0",
  "activated_at": "2026-02-18T19:00:00Z",
  "activated_by": "uuid"
}
```

Status:
- `200`, `403`

Background:
- none

Auth:
- `platform.admin`

## 15) Versioning and Compatibility

- Version prefix required: `/api/v1`.
- Additive changes allowed in `v1`.
- Breaking changes require `/api/v2`.
- Deprecation policy:
  - announce for at least 2 release cycles before removal.

This document is the governing API contract for LSOS.
