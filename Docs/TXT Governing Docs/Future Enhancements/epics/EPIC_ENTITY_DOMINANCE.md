# EPIC — ENTITY DOMINANCE SCORING

Purpose:
Measure semantic authority vs competitors using entity extraction and gap scoring.

Dependencies:
- Crawl Engine
- SERP Snapshot Storage
- Reference Library

Outputs:
- entity_score (0–100)
- missing_entities[]
- confidence_score
- evidence[]

Acceptance Criteria:
- Entity extraction per URL
- Competitor entity comparison
- Gap report generation