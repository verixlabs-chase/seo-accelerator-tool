# WordPress Plugin Contract

## Purpose

The plugin is the site-side mutation worker for WordPress-backed campaigns. It receives structured mutation batches from the platform, applies safe DOM or metadata changes, returns before and after snapshots, and accepts rollback requests.

## Authentication Model

Expected campaign-scoped credential payload:

```json
{
  "base_url": "https://client-site.example",
  "plugin_token": "plugin bearer token",
  "shared_secret": "hmac shared secret",
  "timeout_seconds": 15
}
```

The platform sends:

- `Authorization: Bearer <plugin_token>`
- `X-LSOS-Timestamp`
- `X-LSOS-Nonce`
- `X-LSOS-Signature`

Signature input is `timestamp + "." + nonce + "." + raw_request_body` using
HMAC-SHA256 and the shared secret. The plugin persists a hash of each accepted
nonce for the signature window and rejects reuse.

## Pairing a website

1. In InsightOS, open **Next Steps**, find **Connect WordPress**, and create a
   one-time pairing code.
2. Install and activate the plugin in WordPress.
3. In WordPress, open **Settings → InsightOS**, enter the code, and choose
   **Connect website**.
4. Return to InsightOS and choose **Test connection**.

The pairing code is campaign- and hostname-scoped, expires after 10 minutes,
and is erased after one exchange. The exchange creates a random bearer token
and signing secret for only that website. WordPress administrator passwords
are never requested or stored.

Creating another pairing code leaves the active connection working until the
new code is exchanged, then rotates that site's keys. Disconnect asks the
authenticated plugin to erase its local keys before InsightOS wipes the
encrypted platform copy. A WordPress administrator can also erase the local
keys from the plugin settings page.

## Required Endpoints

- `POST /wp-json/lsos/v1/health`
- `POST /wp-json/lsos/v1/connection/disconnect`
- `POST /wp-json/lsos/v1/content/inventory`
- `POST /wp-json/lsos/v1/mutations/preview`
- `POST /wp-json/lsos/v1/mutations/apply`
- `POST /wp-json/lsos/v1/mutations/rollback`

## Apply Request

Before this request is permitted, InsightOS sends the same mutation set to the
read-only preview endpoint. The plugin returns the exact current and proposed
values, validation results, conflicts, rollback availability, and a revision
identifier plus content fingerprint for every affected page. InsightOS saves
that response as a durable preview and requires approval of its exact hash.

The approved revision and fingerprint are copied into each apply mutation as
`expected_version`. The plugin compares them to WordPress immediately before
the batch runs. If any page changed after preview, the entire request stops
with `wordpress_preview_stale`; no mutation in that batch is applied.

```json
{
  "execution_id": "...",
  "recommendation_id": "...",
  "campaign_id": "...",
  "mutations": [
    {
      "mutation_id": "...",
      "action": "update_meta_title",
      "target_url": "/roof-repair",
      "expected_version": {
        "revision_id": "revision:412",
        "content_hash": "..."
      },
      "payload": {
        "title": "Roof Repair | Atlanta"
      }
    }
  ]
}
```

## Apply Response

```json
{
  "delivery_mode": "wordpress_plugin",
  "results": [
    {
      "mutation_id": "...",
      "status": "applied",
      "mutation_type": "update_meta_title",
      "target_url": "/roof-repair",
      "before_state": {"title": "Old Title"},
      "after_state": {"title": "Roof Repair | Atlanta"},
      "rollback_payload": {"restore_snapshot": {"title": "Old Title"}}
    }
  ]
}
```

## Rollback Request

Rollback uses the stored `before_state` and `rollback_payload` returned by the apply call. The backend does not regenerate rollback instructions from scratch.

## Public-page verification

After WordPress returns an applied result, the platform fetches each affected
URL from the public website with a cache-busting verification request. It
checks the approved output for the mutation type: document title, search
description, internal link and link text, page anchor, structured-data type, or
published-page title. Verification responses store only the check result,
message, target URL, and timestamp; the platform does not store the fetched
HTML.

A draft page is explicitly recorded as not public and is considered safely
created only when WordPress returns its new post identifier. If any required
public check fails, the execution is marked as needing attention while its
applied mutation rows and rollback snapshots remain intact. The customer can
open each checked public page and use the normal rollback control. A failed
public check can never silently become a successful execution.

## Read-only content inventory

Plugin v1.4.0 introduced signed, paginated inventory and exact-change preview
endpoints. Plugin v1.5.0 adds public title and description rendering fallbacks
so post-change verification can check the live page. InsightOS reads at
most 500 public-content records in one manual sync and stores the page URL,
publication state, title, supported SEO title and description, canonical,
headings, internal links, detected schema types, word count, WordPress revision
identifier, modification time, and a SHA-256 content fingerprint.

The page body is not returned or stored by the inventory workflow. The revision
identifier and fingerprint are the conflict inputs for every preview. An
approved change stops if the live page no longer matches the reviewed snapshot.
