"""Unit tests for the feedback-loop drift monitor."""
import importlib.util
import sys
from pathlib import Path

# Load drift.py by file path under a unique module name — the repo binds the shared package
# name `app` to services/agent-runtime (pyproject `pythonpath`), so importing `app.drift`
# would collide with agent-runtime's `app` when both test trees run in one pytest session.
_spec = importlib.util.spec_from_file_location(
    "vcl_feedback_drift", Path(__file__).resolve().parents[1] / "app" / "drift.py")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod  # dataclass (py3.14) resolves cls.__module__ via sys.modules
_spec.loader.exec_module(_mod)
DriftMonitor = _mod.DriftMonitor


def _feed(monitor, values):
    last = {}
    for v in values:
        last = monitor.update(v)
    return last


def test_calibrates_then_stays_quiet_on_stable_stream():
    m = DriftMonitor()
    # a flat, low-rate stream should never flag drift
    flagged = any(m.update(0.1 if i % 10 else 0.0)["drift"] for i in range(300))
    assert flagged is False


def test_detects_a_clear_upward_shift():
    m = DriftMonitor()
    # calibrate on a low baseline...
    _feed(m, [0.0 if i % 5 else 1.0 for i in range(60)])  # ~20% baseline
    # ...then a sustained jump to ~90% must eventually flag drift
    res = _feed(m, [1.0] * 60)
    assert res["drift"] is True
    assert res["z"] is not None and res["z"] > m.k


def test_persistence_debounces_a_single_spike():
    m = DriftMonitor(persistence=6)
    _feed(m, [0.0 if i % 5 else 1.0 for i in range(60)])
    # one short burst shorter than `persistence` should not latch a drift flag
    burst = _feed(m, [1.0] * 3 + [0.2] * 40)
    assert burst["drift"] is False
