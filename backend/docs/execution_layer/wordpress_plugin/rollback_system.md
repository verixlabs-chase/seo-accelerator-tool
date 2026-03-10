# Rollback System

Every applied mutation stores:

- `before_state`
- `after_state`
- `rollback_payload`
- audit metadata in the plugin table

Rollback endpoint: `POST /wp-json/lsos/v1/mutations/rollback`

Rollback restores post content, meta fields, or schema state, and deletes created pages for `publish_content_page`.
