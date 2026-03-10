# Security Model

## Transport Security

The backend never sends raw editor HTML or arbitrary scripts. It sends structured mutation payloads only.

Live WordPress delivery requires:

- bearer token authentication
- HMAC request signing
- organization-scoped encrypted credentials
- execution-scoped correlation through `execution_id`

## Credential Storage

WordPress plugin credentials are stored through the existing provider credential system under provider name `wordpress_plugin`.

The encrypted blob is decrypted only at execution time.

## Operational Guardrails

Execution delivery still runs behind:

- governance enablement checks
- per-type daily caps
- manual approval policies
- risk scoring
- safety breaker pause logic

The platform can refuse to deliver even valid mutation payloads when governance blocks the execution.
