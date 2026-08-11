# Google Business Profile Fleet Campaigns

## Purpose

G1.4B lets a Growth or Enterprise operator prepare one approved Google Business
Profile action for a saved group of authorized locations. The system expands
that action into a separate, reviewable payload for every profile. It never
treats a location group as one Google mutation.

This first slice implements the campaign, preflight, and approval control
plane. Provider publishing remains disabled until a supported action succeeds
against one owned production profile and the Google project quota is reviewed.

## Current safety boundary

- Supported typed contracts are `local_post` and `photo_upload`.
- The customer workspace currently creates local-post drafts. Photo metadata is
  accepted by the API only with an HTTPS source, SHA-256 checksum, supported
  image type/category, and explicit rights confirmation. A durable customer
  asset library remains a later G1.4B slice.
- A campaign references an immutable `PortfolioTargetSnapshot` whose action key
  must match `gbp_local_post` or `gbp_photo_upload`.
- Only confirmed placeholders may be used: location name, city, region, phone,
  and website. A missing value blocks that location; the system never invents
  the value.
- Preflight requires an active location and workspace, an owned profile
  mapping, a verified profile, verified management permission, and a
  connection-level record that the single-profile action was validated.
- Approval stores an immutable hash over the content, target snapshot, rendered
  variants, profile mappings, and readiness state.
- Approval ends in `approved_hold`. It does not create a Fleet job, reserve
  provider cost, or call Google.

## State flow

```text
draft
  -> preflight
       -> blocked
       -> awaiting_approval
            -> approved_hold
```

An approved campaign cannot be edited or re-preflighted. Changed content,
schedule, targets, or assets must be represented by a new request key and a new
campaign. This keeps the approved payload reproducible.

## Stored records

`google_business_profile_campaigns` stores:

- organization and immutable target snapshot
- typed payload template and planned time
- target, content, and approval hashes
- ready/blocked counts and customer-safe preflight summary
- creator, approver, timestamps, and optimistic version

`google_business_profile_campaign_variants` stores:

- one organization/location/profile mapping
- the exact rendered payload and its checksum
- each plain-language preflight check
- ready or blocked status and the first corrective action

Both tables are tenant-scoped, organization-scoped, protected by PostgreSQL
RLS for the application role, and covered by the same delegated location-group
access checks as ML1.

## API surface

- `GET /organizations/{organization_id}/profile-campaigns`
- `POST /organizations/{organization_id}/profile-campaigns`
- `GET /organizations/{organization_id}/profile-campaigns/{campaign_id}`
- `POST /organizations/{organization_id}/profile-campaigns/{campaign_id}/preflight`
- `POST /organizations/{organization_id}/profile-campaigns/{campaign_id}/approve`

Operators can create and preflight work inside an assigned group. Approvers can
approve the frozen previews. Owners and administrators retain organization-wide
authority.

## Required next slices before live release

1. Validate the official local-post contract on one owned profile and set
   `mutation_enabled` only from that governed verification path.
2. Add Google quota discovery, per-operation cost/credit estimation, and a
   production kill switch.
3. Convert an approved campaign into one durable, idempotent Fleet item per
   profile with pacing and retry classification.
4. Store provider receipts, duplicate-prevention identifiers, partial-failure
   states, cancellation, and safe retry.
5. Add the durable media asset library before photo uploads can dispatch.
6. Add T29 location-level baselines and later measurements without presenting
   publication itself as an SEO result.

## Release proof

The release gate is a dry run followed by a bounded live campaign across a
reviewed location group. Evidence must show tenant isolation, exact approved
payloads, quota-aware pacing, duplicate-safe replay, per-location receipts,
partial failure, pause/resume, and no dispatch from Solo accounts.
