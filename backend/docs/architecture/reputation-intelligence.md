# Reputation Intelligence

Status: G1.6D1 implemented locally on 2026-08-10.

## Purpose

Turn authorized, saved customer reviews into useful location and portfolio
decisions without inventing outcomes, hiding the source evidence, or requiring
an AI model to calculate the answer.

## Source of truth

Only `reputation_reviews` rows with `source_type=owned_profile` are included.
Every query is scoped by tenant, organization, campaign, and business location.
Public competitor reviews and legacy synthetic review records cannot enter
these measurements.

## Deterministic measurements

- Current and comparison periods are equal, non-overlapping 30-day windows.
- Positive means 4-5 stars, mixed means 3 stars, and negative means 1-2 stars.
- Response rate uses exact answered and answerable review counts.
- Typical reply time is the median time between the review timestamp and the
  confirmed response timestamp. The sample size is returned with the metric.
- The trend is 12 Monday-aligned weekly buckets and retains zero-review weeks.
- Recurring feedback uses the versioned `service-review-themes-v1` dictionary
  across the latest 180 days. Each returned subject includes up to five review
  IDs as evidence. An AI model does not create or rename these facts.

## Action rules

Actions are derived from measured thresholds and return the current value,
goal, reason, priority, and cited review IDs when applicable. The engine can
surface waiting replies, recurring one- or two-star subjects, reduced review
pace, and reply times over two days. Up to three distinct recurring problem
areas may be shown; the result is not artificially limited to one action.

## Portfolio comparisons

The portfolio endpoint selects one active campaign per active business
location, aggregates exact counts, and orders locations by attention needed.
Comparative outlier claims require at least two locations with saved review
data. Supported comparisons are rating, recent review count, unanswered review
count, and typical reply time. A single location receives no comparative flag.

## Customer API

- `GET /api/v1/reviews/intelligence?campaign_id=...`
- `GET /api/v1/reviews/portfolio`

Both endpoints require a tenant administrator and return only customer-safe
labels. Internal supplier and provider configuration are not returned.

## Customer experience

The Reviews page has two explicit views:

- `This location`: 30-day measures, a 12-week visual trend, recurring customer
  feedback, numbered actions tied to current and goal values, and expandable
  review evidence.
- `All locations`: portfolio measures, a visual location comparison, plain-
  language attention flags, and direct navigation back to a selected location.

## Follow-on boundary

G1.6D2 will add compliant customer review-request campaigns. It must keep
consent, suppression, delivery state, channel price, attribution, and request
history durable. Review gating, incentives conditioned on sentiment, and
selective suppression of dissatisfied customers remain prohibited.
