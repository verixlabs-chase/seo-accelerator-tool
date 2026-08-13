# Security Model

Authentication requires:

- `Authorization: Bearer <token>`
- `X-LSOS-Timestamp`
- `X-LSOS-Nonce`
- `X-LSOS-Signature`

Signature format:

`HMAC_SHA256(timestamp + '.' + nonce + '.' + raw_body, shared_secret)`

The timestamp replay window is five minutes. Requests outside that window are
rejected. Each valid nonce is claimed atomically in the plugin database and a
second use is rejected, so a captured request cannot be replayed inside the
window.

Initial credentials are provisioned through a 96-bit, hostname-bound pairing
code that expires after 10 minutes and is consumed after one successful
exchange. The resulting token and signing secret are encrypted at rest in a
campaign-scoped record, so rotating or disconnecting one website does not
change another website's connection.

Content inventory is read-only, paginated, and bounded to 500 records per
manual sync. It returns structured page metadata, a revision identifier, and a
one-way fingerprint rather than raw page bodies. Every returned URL must match
the paired site hostname before it is persisted.

Every live mutation requires a durable preview record. The record includes the
canonical mutation set, exact before and proposed values, affected URLs,
validation checks, conflicts, rollback plan, and the live WordPress revision
and content fingerprint. A human approves the SHA-256 hash of that snapshot.
The apply request carries the approved version for each mutation, and the
plugin validates the whole batch before applying the first change. A changed
page, missing version, unsupported target, or preview conflict fails closed.
