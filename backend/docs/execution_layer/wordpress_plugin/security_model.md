# Security Model

Authentication requires:

- `Authorization: Bearer <token>`
- `X-LSOS-Timestamp`
- `X-LSOS-Signature`

Signature format:

`HMAC_SHA256(timestamp + '.' + raw_body, shared_secret)`

The timestamp replay window is five minutes. Requests outside that window are rejected.
