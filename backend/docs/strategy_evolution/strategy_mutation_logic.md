# Strategy Mutation Logic

Variants are generated deterministically from the base strategy identifier.

Rules:

- internal-link strategies scale link count
- content strategies scale page count
- technical strategies scale fix count
- industry priors are injected into variant action payloads

Each variant receives a unique `variant_strategy_id` and a plain-language hypothesis.
