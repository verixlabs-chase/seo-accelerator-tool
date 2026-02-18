# EVENT_CONTRACT_SPEC.md
Generated: 2026-02-18T17:29:02.381145

## INTENT
Standardize module communication via event-driven contracts.

---

## EVENT SCHEMA
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "event_type": "string",
  "timestamp": "ISO8601",
  "payload": {}
}

---

## CORE EVENTS
crawl.completed
rank.snapshot.created
recommendation.generated
recommendation.approved
report.generated