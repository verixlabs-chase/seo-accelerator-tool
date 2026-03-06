# Diagrams

## 1) Graph structure
~~~text
(campaign) --derived_from--> (feature)
(feature)  --derived_from--> (pattern)
(pattern)  --correlates_with--> (strategy)
(strategy) --improves/causes--> (outcome)
(campaign) --derived_from--> (outcome)
~~~

## 2) Learning pipeline
~~~text
recommendation outcomes
          +
digital twin simulations
          +
pattern detection
          |
          v
   graph update pipeline
(event normalize -> derive -> score -> validate -> upsert)
          |
          v
    GLOBAL LEARNING GRAPH
~~~

## 3) Query integration
~~~text
recommendation engine -----> query engine -----> global learning graph
          ^                         |                     |
          |                         v                     v
digital twin simulations <--- scored evidence <--- edge metadata + lineage
~~~

## 4) Cross-campaign knowledge flow
~~~text
Campaign A outcomes ----+
Campaign B outcomes ----+--> shared graph evidence --> Campaign C strategy priors
Campaign D simulations -+

Industry-conditioned transfer:
industry context -> strategy edges -> new campaign bootstrap recommendations
~~~
