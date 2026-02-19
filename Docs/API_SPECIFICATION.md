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

## 15) Google OAuth Infrastructure Contract

Scope:
- Infrastructure-only OAuth wiring for organization-scoped Google credentials.
- No reporting, SEO execution, Search Console, GA, or provider task execution is triggered by these routes.

### 15.1 `POST /api/v1/organizations/{organization_id}/providers/google/oauth/start`

Purpose:
- Create a Google OAuth authorization URL and a signed `state` bound to the authenticated user and `organization_id`.

Required role(s):
- `org_owner` or `org_admin` in active membership for the same `organization_id`.

Org scoping behavior:
- Path `organization_id` must match authenticated user organization context.
- Mismatch returns `403` with reason code `organization_scope_mismatch`.

Request schema:
- Body: none

Query parameters:
- none

Success response envelope (`200`):
```json
{
  "data": {
    "organization_id": "uuid",
    "provider_name": "google",
    "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "state": "signed-jwt-state"
  },
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid"
  },
  "error": null
}
```

Full error response examples:

`403 organization_scope_mismatch`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_403",
      "message": "Organization context does not match request scope.",
      "details": {
        "message": "Organization context does not match request scope.",
        "reason_code": "organization_scope_mismatch"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 403
  }
}
```

`409 oauth_provider_not_configured`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_409",
      "message": "Google OAuth is not configured: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI",
      "details": {
        "message": "Google OAuth is not configured: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI",
        "reason_code": "oauth_provider_not_configured"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 409
  }
}
```

Stable reason_code list (explicit, exhaustive for this endpoint):
- `organization_scope_mismatch`
- `oauth_provider_not_configured`

### 15.2 `GET /api/v1/organizations/{organization_id}/providers/google/oauth/callback`

Purpose:
- Validate signed `state`, exchange Google authorization `code` for access/refresh tokens, and persist org-scoped encrypted OAuth credentials (`auth_mode="oauth2"`).

Required role(s):
- `org_owner` or `org_admin` in active membership for the same `organization_id`.

Org scoping behavior:
- Path `organization_id` must match authenticated user organization context.
- Signed `state.organization_id` and `state.user_id` must match path/user context.
- Cross-org or cross-user callback attempts are rejected.

Request schema:
- Body: none

Query parameters:
- `code` (required, non-empty string)
- `state` (required, non-empty signed token)

Success response envelope (`200`):
```json
{
  "data": {
    "organization_id": "uuid",
    "provider_name": "google",
    "auth_mode": "oauth2",
    "connected": true,
    "updated_at": "2026-02-19T12:34:56.000000+00:00"
  },
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid"
  },
  "error": null
}
```

Full error response examples:

`400 oauth_state_invalid`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_400",
      "message": "Google OAuth state is invalid.",
      "details": {
        "message": "Google OAuth state is invalid.",
        "reason_code": "oauth_state_invalid"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 400
  }
}
```

`400 oauth_state_expired`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_400",
      "message": "Google OAuth state expired.",
      "details": {
        "message": "Google OAuth state expired.",
        "reason_code": "oauth_state_expired"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 400
  }
}
```

`400 oauth_state_org_mismatch`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_400",
      "message": "Google OAuth state organization mismatch.",
      "details": {
        "message": "Google OAuth state organization mismatch.",
        "reason_code": "oauth_state_org_mismatch"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 400
  }
}
```

`400 oauth_state_user_mismatch`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_400",
      "message": "Google OAuth state user mismatch.",
      "details": {
        "message": "Google OAuth state user mismatch.",
        "reason_code": "oauth_state_user_mismatch"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 400
  }
}
```

`403 organization_scope_mismatch`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_403",
      "message": "Organization context does not match request scope.",
      "details": {
        "message": "Organization context does not match request scope.",
        "reason_code": "organization_scope_mismatch"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 403
  }
}
```

`409 oauth_provider_not_configured`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_409",
      "message": "Google OAuth is not configured: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI",
      "details": {
        "message": "Google OAuth is not configured: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI",
        "reason_code": "oauth_provider_not_configured"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 409
  }
}
```

`409 oauth_refresh_token_required`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_409",
      "message": "Google OAuth refresh token required.",
      "details": {
        "message": "Google OAuth refresh token required.",
        "reason_code": "oauth_refresh_token_required"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 409
  }
}
```

`502 oauth_exchange_failed`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_502",
      "message": "Google OAuth code exchange failed.",
      "details": {
        "message": "Google OAuth code exchange failed.",
        "reason_code": "oauth_exchange_failed"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 502
  }
}
```

`502 oauth_token_response_invalid`
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_502",
      "message": "Google OAuth token response is invalid.",
      "details": {
        "message": "Google OAuth token response is invalid.",
        "reason_code": "oauth_token_response_invalid"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 502
  }
}
```

`409 master_key_missing` (encryption failure during credential persistence)
```json
{
  "success": false,
  "errors": [
    {
      "code": "http_409",
      "message": "PLATFORM_MASTER_KEY is required for credential encryption.",
      "details": {
        "message": "PLATFORM_MASTER_KEY is required for credential encryption.",
        "reason_code": "master_key_missing"
      }
    }
  ],
  "meta": {
    "request_id": "uuid",
    "tenant_id": "uuid",
    "status_code": 409
  }
}
```

Stable reason_code list (explicit, exhaustive for this endpoint):
- `organization_scope_mismatch`
- `oauth_state_invalid`
- `oauth_state_expired`
- `oauth_state_org_mismatch`
- `oauth_state_user_mismatch`
- `oauth_provider_not_configured`
- `oauth_exchange_failed`
- `oauth_token_response_invalid`
- `oauth_refresh_token_required`
- `master_key_missing`
- `master_key_invalid`

### 15.3 Security Notes

- `state` is signed using server JWT configuration and contains:
  - `type=google_oauth_state`
  - `organization_id`
  - `user_id`
  - `nonce`
  - `iat` / `exp` (TTL-bound)
- CSRF mitigation:
  - Callback requires signed state validation.
  - Callback additionally binds state to authenticated user and org context.
- Replay protection:
  - Bounded by short state TTL and org/user binding.
  - State is not persisted server-side for one-time invalidation in this phase.
- No secrets are returned in API responses.
- No plaintext token persistence is allowed.

### 15.4 Credential Storage Model

- Storage target:
  - `organization_provider_credentials` only (org-scoped).
- Provider key:
  - `provider_name="google"`.
- Auth mode:
  - `auth_mode="oauth2"`.
- Encryption:
  - Envelope encryption via AES-256-GCM payload encryption + encrypted DEK.
  - DEK is encrypted with `PLATFORM_MASTER_KEY`.
  - Persisted fields are encrypted blob + key metadata (`key_reference`, `key_version`).
- Plaintext token material is never persisted to DB rows.

### 15.5 Refresh-on-Demand Behavior

- Trigger location:
  - `app/services/provider_credentials_service.py` during `resolve_provider_credentials(...)`.
- Trigger condition:
  - Selected credential has `auth_mode="oauth2"` and provider is `google`, and access token is missing/expired (with configured skew window).
- Refresh action:
  - Use stored `refresh_token` against Google token endpoint.
  - Merge updated token payload.
  - Re-encrypt and persist updated credential blob.
- If refresh fails:
  - Resolution fails with stable OAuth reason code (`oauth_refresh_failed`, `oauth_token_response_invalid`, or `oauth_refresh_token_required`).

### 15.6 Failure Semantics

- OAuth start failure:
  - No credential row mutation.
- OAuth callback pre-exchange failures (scope/state validation):
  - No credential row mutation.
- OAuth callback exchange failures:
  - No credential row mutation.
- OAuth callback storage/encryption failures:
  - No plaintext persistence; encrypted row update is not successfully committed.
- Refresh-on-demand failures:
  - Existing stored credentials remain as last committed encrypted version.

### 15.7 OAuth Invariants

- No provider execution logic is triggered during OAuth start.
- Tokens are stored organization-scoped only.
- No cross-organization token reuse is allowed.
- Refresh token is never returned in API responses.
- Expired access token auto-refresh occurs only in the credential resolution path.
- Missing refresh token yields `oauth_refresh_token_required`.

## 16) Versioning and Compatibility

- Version prefix required: `/api/v1`.
- Additive changes allowed in `v1`.
- Breaking changes require `/api/v2`.
- Deprecation policy:
  - announce for at least 2 release cycles before removal.

This document is the governing API contract for LSOS.

## 17) Planned Future Enhancement Routes (Docs `01`-`10`)

Policy:
- Routes below are planned contracts only.
- No active implementation is implied by this section.
- Existing `/api/v1` routes remain unchanged.
- Activation requires feature flags, dependency checks, and rollout approvals.

Planned endpoints:
- `GET /api/v1/roi/summary?campaign_id=...` (ROI Attribution Engine)
- `GET /api/v1/dashboard/command-center?campaign_id=...` (SEO Command Center)
- `POST /api/v1/orgs` (Organization and Subaccount Model)
- `POST /api/v1/orgs/{id}/subaccounts` (Organization and Subaccount Model)
- `GET /api/v1/orgs/{id}/usage` (Organization and Subaccount Model)
- `POST /api/v1/content/publish` (Native CMS Publishing)
- `GET /api/v1/content/status` (Native CMS Publishing)
- `GET /api/v1/margin/summary` (Margin Dashboard)
- `POST /api/v1/playbooks/apply` (SEO Playbook Engine)
- `GET /api/v1/playbooks/status` (SEO Playbook Engine)
- `GET /api/v1/locations/summary` (Multi-Location Intelligence)
- `POST /api/v1/reports/executive` (Executive Auto Reports)
- `GET /api/v1/provider-health/summary` (Provider Health Dashboard)

Planned non-HTTP outputs:
- Link Risk Scoring Engine (`05_Link_Risk_Scoring.md`) primarily produces risk artifacts:
  - toxic backlink list
  - risk index
  - disavow export file
