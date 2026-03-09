# Mutation Schema

All website mutations are structured JSON objects. Executors produce them; the WordPress plugin applies them.

## Canonical Shape

```json
{
  "mutation_id": "sha256 payload fingerprint",
  "action": "insert_internal_link",
  "target_url": "/service/roof-repair",
  "source_url": "/service/roof-repair",
  "payload": {
    "target_url": "/locations/atlanta",
    "anchor_text": "Atlanta roof repair",
    "placement": "body_first_paragraph"
  },
  "rollback_hint": {
    "strategy": "remove_inserted_link"
  }
}
```

## Supported Actions

- `update_meta_title`
- `update_meta_description`
- `insert_internal_link`
- `create_internal_anchor`
- `add_schema_markup`
- `publish_content_page`

## Safety Properties

- No raw HTML payloads are accepted from executors.
- URLs are normalized before delivery.
- Mutation IDs are deterministic payload hashes.
- Rollback depends on persisted snapshots returned by the executor transport.
