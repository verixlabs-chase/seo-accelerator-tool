# WordPress Automation Plugin — Enterprise Technical Specification (Future Feature)

Document ID: LSOS-WP-AUTOMATION-SPEC-v1
Status: Planned
Target Audience: Senior Engineers, Staff Engineers, Security Engineers, SRE, Product Architecture, Codex Agents
Last Updated: 2026-02-27
Owner: Platform Architecture

---

## 1. Executive Summary

This document defines the enterprise architecture for a future LSOS WordPress automation capability that can:

1. Apply approved internal-link recommendations to live WordPress content.
2. Publish approved LSOS content drafts to WordPress posts/pages.
3. Maintain deterministic, auditable, reversible execution behavior.

The design is explicitly built for multi-tenant SaaS, enterprise compliance, replay-safe governance, and controlled risk escalation.

---

## 2. Problem Statement

LSOS can generate strategic recommendations and content direction, but execution remains partially manual in most client environments.

Manual execution creates:
- Slow time-to-impact.
- Inconsistent implementation quality.
- Weak traceability between recommendations and outcomes.
- High operational overhead in agency and multi-location settings.

A WordPress automation plugin + control plane integration closes the loop from recommendation to controlled execution.

---

## 3. Goals and Non-Goals

### 3.1 Goals

- Deterministic automation of internal link insertion and content publishing for WordPress sites.
- Strong approval gates with risk-tier controls.
- Full audit trail for every change event.
- Safe rollback of any auto-applied change.
- Multi-tenant secure architecture with org/campaign/site scoping.
- Idempotent, replay-safe execution semantics.

### 3.2 Non-Goals (v1)

- Autonomous generation of long-form content inside plugin.
- Non-WordPress CMS integrations.
- Visual page builder deep integration (Elementor/Divi-specific AST mutation).
- JS-rendered frontend DOM mutation at runtime.

---

## 4. Terminology and Definitions

- **Execution Layer**: System that applies approved actions to external systems (WordPress).
- **Change Action**: Atomic operation proposed by LSOS (e.g., insert link, publish post).
- **Risk Tier (0–4)**:
  - `0`: Insight only (no write).
  - `1`: Draft/staging only.
  - `2`: Low-risk auto-apply allowed.
  - `3`: Approval required.
  - `4`: Structural/high-risk, approval + PR-like review required.
- **Idempotency Key**: Stable execution key preventing duplicate writes for same action.
- **Execution Receipt**: Immutable record of request, response, outcome, hash, and timestamps.
- **Deterministic Payload**: Canonical JSON (sorted keys, fixed precision, stable ordering) used for hash generation.
- **Plugin Site Binding**: Trust relationship between one WordPress instance and one LSOS site identity.

---

## 5. Capability Scope

### 5.1 Internal Link Automation

Supported actions:
- Insert contextual internal links into post/page HTML.
- Enforce per-page max links and per-anchor constraints.
- Skip excluded templates and noindex content.
- Preserve existing editorial links unless replacement policy explicitly enabled.

### 5.2 Content Publishing Automation

Supported actions:
- Create draft post/page from LSOS-approved content payload.
- Publish approved draft with taxonomy, metadata, canonical, and scheduling controls.
- Update existing draft if revision hash matches expected base.

### 5.3 Execution Modes

- `dry_run`: validate and preview changes, no writes.
- `staged_apply`: write to draft/revision only.
- `auto_apply`: write to production where risk policy permits.
- `approval_required`: queue until human approval.

---

## 6. High-Level Architecture

```text
LSOS Strategy/Content Services
        |
        v
Execution Control Plane (API + Queue + Policy Engine)
        |
        v
WordPress Plugin Gateway (Signed Requests)
        |
        v
WP Plugin Runtime
 - Auth verifier
 - Change planner
 - HTML transformer
 - WP REST adapter
 - Rollback manager
 - Telemetry emitter
```

### 6.1 Logical Components

1. **LSOS Control Plane**
- Generates action bundles.
- Evaluates policy/risk tier.
- Signs requests.
- Stores immutable audit records.

2. **WordPress Plugin**
- Authenticates incoming execution commands.
- Resolves target entities (post/page IDs).
- Applies deterministic transforms.
- Emits execution receipts and telemetry.

3. **Observability Plane**
- Centralized metrics/events/traces.
- SLO dashboards and alerts.

---

## 7. Security Model

### 7.1 Trust and Authentication

- Plugin registration via one-time signed bootstrap token.
- Mutual trust using rotating key material:
  - LSOS signs command envelopes.
  - Plugin signs execution receipts.
- Optional IP allowlist for enterprise deployments.

### 7.2 Authorization

- Action scope check must include:
  - `organization_id`
  - `campaign_id`
  - `site_id`
  - `wp_site_binding_id`
- Plugin enforces local role capability boundary:
  - No operation runs with less than required WP capability (`edit_posts`, `publish_posts`, etc.).

### 7.3 Secrets and Key Management

- No plaintext API secrets in DB logs.
- Encrypted credential at rest in LSOS and plugin.
- Key rotation policy:
  - Scheduled every 90 days.
  - Emergency rotation on compromise signal.

### 7.4 Abuse and Safety Controls

- Rate limiting per site binding.
- Replay protection by nonce + timestamp + signature.
- Request TTL max (e.g., 5 minutes) before rejection.

---

## 8. Data Contracts and Canonicalization

### 8.1 Canonical Execution Envelope (Control Plane -> Plugin)

```json
{
  "schema_version": "v1",
  "action_id": "uuid",
  "organization_id": "uuid",
  "campaign_id": "uuid",
  "site_id": "uuid",
  "risk_tier": 2,
  "action_type": "internal_link_insert",
  "idempotency_key": "stable-key",
  "issued_at": "2026-02-27T00:00:00Z",
  "expires_at": "2026-02-27T00:05:00Z",
  "payload": {},
  "payload_hash": "sha256hex",
  "signature": "base64"
}
```

### 8.2 Internal Link Action Payload

```json
{
  "target_post_id": 123,
  "target_post_slug": "local-seo-guide",
  "source_url": "https://site.com/current-page",
  "destination_url": "https://site.com/target-page",
  "anchor_text": "local SEO checklist",
  "placement_strategy": "first_contextual_match",
  "max_links_per_page": 5,
  "allowed_html_blocks": ["p", "li"],
  "deny_selectors": [".toc", ".footer", ".menu"],
  "revision_expected_hash": "sha256hex"
}
```

### 8.3 Content Publish Action Payload

```json
{
  "wp_post_type": "post",
  "title": "...",
  "slug": "...",
  "status": "draft",
  "content_html": "...",
  "excerpt": "...",
  "categories": ["seo"],
  "tags": ["local-seo"],
  "meta": {
    "_yoast_wpseo_title": "...",
    "_yoast_wpseo_metadesc": "..."
  },
  "schedule_at": null,
  "revision_expected_hash": null
}
```

### 8.4 Deterministic Requirements

- Canonical JSON serialization: `sort_keys=true`, compact separators.
- Stable list ordering by deterministic keys.
- Fixed float precision where applicable (6 decimals).
- Stable hash generation using SHA256.

---

## 9. Plugin Runtime Architecture

### 9.1 Modules

- **Auth Module**: signature verification + nonce/replay checks.
- **Resolver Module**: map URLs/slugs to WP object IDs.
- **Transform Module**: HTML AST-safe mutation for links/content.
- **Policy Module**: enforce local safety rules and caps.
- **Execution Module**: call WP native APIs (`wp_update_post`, metadata APIs).
- **Rollback Module**: snapshot before/after and reverse operation support.
- **Telemetry Module**: emit signed receipts/events.

### 9.2 WordPress Integration Surface

- Prefer native WP APIs over raw SQL.
- Use WP hooks for compatibility and eventing:
  - `save_post`
  - `transition_post_status`
- Avoid direct plugin dependency on one SEO plugin; provide adapter interface for metadata providers.

---

## 10. Internal Linking Engine Behavior (Plugin Side)

### 10.1 Candidate Selection

- Resolve target page as destination.
- Parse source page content into deterministic block model.
- Identify anchor candidate occurrences outside deny selectors.
- Apply first valid match by deterministic text position ordering.

### 10.2 Guardrails

- Enforce max links per page and max exact-match anchors.
- Skip if destination already linked in source block.
- Skip if source/destination is noindex or excluded.
- Skip if content hash changed from expected and strict mode enabled.

### 10.3 Output

- Action result includes:
  - `changed=true|false`
  - `reason_code`
  - before/after content hash
  - applied offsets/indexes for forensic traceability

---

## 11. Content Publishing Engine Behavior (Plugin Side)

### 11.1 Create/Update Rules

- If `slug` exists:
  - Update only if status allows and revision policy passes.
- If no slug exists:
  - Create draft with deterministic slug collision strategy.

### 11.2 Publish Safety Rules

- Tier 2 can auto-publish only for allowlisted post types.
- Tier 3/4 requires explicit human approval artifact from LSOS.
- Optional blackout windows to prevent high-traffic-time auto-publishing.

### 11.3 Metadata and SEO Fields

- Metadata applied via adapter contract.
- Failure in metadata write does not silently pass: produce partial-failure receipt.

---

## 12. Idempotency, Retries, and Consistency

### 12.1 Idempotency

- Unique action key: `(site_binding_id, action_type, idempotency_key)`.
- Plugin stores executed action receipts for dedupe window.
- Repeat request returns previous receipt with `status=already_applied`.

### 12.2 Retry Policy

- Retries only for transient transport errors.
- No retry on validation/policy errors.
- Exponential backoff with jitter bounds.

### 12.3 Consistency Strategy

- Precondition hashes for optimistic concurrency.
- Conflict returns deterministic error `revision_mismatch`.

---

## 13. Observability and Audit

### 13.1 Required Events

- `wp_plugin.bound`
- `wp_action.received`
- `wp_action.validated`
- `wp_action.applied`
- `wp_action.skipped`
- `wp_action.failed`
- `wp_action.rolled_back`

### 13.2 Required Metrics

- Action success rate by type and risk tier.
- Mean/95th action latency.
- Retry rates.
- Conflict (`revision_mismatch`) rate.
- Rollback frequency.

### 13.3 Audit Record Requirements

Every write action must persist:
- actor source (`automation`, `user_approved`, `manual_override`)
- action payload hash
- pre/post content hash
- timestamp and version
- reason codes

---

## 14. SLOs and Error Budgets

- **Availability SLO**: 99.9% command acceptance (control plane).
- **Execution SLO**: 99.0% successful eligible low-risk actions.
- **Latency SLO**: p95 < 3s for link insert actions.
- **Safety SLO**: 0 unauthorized write actions.

Error budget policy:
- Exhaustion triggers automation mode downgrade (auto_apply -> approval_required).

---

## 15. Multi-Tenant and Multi-Site Model

### 15.1 Entity Hierarchy

`organization -> portfolio -> campaign -> site_binding -> wp_site`

### 15.2 Isolation Guarantees

- No cross-binding actions.
- Plugin token cannot execute across another site binding.
- Control plane validates org/campaign/site alignment before dispatch.

---

## 16. Compliance and Governance

- Immutable action logs with retention policy.
- Data minimization in logs (no full content bodies in default logs).
- Security review required for:
  - signature scheme changes
  - auth bootstrap changes
  - capability escalation changes

Enterprise controls:
- Change approval matrix by risk tier.
- Dual-approval option for Tier 4 actions.

---

## 17. Performance and Scale Targets

- Support 10,000+ action executions/day across tenant fleet.
- Burst handling for monthly publishing windows.
- Plugin local queue size caps to prevent WP admin degradation.

Optimization strategies:
- Batch fetch for recommendations.
- Incremental content hash checks.
- Asynchronous receipt upload to reduce request blocking.

---

## 18. Testing Strategy

### 18.1 Unit

- Canonical payload hashing determinism.
- Signature verification.
- Link insertion AST transform correctness.
- Idempotency dedupe behavior.

### 18.2 Integration

- WordPress version matrix (latest minus 2 major).
- Plugin compatibility with common SEO plugins.
- End-to-end apply + rollback with real WP test container.

### 18.3 Chaos/Failure

- Network partition during receipt upload.
- Duplicate command replay.
- Concurrent edit conflict race.
- Corrupted nonce store.

### 18.4 Security

- Signature forgery tests.
- Privilege escalation attempts.
- Input sanitization and XSS regression suite.

---

## 19. Rollback and Recovery

### 19.1 Rollback Types

- **Immediate rollback**: revert last action for specific post.
- **Batch rollback**: revert execution window by `action_batch_id`.
- **Mode rollback**: disable auto-apply globally or by tenant/site.

### 19.2 Recovery Runbook

1. Freeze affected automation policy.
2. Identify action set by deterministic hash/time window.
3. Execute rollback plan.
4. Recompute content hash integrity.
5. Re-enable progressively after postmortem sign-off.

---

## 20. API Surface (Proposed)

Control plane endpoints (internal/external split to be finalized):

- `POST /api/v1/wp/bindings/register`
- `POST /api/v1/wp/actions/dispatch`
- `POST /api/v1/wp/actions/{action_id}/approve`
- `POST /api/v1/wp/actions/{action_id}/rollback`
- `GET /api/v1/wp/actions/{action_id}`
- `GET /api/v1/wp/sites/{site_id}/health`

Plugin endpoints:

- `POST /wp-json/lsos/v1/actions/execute`
- `POST /wp-json/lsos/v1/receipts`
- `GET /wp-json/lsos/v1/health`

---

## 21. Feature Flags and Progressive Delivery

Required flags:

- `wp_plugin_integration_enabled`
- `wp_internal_link_auto_apply_enabled`
- `wp_content_publish_enabled`
- `wp_tier3_requires_dual_approval`
- `wp_rollback_enabled`

Rollout policy:
- Dogfood tenants -> pilot tenants -> GA cohorts.
- Gate by tenant plan and explicit legal/security approvals.

---

## 22. Commercialization Model

Potential packaging:

- **Pro**: staged apply, manual approvals.
- **Enterprise**: auto-apply Tier 2, advanced audit and rollback controls.
- **Enterprise+**: multi-site orchestration, dual approval, custom compliance exports.

Usage meters:
- actions executed
- pages modified
- posts published
- rollback operations

---

## 23. Dependency Map

Hard dependencies:
- Provider credential governance.
- Audit/event pipeline.
- Risk-tier recommendation contracts.
- Deterministic serialization/hashing utilities.
- Queue infrastructure and retry policy.

Soft dependencies:
- Executive attribution layer for ROI reporting.
- Portfolio allocation signals for publish/link prioritization.

---

## 24. Delivery Roadmap (Proposed)

### Phase WP-0: Design and Security ADRs

- Finalize auth/signature protocol.
- Approve plugin threat model.
- Define canonical payload schemas.

### Phase WP-1: Read-Only Plugin + Site Binding

- Plugin registration and health checks.
- Read-only diagnostics and dry-run execution receipts.

Exit Criteria:
- Deterministic receipt generation verified.
- No write actions enabled.

### Phase WP-2: Internal Link Staged Apply

- Deterministic insertion engine.
- Tier 1/2 staged apply only.
- Rollback primitives.

Exit Criteria:
- 99% deterministic replay parity in test corpus.
- No uncontrolled link injection incidents.

### Phase WP-3: Controlled Auto-Apply for Links

- Auto-apply for eligible Tier 2.
- Full observability and alerting.

Exit Criteria:
- SLOs stable for 30 days in pilot.

### Phase WP-4: Content Publish Integration

- Draft create/update/publish pipelines.
- Tiered approval workflows.

Exit Criteria:
- End-to-end publish with rollback and audit validated.

### Phase WP-5: Enterprise Hardening + GA

- Compliance exports.
- Advanced policy controls.
- Multi-site orchestration.

---

## 25. Open Questions

- Preferred signature standard (HMAC vs asymmetric signing).
- WordPress minimum version and official support matrix.
- Exact metadata adapter strategy for major SEO plugins.
- Retention period for content snapshots vs privacy constraints.
- Legal approval boundary for autonomous publish in enterprise contracts.

---

## 26. Acceptance Criteria for “Ready to Build”

This feature is implementation-ready only when:

1. ADRs approved for security, auth, and risk-tier behavior.
2. Canonical schemas finalized and versioned.
3. Replay-safe deterministic test harness defined.
4. Rollback runbook approved by SRE and Security.
5. Commercial packaging and entitlement gates signed off by Product + Finance.

---

## 27. Codex Implementation Guidance (Future)

When execution starts, Codex should:

1. Implement Phase WP-0/1 only first.
2. Keep plugin writes disabled behind flags.
3. Add deterministic tests before endpoint wiring.
4. Enforce idempotency and hash contracts as non-optional.
5. Refuse auto-apply implementation unless Tier policy and rollback are complete.
