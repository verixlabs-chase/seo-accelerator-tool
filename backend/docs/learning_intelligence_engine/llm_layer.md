# LLM Strategy Explanation Layer

## Purpose
Provide human readable strategy explanations for recommendations and outcomes.

## Strict boundary
The LLM does not decide recommendation priority, risk, or execution eligibility.

Authoritative decision source remains:
- recommendation policy engine
- deterministic strategy and automation services

## Inputs to explanation layer
- recommendation payload
- matched patterns
- evidence features
- confidence and risk values
- outcome history summaries

## Outputs
- operator friendly explanation
- concise action rationale
- expected outcome narrative
- caveats and assumptions

## Prompt template example

System role:
Explain SEO strategy decisions using provided structured evidence. Do not invent data.

Input object:
- campaign context
- recommendation list
- feature evidence
- active patterns
- confidence and risk scores

Output format:
- summary
- why now
- expected impact
- risk notes
- monitoring plan

## Example call contract

    {
      task: explain_recommendations,
      campaign_id: cmp_001,
      recommendation_ids: [rec_001, rec_002],
      include_evidence: true,
      include_monitoring_steps: true
    }

## Governance
- include source references in explanation metadata
- store prompt and response hashes for traceability
- reject output if it conflicts with authoritative scores
