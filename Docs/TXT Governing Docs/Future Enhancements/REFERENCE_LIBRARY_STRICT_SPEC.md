# REFERENCE LIBRARY — STRICT SPECIFICATION (V6)

Generated: 2026-02-18T16:31:23.806508

## STRICT DEFINITIONS

**Metric**  
Measurable system value with defined units, percentile model, thresholds, validation.

**Threshold**  
Boundary defining Good / Needs Improvement / Poor states.

**Diagnostic Signal**  
Secondary metric used to infer root cause.

**Recommendation**  
Structured remediation action tied to diagnostic signals.

**Validation Rule**  
Measurement confirming recommendation success.

---

## INTENT BLOCK

### Purpose
Authoritative knowledge layer for Recommendation Engines.

### Requirements
- Data-driven JSON/YAML only
- Versioned (semver)
- Hot reloadable
- CI schema validation enforced

### Prohibited
- Execution logic inside library
- Hardcoded thresholds in service code

### Integration
RecommendationEngine → ReferenceLibrary.get(metric_key)

### Acceptance Criteria
- Schema validated in CI
- Metrics include thresholds + units + validation
- Recs include impact + effort + risk_tier