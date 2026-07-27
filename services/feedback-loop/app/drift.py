"""Minimal distributional-drift monitor for the feedback loop.

The VCL's fifth component claims *continuous assurance* — the feedback loop should surface when
the behaviour of the governed system shifts (a data regression, a policy change, a population
shift) rather than merely logging events. This is a deliberately small, honest realisation of
that claim: a monitored metric stream (e.g. the per-query residency-exclusion rate, decline
rate, or answer-grounding score) is watched with a two-window test — a fixed reference window
establishes the baseline mean/σ, and each incoming value updates a sliding recent window whose
mean is compared to the baseline. Drift is flagged when the recent mean is more than ``k``
standard errors from the reference.

It is not a research-grade change-point detector; it is enough to make "the feedback loop
detects drift" a demonstrated capability rather than a promise (see eval/drift.py).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class DriftMonitor:
    reference_size: int = 50      # events used to establish the baseline
    window: int = 40             # sliding recent-window size compared to the baseline
    k: float = 5.0               # flag when recent mean is > k standard errors from baseline
    persistence: int = 6         # require this many consecutive breaches (debounce transients)
    _ref: list[float] = field(default_factory=list)
    _recent: deque = field(default_factory=deque)
    ref_mean: float | None = None
    ref_std: float | None = None
    n: int = 0
    _run: int = 0                # consecutive-breach run length

    def update(self, value: float) -> dict:
        """Feed one metric value; return {'drift': bool, 'z': float|None, 'index': n}."""
        self.n += 1
        if self.ref_mean is None:
            self._ref.append(value)
            if len(self._ref) >= self.reference_size:
                self.ref_mean = sum(self._ref) / len(self._ref)
                var = sum((x - self.ref_mean) ** 2 for x in self._ref) / len(self._ref)
                # floor σ so a near-constant baseline doesn't make every wobble "infinite σ"
                self.ref_std = max(math.sqrt(var), 1e-6)
            return {"drift": False, "z": None, "index": self.n, "calibrating": True}

        self._recent.append(value)
        if len(self._recent) > self.window:
            self._recent.popleft()
        if len(self._recent) < self.window:
            return {"drift": False, "z": None, "index": self.n, "calibrating": True}

        recent_mean = sum(self._recent) / len(self._recent)
        se = self.ref_std / math.sqrt(len(self._recent))
        z = (recent_mean - self.ref_mean) / se if se else 0.0
        self._run = self._run + 1 if abs(z) > self.k else 0
        return {"drift": self._run >= self.persistence, "z": round(z, 2), "index": self.n,
                "run": self._run, "recent_mean": round(recent_mean, 4),
                "ref_mean": round(self.ref_mean, 4), "calibrating": False}
