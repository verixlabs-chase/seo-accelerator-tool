# Website Analytics and Inquiry Events

## Purpose

InsightOS connects search visibility to what visitors do on the matched
business website. It reports visits, engaged visits, important website actions,
entry pages, traffic sources, and verified website inquiries for one business
location at a time. It does not claim that a visit caused a sale.

## Saved facts

The read-only website activity connection saves daily totals for:

- visits;
- engaged visits;
- approved key events;
- entry pages, with query strings and fragments removed; and
- traffic source and medium.

Detail imports use bounded date ranges and save explicit zero-activity coverage
markers. Those internal markers prevent paid history requests from repeating
when a date has no activity and are never shown to customers.

## Privacy-minimized inquiry contract

An organization administrator creates or replaces a private connection key in
Settings. The raw key is returned once. Only its SHA-256 hash and creation time
are saved. Replacing the key invalidates the previous key immediately.

The public endpoint is:

`POST /api/v1/website-events/forms/{connection_id}`

It requires `Authorization: Bearer {private_key}` and this exact JSON contract:

```json
{
  "event_id": "form-20260812-000001",
  "event_name": "inquiry_confirmed",
  "page_url": "https://example.com/contact",
  "form_id": "contact-main",
  "occurred_at": "2026-08-12T18:30:00Z"
}
```

Allowed event names are `form_submitted` and `inquiry_confirmed`. Unknown JSON
fields are rejected. Page URLs must belong to the mapped campaign domain. Query
strings and fragments are discarded before storage. Events must include a time
zone and arrive within the bounded delivery window.

The contract must never include or store:

- a person's name, email address, phone number, or postal address;
- message text or other form contents;
- CRM, field-service, call-tracking, job, payment, or revenue data; or
- cookies, browser fingerprints, IP addresses, or advertising identifiers.

## Retry and tenant safety

`event_id` is unique inside the saved website connection. Replaying the same
facts returns success without creating a duplicate. Reusing that identifier for
different facts returns a conflict. The server derives tenant, organization,
location, campaign, and website scope from the saved connection; the website
cannot supply or override those identifiers.

## Customer-facing tracking health

Tracking health is deliberately conservative:

- **Setup required:** no private website-event key exists.
- **Waiting:** the key exists but no event has arrived.
- **Active:** a recent event was received.
- **Check tracking:** visits continued at meaningful volume but no event arrived
  for more than 30 days.
- **Quiet:** no recent inquiry was observed, but there is not enough evidence to
  say the form is broken.

The system never treats a quiet period alone as proof of a tracking failure.

## Installation and validation

1. Map the correct read-only website activity property to the location.
2. In Settings, create the form connection and copy the one-time key.
3. Configure the website or future WordPress connector to send one approved
   event after a genuine form success state, not on button click.
4. Submit one test inquiry and confirm that the dashboard reports one verified
   inquiry for the correct location.
5. Repeat the same event identifier and confirm it remains one inquiry.
6. Replace the key immediately if it is exposed.

The WordPress implementation belongs to its separately gated premium sprint.
This contract is the narrow transport it may use; it is not authorization to
change website content.
