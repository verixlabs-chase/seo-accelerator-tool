# Mutation Engine

Supported actions:

- `update_meta_title`
- `update_meta_description`
- `insert_internal_link`
- `create_internal_anchor`
- `add_schema_markup`
- `publish_content_page`

The engine resolves WordPress posts from URL paths, validates the payload, captures `before_state`, applies the mutation, stores `after_state`, and returns a rollback payload for every successful mutation.
