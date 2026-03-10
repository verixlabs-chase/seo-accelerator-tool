# Promotion And Demotion Rules

Lifecycle rules:

- `candidate`: fewer than 3 samples
- `promoted`: score >= 0.70 with enough support
- `active`: between the promotion and demotion thresholds
- `demoted`: score <= 0.35 with enough support

Lifecycle changes update persisted performance state and emit graph evidence so the rest of the intelligence stack can reuse the result.
