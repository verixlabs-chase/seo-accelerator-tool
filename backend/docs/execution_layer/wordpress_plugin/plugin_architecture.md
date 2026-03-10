# Plugin Architecture

The LSOS WordPress Execution Plugin is the site-side execution control plane for LSOS. It accepts authenticated structured mutation batches from the backend and applies them through deterministic WordPress-safe handlers.

## Components

- bootstrap plugin file
- `LSOS_Auth`
- `LSOS_Audit_Store`
- `LSOS_DOM_Mutation_Engine`
- `LSOS_REST_Controller`

## Routes

- `POST /wp-json/lsos/v1/mutations/apply`
- `POST /wp-json/lsos/v1/mutations/rollback`
