# Onboarding Architecture Status

## Current Flow
Implemented onboarding remains manual and multi-step.

### Identity and Scope
- users authenticate through `backend/app/api/v1/auth.py`
- org selection is handled by `POST /api/v1/auth/select-org`
- memberships are enforced through `backend/app/services/auth_service.py`

### Organization and Tenant State
Current constraint:
- `backend/app/api/v1/tenants.py` creates a tenant record, but it does not complete a usable organization onboarding flow by itself
- no single public API creates the full usable stack of tenant + organization + user + membership

### Sub-Accounts and Hierarchy
Implemented creation paths:
- sub-account creation: `backend/app/api/v1/subaccounts.py`
- business location creation: `backend/app/api/v1/business_locations.py`
- location creation: `backend/app/api/v1/locations.py`

### Campaign Creation
Implemented path:
- `POST /api/v1/campaigns` in `backend/app/api/v1/campaigns.py`

Current behavior:
- campaign creation is manual
- setup-state transitions are manual via `PATCH /campaigns/{id}/setup-state`
- no automatic analytics bootstrap is triggered from campaign creation today

### Provider Connection
Implemented credential paths:
- organization provider credentials: `backend/app/api/v1/provider_credentials.py`
- Google OAuth client config and callback: `backend/app/api/v1/google_oauth.py`

Current behavior:
- provider connections are manual
- OAuth completion does not automatically trigger a baseline data pull

## Gaps
Structural gaps still present:
- no end-to-end onboarding wizard
- no single idempotent onboarding API
- no automatic baseline crawl, rank, or analytics seeding on campaign creation
- no automatic verification that provider credentials are ready before the user reaches reporting screens

## Required Automation
Minimum automation still needed for production-grade onboarding:
1. create organization, user, and membership in one transactionally coherent workflow
2. create or attach sub-account and campaign in the same guided flow
3. validate provider credentials before marking setup complete
4. trigger baseline collection jobs after campaign onboarding
5. trigger first analytics rollup after baseline data lands

## Required Idempotency Fixes
Current idempotent pieces:
- provider credential upserts
- OAuth credential storage behavior

Still not idempotent end-to-end:
- account bootstrap as a whole
- campaign onboarding as a whole
- repeated manual creation calls can still create duplicate entities across steps

## Future Onboarding Wizard Design
Planned target design:
```text
start onboarding
    -> create tenant/org/user/membership
    -> create sub-account / location context
    -> connect providers
    -> validate provider readiness
    -> create campaign
    -> trigger crawl/rank/local baseline
    -> run analytics.rollup_daily for the baseline date
    -> mark campaign ready
```

## Analytics Layer Interaction
With Analytics Layer v1 in place:
- onboarding should eventually seed `campaign_daily_metrics` immediately after the first successful baseline window
- until that exists, new campaigns still depend on fallback live-provider reads or sparse operational tables
