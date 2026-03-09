# WordPress Plugin Contract

## Purpose

The plugin is the site-side mutation worker for WordPress-backed campaigns. It receives structured mutation batches from the platform, applies safe DOM or metadata changes, returns before and after snapshots, and accepts rollback requests.

## Authentication Model

Expected organization credential payload under provider name `wordpress_plugin`:

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
- `X-LSOS-Signature`

Signature input is `timestamp + "." + raw_request_body` using HMAC-SHA256 and the shared secret.

## Required Endpoints

- `POST /wp-json/lsos/v1/mutations/apply`
- `POST /wp-json/lsos/v1/mutations/rollback`

## Apply Request

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
