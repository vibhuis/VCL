#!/usr/bin/env python3
"""Feedback-loop drift-detection study — is 'continuous assurance' a demonstrated capability?

We exercise the feedback loop's DriftMonitor (services/feedback-loop/app/drift.py) on a stream
of a governance metric: the per-query residency-exclusion rate. In the STABLE phase the rate is
low (a small, steady fraction of queries touch an out-of-EU supplier). Then a data regression
is injected — many suppliers' data_residency flips to non-EU — and the exclusion rate jumps.
A useful feedback loop should flag the shift quickly, without crying wolf on stable streams.

Reported over T seeded trials: detection rate, mean detection latency (events after the change),
and false-positive rate on pure-stable streams of equal length.

Run: `python eval/drift.py`  (deterministic, seeded; no services, no LLM).
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "feedback-loop"))

from app.drift import DriftMonitor  # noqa: E402

STABLE_RATE = 0.10      # ~10% of queries hit an out-of-EU supplier (steady state)
DRIFT_RATE = 0.55       # after a residency regression, the exclusion rate spikes
PRE = 120               # events before the regression (covers calibration + steady run)
POST = 120              # events after the regression


def _stream(rng: random.Random, drift_at: int | None) -> list[float]:
    out = []
    for i in range(PRE + POST):
        rate = DRIFT_RATE if (drift_at is not None and i >= drift_at) else STABLE_RATE
        out.append(1.0 if rng.random() < rate else 0.0)
    return out


def _first_flag(stream: list[float], after: int = 0) -> int | None:
    m = DriftMonitor()
    for i, v in enumerate(stream):
        r = m.update(v)
        if r["drift"] and i >= after:
            return i
    return None


def run(trials: int = 200) -> dict:
    detections, latencies, false_positives = 0, [], 0
    for t in range(trials):
        rng = random.Random(1000 + t)
        # (a) drift stream: regression at PRE — measure detection + latency
        flag = _first_flag(_stream(rng, drift_at=PRE))
        if flag is not None and flag >= PRE:
            detections += 1
            latencies.append(flag - PRE)
        # (b) stable stream (no regression): any flag is a false positive
        rng2 = random.Random(5000 + t)
        if _first_flag(_stream(rng2, drift_at=None)) is not None:
            false_positives += 1
    return {
        "trials": trials,
        "stable_rate": STABLE_RATE, "drift_rate": DRIFT_RATE,
        "detection_rate": round(detections / trials, 3),
        "mean_detection_latency_events": round(statistics.mean(latencies), 1) if latencies else None,
        "median_detection_latency_events": statistics.median(latencies) if latencies else None,
        "false_positive_rate": round(false_positives / trials, 3),
    }


def main() -> None:
    res = run(trials=int(sys.argv[1]) if len(sys.argv) > 1 else 200)
    outdir = Path(__file__).resolve().parent
    (outdir / "drift_results.json").write_text(json.dumps(res, indent=2))
    md = ["# Feedback-loop drift detection", "",
          "Does the feedback loop *detect* distributional drift (the 'continuous assurance' "
          "claim), not just log events? We stream a governance metric — the per-query "
          f"residency-exclusion rate — through the feedback loop's `DriftMonitor`. It runs "
          f"stable at {STABLE_RATE:.0%}, then a data regression flips many suppliers out of the "
          f"EU and the rate jumps to {DRIFT_RATE:.0%}.", "",
          f"Over {res['trials']} seeded trials:", "",
          "| Metric | Result |", "|---|---|",
          f"| Drift detected after the regression | **{res['detection_rate']:.0%}** |",
          f"| Mean detection latency | {res['mean_detection_latency_events']} events "
          f"(median {res['median_detection_latency_events']}) |",
          f"| False-positive rate on stable streams | **{res['false_positive_rate']:.0%}** |", "",
          "This is a deliberately minimal two-window detector — enough to make 'the feedback loop "
          "detects drift' a demonstrated capability, not a promise. A production deployment would "
          "monitor several metrics (decline rate, grounding score, latency) with a mature "
          "change-point method; the architectural point is that the governed trace makes such "
          "monitoring possible at all. Deterministic and seeded.", ""]
    (outdir / "drift_results.md").write_text("\n".join(md) + "\n")
    print(json.dumps(res, indent=2))
    print(f"\nwrote {outdir/'drift_results.json'} and .md")


if __name__ == "__main__":
    main()
