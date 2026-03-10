# CAMPAIGN_LOGIC_ENGINE.md

## 1) Purpose

Defines the campaign logic engine that encodes LSOS month-by-month execution for a 12-month local SEO roadmap. This document governs automation triggers, recurrence patterns, scoring logic, and operational safeguards for multi-tenant production use.

## 2) Engine Architecture

Core components:
- `CampaignStateService`: current month/stage/status, milestones, freeze windows.
- `RuleEvaluationService`: month rules, prerequisites, completion checks.
- `TaskEmissionService`: queues concrete jobs for modules.
- `ScoringService`: computes KPI and strategy scores.
- `RecoveryService`: gap handling, backfill, rerun planning.

Execution mode:
- Nightly rule evaluation for all active campaigns.
- Event-driven re-evaluation after major pipeline completions.
- Monthly checkpoint transitions only after mandatory milestone completion or approved override.

## 3) Campaign State Model

```text
created -> onboarding -> active(month=1..12) -> completed
                          |                     |
                          +-> paused -----------+
                          +-> archived
```

State fields:
- `campaign_id`
- `tenant_id`
- `current_month` (1-12)
- `month_status` (`pending`, `in_progress`, `blocked`, `complete`)
- `last_rule_eval_at`
- `next_eval_at`
- `required_milestones[]`
- `completed_milestones[]`
- `override_flags[]`

## 4) Month-by-Month Execution Blueprint

## 4.1 Month 1 Requirements

Mandatory workstreams:
- Audit
- Rank setup
- Outreach system build
- Technical optimization

Automations:
- Schedule deep crawl baseline and technical issue extraction.
- Initialize keyword clusters and geo grid for rank tracking.
- Build outreach campaign skeleton, contacts enrichment pipeline, sequence templates.
- Generate technical remediation plan from issue severity.

Month 1 completion criteria:
- Baseline crawl completed with issue severity report.
- Rank tracking daily schedule active for core keywords.
- Outreach base configuration active with at least one sequence ready.
- Technical optimization backlog generated and prioritized.

## 4.2 Month 2 Requirements

Mandatory workstreams:
- On-page optimization
- GBP optimization
- Authority link placement

Automations:
- Trigger on-page task pack from month-1 issue backlog and ranking gaps.
- Trigger local profile health checks and GBP optimization checklist.
- Launch authority placement workflow with target inventory and status tracking.

Month 2 completion criteria:
- On-page optimization actions completed for prioritized pages.
- Local profile optimization state advanced and verified.
- First authority placement cycle initiated and tracked.

## 4.3 Month 3 Requirements

Mandatory workstreams:
- Citation stack (30)
- Location page template
- Topical roadmap
- Health check #1

Automations:
- Create citation campaign batch target count = 30.
- Deploy location page template plan and production schedule.
- Generate topical roadmap from ranking and competitor gaps.
- Run first formal monthly health check with scorecard freeze.

Month 3 completion criteria:
- Citation submission workflows launched toward 30 target.
- Location page template approved and instantiated.
- Topical roadmap published for future months.
- Health check #1 report persisted.

## 4.4 Months 4-12 Recurring Cadence

Mandatory recurring work each month:
- 3 location pages per month
- 2 authority articles per month
- Directory expansion
- Link placements
- Monthly health check
- Strategy check
- Snapshot report

Automations:
- Emit content plan with required monthly quotas.
- Emit outreach/citation expansion jobs with dependency-aware sequencing.
- Execute monthly crawl/rank/review aggregation and scoring.
- Generate snapshot report and recommendation bundle.

Recurring completion criteria:
- Required content counts met or marked with approved exception.
- Health and strategy checks completed.
- Monthly report generated and delivered.

## 5) Rule Engine Design

Rule entities:
- `rule_id`
- `month_scope` (`1`, `2`, `3`, `4-12`)
- `trigger_type` (`scheduled`, `event`, `manual`)
- `prerequisites[]`
- `actions[]`
- `success_criteria[]`
- `failure_policy`

Rule evaluation order:
1. Validate campaign active state and tenant entitlements.
2. Load month-specific rule set.
3. Check prerequisites from persisted milestones.
4. Emit missing actions as tasks.
5. Evaluate completion and block conditions.
6. Persist evaluation result and next evaluation timestamp.

## 6) Automation Trigger Matrix

```text
Trigger: campaign_month_started
  Action: emit month task pack for current month

Trigger: crawl_completed
  Action: recompute technical score, update strategy recommendations

Trigger: rank_window_completed
  Action: recompute visibility score, detect anomalies

Trigger: review_snapshot_ingested
  Action: recompute review velocity score

Trigger: month_close_window
  Action: run health check + strategy check + report generation

Trigger: critical_issue_detected
  Action: create urgent remediation tasks and notify owners
```

## 7) Scoring Logic

## 7.1 Score Categories

- Technical Health Score (0-100)
- Local Visibility Score (0-100)
- Authority Growth Score (0-100)
- Citation Completeness Score (0-100)
- Review Velocity Score (0-100)
- Content Execution Score (0-100)
- Overall Campaign Momentum Score (0-100)

## 7.2 Weighted Composite

Baseline weights:
- Technical Health: 0.22
- Local Visibility: 0.22
- Authority Growth: 0.14
- Citation Completeness: 0.10
- Review Velocity: 0.12
- Content Execution: 0.20

Composite formula:

```text
momentum_score =
  tech*0.22 +
  visibility*0.22 +
  authority*0.14 +
  citations*0.10 +
  reviews*0.12 +
  content*0.20
```

Weight modulation:
- Months 1-3: increase technical/content/citation influence.
- Months 4-12: rebalance toward visibility/authority/reviews growth.

## 7.3 Scoring Inputs

- Technical issue severity deltas from crawl snapshots.
- Ranking deltas by cluster and geo coverage.
- Net backlink quality gains and placement completion.
- Citation submitted/verified ratio.
- Review count/sentiment/velocity trend.
- Content quota completion and indexation evidence.

## 8) Milestone and Quota Enforcement

Quota engine:
- Validates monthly required counts per campaign.
- Supports campaign-specific overrides with audit trail.
- Emits deficit remediation tasks when quotas are short.

Quota defaults (months 4-12):
- `location_pages_required = 3`
- `authority_articles_required = 2`
- `citation_expansion_required = configured_by_campaign`
- `link_placements_required = configured_by_campaign`

## 9) Failure and Recovery Logic

Failure classes:
- Data gap (missing crawl/rank/review snapshots).
- Task exhaustion (dead-letter).
- External dependency outage.
- Rule conflict or invalid prerequisites.

Recovery actions:
- Attempt bounded backfill in same month window.
- If backfill fails, mark metric confidence reduced and continue monthly closure.
- Create operator intervention ticket for persistent dead-letter failures.
- Prevent month advancement if mandatory milestones remain incomplete and no override exists.

## 10) Month Advancement Protocol

Advancement preconditions:
- Mandatory month milestones complete.
- Snapshot report generated.
- No unresolved critical blockers.

Advancement flow:
1. Freeze current month records.
2. Persist month completion summary and scorecard.
3. Increment `current_month`.
4. Emit next month task pack.

End-of-program:
- Month 12 completion triggers campaign closure workflow and final summary report.

## 11) Data Contracts

Required persisted outputs:
- `campaign_milestones`
- `intelligence_scores`
- `strategy_recommendations`
- `anomaly_events`
- `monthly_reports`

Each record must include:
- `tenant_id`
- `campaign_id`
- `source_run_id` or `correlation_id`
- `created_at`
- `algorithm_version` where applicable

## 12) Observability and Governance

Required metrics:
- Rule evaluations per hour.
- Month completion rate and blocked campaigns.
- Quota completion percentages by month.
- Score volatility and anomaly counts.
- Manual override frequency.

Required audit logs:
- Rule evaluation decisions.
- Override usage with actor and reason.
- Month advancement events.
- Strategy recommendation publication.

This document is the governing automation and scoring contract for LSOS campaign execution.
