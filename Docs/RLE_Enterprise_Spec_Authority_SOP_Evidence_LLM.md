# Reference Library Engine (RLE) — Enterprise Specification
## Authoritative Knowledge, SOP Task Library, Evidence Packs, and Safe LLM Augmentation (DSSIE-Compatible)

**Version:** 1.0 (Enterprise Spec)  
**Generated:** 2026-02-23  
**System Scope:** Local SEO Operating System (LSOS)  
**Primary Consumers:** DSSIE (Strategy Engine), UI/Reporting Layer, Support/Control Plane  
**Design Goals:** Deterministic, versioned, auditable, secure, multi-tenant safe, and resilient  
**Core Principle:** DSSIE never browses the web at runtime. RLE provides curated, versioned citations and SOPs.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)  
2. [Non-Negotiable Requirements](#2-non-negotiable-requirements)  
3. [System Overview](#3-system-overview)  
4. [Reference Library (Authoritative Sources) Data Model](#4-reference-library-authoritative-sources-data-model)  
5. [SOP Task Library Data Model (TaskTypes)](#5-sop-task-library-data-model-tasktypes)  
6. [Evidence Pack Model + Selection Algorithm](#6-evidence-pack-model--selection-algorithm)  
7. [Ingestion Pipeline (Fetch → Parse → Diff → Stage)](#7-ingestion-pipeline-fetch--parse--diff--stage)  
8. [Review & Approval Workflow](#8-review--approval-workflow)  
9. [Release Governance (Versioning, Canary, Rollback, Pinning)](#9-release-governance-versioning-canary-rollback-pinning)  
10. [LLM Augmentation Layer (Safe by Construction)](#10-llm-augmentation-layer-safe-by-construction)  
11. [Validation & Guardrails (No Hallucinations)](#11-validation--guardrails-no-hallucinations)  
12. [APIs (Control Plane + Internal Read APIs)](#12-apis-control-plane--internal-read-apis)  
13. [Background Jobs and Pipeline Design (Celery)](#13-background-jobs-and-pipeline-design-celery)  
14. [Minimal Admin UI Requirements](#14-minimal-admin-ui-requirements)  
15. [Observability, SLAs, and Failure Modes](#15-observability-slas-and-failure-modes)  
16. [Testing & Regression Strategy](#16-testing--regression-strategy)  
17. [Implementation Roadmap](#17-implementation-roadmap)  
18. [Appendices (Templates + Pseudocode + Examples)](#18-appendices-templates--pseudocode--examples)

---

# 1. Executive Summary

The **Reference Library Engine (RLE)** is the authoritative knowledge subsystem that makes DSSIE recommendations **evidence-backed and fact-based** without sacrificing determinism.

RLE provides:
- a curated, whitelisted library of authoritative sources (Google docs, web.dev, schema.org, etc.)
- versioned excerpts (“cite-able evidence”) with hashes and provenance
- a structured **SOP Task Library** (TaskTypes) used for agency replacement outputs
- deterministic mappings from TaskTypes to Evidence Packs
- governed release process (draft → canary → active → rollback)
- org-level version pinning (enterprise stability)
- optional LLM augmentation (rewrite/briefs/support) constrained to the curated library and validated against evidence IDs

**RLE prevents:**
- runtime web browsing and poison risk
- hallucinated advice
- unstable or non-reproducible recommendations

---

# 2. Non-Negotiable Requirements

## 2.1 Determinism
- same inputs + same library version → same evidence pack selection and citations
- stable ordering rules with deterministic tie-breakers

## 2.2 Authority & Trust
- sources must be allowlisted
- every evidence excerpt must have provenance (source snapshot hash)
- sources carry trust_level and status (active/deprecated)

## 2.3 Governance
- versioning of library and SOPs
- canary rollout
- rollback
- org pinning supported

## 2.4 Safety for Non-Experts
- SOP steps and templates must be pre-authored and versioned
- risky tasks must carry safety levels + escalation criteria

## 2.5 Security & Isolation
- strict org_id isolation for pins and entitlements
- no secret leakage
- ingestion pipeline never executes untrusted scripts

---

# 3. System Overview

## 3.1 System Components

1. **Source Registry** — allowlist of authoritative sources
2. **Ingestion Pipeline** — fetch/parse/diff/store snapshots
3. **Excerpt Store** — curated cite-able excerpt units
4. **Claim Store** (optional but recommended) — machine-checkable claims derived from excerpts
5. **TaskType (SOP) Library** — action-native tasks with DoD and verification
6. **Evidence Mapping** — TaskType → excerpt selection rules
7. **Release System** — library versions + membership
8. **Read APIs** — deterministic evidence pack retrieval for DSSIE
9. **Admin UI** — approval workflow and governance controls
10. **LLM Augmentation** — optional, isolated, validated

## 3.2 Relationship to DSSIE

DSSIE does:
- scenario detection + prioritization + roadmap planning

RLE does:
- “what is correct to do” (SOP TaskTypes)
- “why is it correct” (citations to authoritative sources)

DSSIE never invents actions; it selects TaskTypes and evidence packs from RLE.

---

# 4. Reference Library (Authoritative Sources) Data Model

## 4.1 Entities

### 4.1.1 `rle_source`
- `source_id: uuid`
- `publisher: str`
- `domain: str`
- `canonical_url: str`
- `content_type: enum(html,pdf,md)`
- `trust_level: enum(high,medium)`
- `topic_tags: text[]`
- `status: enum(active,deprecated,disabled)`
- `fetch_strategy: enum(static,rendered)`
- `created_at, updated_at`

### 4.1.2 `rle_source_snapshot`
Immutable fetched artifact state for audit.
- `snapshot_id: uuid`
- `source_id: uuid`
- `fetched_at: datetime`
- `http_status: int`
- `etag: str|null`
- `last_modified: str|null`
- `content_hash: str` (sha256 raw)
- `normalized_text_hash: str` (sha256 extracted normalized text)
- `storage_uri: str`
- `parser_version: str`
- `notes: str|null`

### 4.1.3 `rle_excerpt`
Cite-able excerpt unit.
- `excerpt_id: uuid`
- `source_id: uuid`
- `snapshot_id: uuid`
- `section_title: str`
- `excerpt_text: str` (short; compliance-friendly)
- `excerpt_hash: str`
- `applies_to_tags: text[]`
- `status: enum(draft,active,deprecated)`
- `created_at, updated_at`

### 4.1.4 `rle_claim` (recommended)
- `claim_id: uuid`
- `excerpt_id: uuid`
- `claim_type: enum(guideline,requirement,warning,definition)`
- `claim_text: str`
- `applies_to_tags: text[]`
- `risk_level: enum(low,medium,high)`
- `created_at`

### 4.1.5 `rle_library_version`
- `library_version_id: uuid`
- `version_label: str` (e.g., 2026.02.23-01)
- `status: enum(draft,canary,active,rolled_back)`
- `created_at, released_at`
- `release_notes: str`

### 4.1.6 `rle_version_membership`
- `library_version_id: uuid`
- `excerpt_id: uuid`
- `action: enum(added,removed,modified)`
- `excerpt_hash_at_release: str`
- primary key: (library_version_id, excerpt_id)

### 4.1.7 `rle_org_version_pin`
- `org_id: uuid`
- `library_version_id: uuid`
- `pinned_at: datetime`
- `pinned_by: uuid|service`
- `reason: str`

---

# 5. SOP Task Library Data Model (TaskTypes)

## 5.1 Why TaskTypes Live in RLE
Agency replacement requires deterministic, pre-authored SOPs. TaskTypes:
- are stable units
- enable beginner/advanced modes
- provide definition-of-done and verification plans
- can be versioned and approved like citations

## 5.2 `rle_task_type`
- `task_type_id: str` (stable identifier)
- `title_plain: str`
- `objective_plain: str`
- `description_plain: str`
- `category: enum(ctr,gbp,reviews,technical,content,local,ai_visibility,setup)`
- `safety_level: enum(beginner,advanced)`
- `estimated_time_minutes_low: int`
- `estimated_time_minutes_high: int`
- `difficulty: int` (1–5)
- `prerequisites: jsonb` (list of prerequisite codes)
- `steps_sop: jsonb` (ordered steps; each step has substeps)
- `templates: jsonb` (copy/paste patterns)
- `definition_of_done: jsonb` (objective checklist)
- `verification_ruleset_id: str`
- `rollback_guidance: str`
- `escalation_required: bool`
- `escalation_checklist: jsonb`
- `status: enum(draft,active,deprecated)`
- `created_at, updated_at`

## 5.3 `rle_task_ruleset`
Defines deterministic verification.
- `verification_ruleset_id: str`
- `metric: str`
- `min_window_days: int`
- `success_threshold: str` (structured expression, not free text)
- `guard_conditions: jsonb` (stability checks; e.g., impressions ±10%)
- `negative_threshold: str`
- `status: enum(active,deprecated)`

## 5.4 Task Library Versioning (Optional)
If SOP changes must be separated from evidence releases:
- `rle_task_library_version`
- `rle_task_version_membership`

For MVP, align TaskTypes to library_version for simplicity.

---

# 6. Evidence Pack Model + Selection Algorithm

## 6.1 Evidence Pack Definition
An **Evidence Pack** is the set of citations that justify a TaskType in a specific context, returned in deterministic order.

`EvidencePackOut`:
- `task_type_id`
- `library_version_label`
- `citations[]` ordered deterministically
- `claims[]` optional
- `meta` (last verified, trust mix)

## 6.2 Mapping Table: `rle_task_evidence_map`
- `task_type_id`
- `excerpt_id`
- `relevance_weight: float` (0–1)
- `is_required: bool`
- `context_tags_required: text[]|null`
- `context_tags_excluded: text[]|null`

## 6.3 Deterministic Selection Algorithm (Formal)
**Inputs:** `task_type_id`, `org_id`, `context_tags[]`

1. Resolve library version:
   - if org pinned → pinned version
   - else active version
2. Candidate set = all mappings for task_type_id where excerpt is in library version membership.
3. Apply tag filters:
   - exclude any candidate with excluded tags intersecting context_tags
   - if context_tags_required not null: require ⊆ context_tags
4. Sort deterministically:
   - is_required desc
   - relevance_weight desc
   - source trust_level desc
   - publisher asc
   - excerpt_id asc (tie breaker)
5. Output:
   - include all required
   - plus top N additional (configurable)
6. Return EvidencePackOut with stable ordering.

---

# 7. Ingestion Pipeline (Fetch → Parse → Diff → Stage)

## 7.1 Background Job Steps
- Fetch content → snapshot
- Parse & normalize → normalized hash
- Diff vs previous snapshot
- If changed: propose updated excerpts
- Human approves excerpts
- Release built and promoted

## 7.2 Fetch Safety Rules
- HTTPS only
- allowlist domain only
- strict timeout and retry
- max content size
- store raw bytes + headers
- never execute embedded scripts

## 7.3 Parsing & Normalization
- boilerplate removal
- heading segmentation
- preserve section titles
- record parser_version
- store normalized text hash

---

# 8. Review & Approval Workflow

## 8.1 Review States
- draft → active → deprecated

## 8.2 Reviewer Checklist (Deterministic)
- excerpt_text matches source snapshot
- excerpt_text short and citable
- applies_to_tags correct
- claim annotations correct
- risk_level appropriate

---

# 9. Release Governance (Versioning, Canary, Rollback, Pinning)

## 9.1 Release Flow
- create library_version (draft)
- add membership (excerpts + tasktypes)
- promote to canary cohort
- monitor metrics
- promote to active
- rollback if issues

## 9.2 Pinning & Stability
- org pinning ensures enterprise stability
- DSSIE includes library_version_label in outputs for audit

---

# 10. LLM Augmentation Layer (Safe by Construction)

## 10.1 Allowed Uses
- rewrite SOP steps in simpler language
- CMS-specific variants (WordPress/Squarespace)
- generate content briefs from templates
- support assistant grounded in RLE excerpts only

## 10.2 Prohibited Uses
- deciding TaskTypes
- inventing actions
- changing DSSIE scores
- producing facts without citations

## 10.3 Inputs/Outputs
Inputs:
- TaskType SOP + templates
- EvidencePack excerpt_ids
Outputs:
- plain-language variants with citations per sentence

---

# 11. Validation & Guardrails (No Hallucinations)

Validator must enforce:
- every factual statement references excerpt_id or claim_id
- any number mentioned exists in evidence or is flagged as “estimate” with approved template
- disallowed promises blocked (“guaranteed ranking”)

---

# 12. APIs (Control Plane + Internal Read APIs)

## 12.1 Admin APIs (examples)
- POST /control/rle/sources
- POST /control/rle/sources/{id}/fetch
- POST /control/rle/excerpts/{id}/approve
- POST /control/rle/releases
- POST /control/rle/releases/{id}/promote
- POST /control/rle/releases/{id}/rollback
- POST /control/rle/orgs/{org_id}/pin

## 12.2 Internal APIs (DSSIE)
- GET /internal/rle/evidence/task/{task_type_id}?org_id=...&tags=...
- GET /internal/rle/version/active?org_id=...

---

# 13. Background Jobs and Pipeline Design (Celery)

Jobs (idempotent):
- rle_fetch_source_snapshot(source_id)
- rle_parse_snapshot(snapshot_id)
- rle_diff_source(source_id)
- rle_propose_excerpt_updates(source_id)
- rle_release_build(version_label)
- rle_release_promote(version_id, stage)

Each job writes telemetry:
- duration
- status
- failure reason_code

---

# 14. Minimal Admin UI Requirements

Screens:
- Source registry
- Snapshot history + diff
- Excerpt editor + tags + claims
- Approval queue
- Release builder
- Canary promotion + rollback
- Org pin management
- TaskType library editor
- TaskType ↔ evidence mapping editor

---

# 15. Observability, SLAs, and Failure Modes

Metrics:
- snapshot fetch success rate
- diff frequency
- approval latency
- evidence lookup latency
- evidence missing rate in DSSIE outputs

Failure behavior:
- DSSIE degrades gracefully if RLE lookup fails:
  - mark evidence unavailable
  - downgrade confidence band
  - emit admin restoration task

---

# 16. Testing & Regression Strategy

- deterministic sorting tests
- golden evidence pack snapshots by version
- org pin behavior
- rollback behavior
- allowlist enforcement tests
- excerpt hash integrity tests

---

# 17. Implementation Roadmap

**RLE-1 MVP**
- sources, snapshots, excerpts, tasktypes, mapping, active version, read API

**RLE-2 Governance**
- releases (draft/canary/active), rollback, org pinning

**RLE-3 Automation**
- diff-based update suggestions, approval queues

**RLE-4 LLM Readiness**
- claim store + validators + augmentation endpoints

---

# 18. Appendices (Templates + Pseudocode + Examples)

## Appendix A — TaskType YAML Template
```yaml
task_type_id: task.optimize_titles_top_pages
title_plain: "Improve the page titles people see in Google"
objective_plain: "Increase clicks without needing better rankings"
category: ctr
safety_level: beginner
estimated_time_minutes_low: 45
estimated_time_minutes_high: 90
difficulty: 2
prerequisites:
  - CMS_ACCESS
steps_sop:
  - step: "Open the list of pages to edit"
    details:
      - "Use the Top Pages list in the platform"
  - step: "Update titles using the template"
templates:
  - "Primary service + city | Brand"
definition_of_done:
  - "Updated titles for top 5 pages by impressions"
verification_ruleset_id: verify.ctr_uplift_28d
rollback_guidance: "Restore previous titles if CTR declines"
escalation_required: false
```

## Appendix B — Evidence Pack Selection Pseudocode
```text
function buildEvidencePack(task_type_id, org_id, context_tags):
  version = pinned(org_id) or active_version()
  candidates = join(task_evidence_map, version_membership) on excerpt_id
  candidates = filterByTags(candidates, context_tags)
  candidates = sort(
    is_required desc,
    relevance_weight desc,
    trust_level desc,
    publisher asc,
    excerpt_id asc
  )
  return takeRequiredPlusTopN(candidates)
```

## Appendix C — Example Evidence Pack Output
```json
{
  "task_type_id": "task.optimize_titles_top_pages",
  "library_version_label": "2026.02.23-01",
  "citations": [
    {
      "publisher": "Google Search Central",
      "canonical_url": "https://developers.google.com/search/docs/...",
      "section_title": "Title links",
      "excerpt_id": "ex_123",
      "excerpt_hash": "sha256..."
    }
  ]
}
```

---

## End of RLE Enterprise Specification
