# Feedback-loop drift detection

Does the feedback loop *detect* distributional drift (the 'continuous assurance' claim), not just log events? We stream a governance metric — the per-query residency-exclusion rate — through the feedback loop's `DriftMonitor`. It runs stable at 10%, then a data regression flips many suppliers out of the EU and the rate jumps to 55%.

Over 200 seeded trials:

| Metric | Result |
|---|---|
| Drift detected after the regression | **98%** |
| Mean detection latency | 25.3 events (median 24.0) |
| False-positive rate on stable streams | **8%** |

This is a deliberately minimal two-window detector — enough to make 'the feedback loop detects drift' a demonstrated capability, not a promise. A production deployment would monitor several metrics (decline rate, grounding score, latency) with a mature change-point method; the architectural point is that the governed trace makes such monitoring possible at all. Deterministic and seeded.

