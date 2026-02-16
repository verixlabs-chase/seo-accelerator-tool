# SRE_SLOS_AND_ALERTING.md

## 1) Scope

Defines LSOS SLI/SLO targets, alert thresholds, paging policy, and error budget governance.

## 2) Service Level Indicators (SLIs)

- API availability: successful requests / total requests.
- API latency: p95 and p99 by endpoint group.
- Queue latency: message enqueue-to-start duration by queue.
- Task success rate: successful task runs / total runs by queue.
- Data freshness:
  - Rank freshness per campaign.
  - Crawl freshness per campaign.
  - Review freshness per campaign.
- Report delivery success rate.

## 3) Service Level Objectives (SLOs)

- API availability: >= 99.9% monthly.
- API p95 latency:
  - reads <= 300 ms
  - writes <= 600 ms
- Queue latency:
  - high-priority queues <= 2 minutes p95
  - reporting queue <= 10 minutes p95 outside month-close peak
- Task success rate:
  - crawl/serp >= 97%
  - intelligence/reporting >= 99%
- Monthly report completion:
  - 95% within 6 hours
  - 99% within 24 hours

## 4) Error Budget Policy

- Availability error budget: 0.1% per month.
- If 50% budget burned in first half of period:
  - Freeze non-critical feature releases.
  - Prioritize reliability fixes.
- If 100% budget exhausted:
  - Reliability-only sprint mode until SLO trend recovers.

## 5) Alerting Thresholds

Critical alerts:
- API availability < 99% over 10 minutes.
- Any cross-tenant authorization violation detected.
- Dead-letter growth > 5x baseline over 15 minutes.
- Report failure ratio > 10% over 30 minutes in month-close window.

High alerts:
- Queue lag > 15 minutes (core queues).
- Replica lag > threshold.
- Task success rate below queue SLO for 30 minutes.

Medium alerts:
- Rising retry rates without failure spikes.
- Elevated p95 latency trending above SLO for 1 hour.

## 6) Paging Policy

- SEV-1: page primary and secondary on-call immediately.
- SEV-2: page primary on-call; escalate if unresolved in 30 minutes.
- SEV-3: open ticket and notify module owner.

## 7) Alert Routing

- API and auth alerts -> platform/on-call.
- Crawl/SERP alerts -> data acquisition module on-call.
- Reporting alerts -> reporting module on-call.
- Security anomalies -> security lead + platform on-call.

## 8) Dashboard Requirements

- Global health overview dashboard.
- Queue and worker performance dashboard.
- Data freshness dashboard by campaign.
- Report generation and delivery dashboard.
- Security and access anomaly dashboard.

## 9) SLO Review Cadence

- Weekly operational review:
  - incidents, near-misses, budget burn.
- Monthly SLO recalibration:
  - adjust thresholds based on stable load trends.

This document is the governing SRE reliability and alerting policy for LSOS.
