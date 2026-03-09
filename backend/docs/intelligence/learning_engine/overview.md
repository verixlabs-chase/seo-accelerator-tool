# Self-Learning SEO Intelligence Engine

## System purpose
The self-learning SEO intelligence engine learns from campaign history and improves recommendation quality over time.

It extends current deterministic components and keeps governance and replay guarantees.

## Platform integrations
- Crawl and technical extraction:
  - app/services/crawl_service.py
  - app/services/crawl_parser.py
- Intelligence scoring and recommendation lifecycle:
  - app/services/intelligence_service.py
- Strategy generation:
  - app/services/strategy_engine/engine.py
  - app/services/strategy_build_service.py
- Automation loop:
  - app/services/strategy_engine/automation_engine.py
- KPI and reporting:
  - app/services/analytics_service.py
  - app/services/reporting_service.py
- Tasks and events:
  - app/tasks/tasks.py
  - app/events/emitter.py
  - app/observability/events.py

## Continuous improvement loop

Crawl engine plus rank plus local plus KPI plus automation events
      |
      v
Signal extraction
      |
      v
Temporal signal store
      |
      v
Feature store
      |
      v
Pattern discovery
      |
      v
Recommendation policy
      |
      v
Automation execution
      |
      v
Outcome measurement
      |
      v
Learning feedback updates

## System schematic

+----------------------+      +----------------------+      +----------------------+
| Data producers       | ---> | Signal extraction    | ---> | Temporal store       |
+----------------------+      +----------------------+      +----------------------+
                                                                  |
                                                                  v
                                                        +----------------------+
                                                        | Feature store        |
                                                        +----------------------+
                                                                  |
                                                                  v
                                                        +----------------------+
                                                        | Pattern engine       |
                                                        +----------------------+
                                                                  |
                                                                  v
                                                        +----------------------+
                                                        | Policy engine        |
                                                        +----------------------+
                                                                  |
                                                                  v
                                                        +----------------------+
                                                        | Automation engine    |
                                                        +----------------------+
                                                                  |
                                                                  v
                                                        +----------------------+
                                                        | Outcome tracking     |
                                                        +----------------------+
                                                                  |
                                                                  v
                                                        +----------------------+
                                                        | Learning updater     |
                                                        +----------------------+

## Design principles
- Deterministic core decision path.
- Learning used for calibration of weights and confidence.
- Full artifact versioning across signal, feature, pattern, and policy.
- LLM is for explanation only.
