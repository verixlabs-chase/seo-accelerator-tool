# PORTFOLIO CONTROL PLANE API CONTRACT SPEC

---

## 1. Scope

Define stable API contracts for portfolio control-plane reads.

Endpoints:
- `GET /api/v1/portfolio/{id}/control-plane`
- `GET /api/v1/portfolio/{id}/allocation`
- `GET /api/v1/portfolio/{id}/automation-timeline`

All endpoints require organization-scoped auth.

---

## 2. Common Response Envelope

```json
{
  "success": true,
  "data": {},
  "meta": {
    "request_id": "uuid",
    "organization_id": "uuid"
  },
  "errors": []
}
```

---

## 3. `GET /api/v1/portfolio/{id}/control-plane`

### Response Data

```json
{
  "portfolio_id": "uuid",
  "current_phase": "stabilize",
  "stability_index": 0.812345,
  "latest_evaluation_date": "2026-02-27T00:00:00Z",
  "triggered_rules": ["sustained_positive_momentum"],
  "top_interventions": [
    {
      "campaign_id": "uuid",
      "scenario_id": "ranking_recovery",
      "priority_score": 0.923456
    }
  ],
  "decision_hash": "sha256hex",
  "version_hash": "sha256hex"
}
```

---

## 4. `GET /api/v1/portfolio/{id}/allocation`

### Response Data

```json
{
  "portfolio_id": "uuid",
  "proposal_id": "uuid",
  "status": "generated",
  "window": {
    "start": "2026-03-01",
    "end": "2026-03-31"
  },
  "max_shift": 0.2,
  "allocations": [
    {
      "campaign_id": "uuid",
      "allocation": 0.334567,
      "delta": 0.054321
    }
  ],
  "allocation_sum": 1.0,
  "allocation_hash": "sha256hex"
}
```

---

## 5. `GET /api/v1/portfolio/{id}/automation-timeline`

### Response Data

```json
{
  "portfolio_id": "uuid",
  "items": [
    {
      "evaluation_date": "2026-02-01T00:00:00Z",
      "prior_phase": "recovery",
      "new_phase": "stabilize",
      "triggered_rules": ["volatility_normalized"],
      "decision_hash": "sha256hex"
    }
  ]
}
```

---

## 6. Error Codes

- `portfolio_not_found`
- `portfolio_scope_mismatch`
- `control_plane_data_unavailable`
- `allocation_proposal_unavailable`
- `timeline_unavailable`

---

## 7. Determinism API Requirements

- Stable ordering for arrays.
- Numeric precision fixed at 6 decimals where applicable.
- Hash fields returned exactly as persisted.
- No non-deterministic generated fields in `data` section.

---

## 8. Versioning

- API path remains `v1`.
- Response `meta` must include optional model versions if requested via query:
  - `include_versions=true`

---

## 9. Security Requirements

- Auth required with organization role gate.
- All portfolio reads must validate organization ownership.
- Request/response audit logging mandatory.

---

END OF DOCUMENT