# Experiment Design

The experiment engine selects promoted or active strategies, generates a small set of deterministic variants, and evaluates each variant with the digital twin simulation engine before persisting an experiment record.

Stored experiment fields include:

- base strategy
- variant strategy
- campaign
- mutation payload
- predicted rank delta
- predicted traffic delta
- confidence
- expected value
