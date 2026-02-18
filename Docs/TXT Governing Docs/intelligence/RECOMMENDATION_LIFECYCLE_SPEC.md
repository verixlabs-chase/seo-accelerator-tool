# RECOMMENDATION_LIFECYCLE_SPEC.md
Generated: 2026-02-18T17:29:02.381145

## INTENT
Defines state machine and safety rules for recommendation lifecycle.

---

## STATES
DRAFT
GENERATED
VALIDATED
APPROVED
SCHEDULED
EXECUTED
FAILED
ROLLED_BACK
ARCHIVED

---

## REQUIRED FIELDS
- confidence_score (0–1 float)
- evidence[] (non-empty array)
- risk_tier (0–4 int)
- rollback_plan (non-empty text/json)