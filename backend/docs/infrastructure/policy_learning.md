# Policy Learning

Policy learning now persists weights in `policy_weights`. Recommendation outcomes update stored weights, confidence, and sample size. Policy scoring loads those persisted weights so the next recommendation cycle uses learned values instead of transient return data.
