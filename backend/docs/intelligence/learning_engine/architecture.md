# System Architecture Diagrams

## 1. End to end architecture

Crawler and technical parsers
        |
        v
Signal extractor jobs
        |
        v
Temporal signal store
        |
        v
Feature store
        |
        v
Pattern engine
        |
        v
Recommendation policy engine
        |
        v
Automation engine
        |
        v
Outcome tracking
        |
        v
Learning updater

## 2. Runtime component diagram

+-------------------+    +-------------------+    +-------------------+
| Source services   | -> | Extraction layer  | -> | Temporal storage  |
+-------------------+    +-------------------+    +-------------------+
                                                     |
                                                     v
                                           +-------------------+
                                           | Feature store     |
                                           +-------------------+
                                                     |
                                                     v
                                           +-------------------+
                                           | Pattern engine    |
                                           +-------------------+
                                                     |
                                                     v
                                           +-------------------+
                                           | Policy engine     |
                                           +-------------------+
                                                     |
                                                     v
                                           +-------------------+
                                           | Automation engine |
                                           +-------------------+
                                                     |
                                                     v
                                           +-------------------+
                                           | Outcome tracker   |
                                           +-------------------+
                                                     |
                                                     v
                                           +-------------------+
                                           | Learning updater  |
                                           +-------------------+

## 3. Event driven diagram

Event producer
  -> event envelope
  -> event bus
      -> extraction trigger
      -> feature refresh trigger
      -> outcome trigger
      -> learning scheduler trigger

## 4. Data lineage diagram

source row
  -> canonical signal row
  -> feature row
  -> matched pattern
  -> recommendation
  -> automation action
  -> outcome row
  -> learning update event

## 5. Governance boundary diagram

Deterministic policy decisions
   |
   +--> recommendation ranking and risk
   +--> automation gating

LLM explanation layer
   |
   +--> human readable narrative only
   +--> no authority to alter ranking or risk
