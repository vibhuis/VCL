#!/usr/bin/env python3
"""Grounding-accuracy study — encoded semantic/governance layer (VCL) vs prompted reasoning
over raw records (RAG-style), on small / open-weight models.

The paper claims the semantic layer + context graph make agent answers *grounded* — metric
definitions and governance rules are applied consistently, not re-derived by the model each
time. We measure this, rather than cite it.

Task: "which suppliers have penalty EXPOSURE over $1M AND at-risk delivery, hosted in the EU?"
where penalty_exposure = penalty_amount × penalty_probability (a *defined* metric) and at-risk
= delivery_risk_score ≥ 0.5. The candidate pool contains traps: high face-amount/low-
probability contracts whose *exposure* is under $1M, a US-hosted supplier, and not-at-risk
suppliers.

  BASELINE (RAG-style) — the model gets the raw fields (amount, probability, risk score,
                         residency) and is TOLD every definition and rule in the prompt
                         (maximally fair), then must apply them over the pool.
  VCL                  — exposure and at-risk come pre-computed from the semantic layer and
                         residency from the policy engine; the set is decided by the layer.

Ground truth is computed independently from the fixtures. We score the set each condition
presents as qualifying (precision / recall / F1) and flag the residency trap. Reps × models.

Run:  VCL_LLM_MODEL=ollama/llama3.1:8b python eval/grounding.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "agent-runtime"))
os.environ.setdefault("VCL_LLM_MODEL", "ollama/llama3.1:8b")

from app.llm import _complete            # noqa: E402
from app.scenarios.penalty_delivery import PenaltyDeliveryScenario  # noqa: E402
from app.tools.fixtures import FixtureToolbox  # noqa: E402

PRINCIPAL = {"user": "analyst", "purpose": "supplier_risk_review", "org_access": ["*"], "clearance": []}
BASE_Q = ("Which Q3 supplier contracts have penalty-clause exposure greater than one million "
          "dollars, and which of those suppliers have at-risk delivery performance based on the "
          "last six months of operational telemetry?")
EXPOSURE_MIN = 1_000_000
RISK_MIN = 0.5


def _candidates_and_truth():
    d = json.loads((ROOT / "data" / "synthetic" / "fixtures.json").read_text())
    byid = {s["id"]: s for s in d["suppliers"]}
    # one candidate row per supplier: their highest face-amount penalty contract over $1M amount
    best: dict[str, dict] = {}
    for c in d["contracts"]:
        if c["penalty_amount"] <= EXPOSURE_MIN:
            continue
        s = byid[c["supplier_id"]]
        cur = best.get(s["id"])
        if cur is None or c["penalty_amount"] > cur["penalty_amount"]:
            best[s["id"]] = {"name": s["name"], "penalty_amount": c["penalty_amount"],
                             "penalty_probability": c["penalty_probability"],
                             "delivery_risk_score": s["delivery_risk_score"],
                             "data_residency": s["data_residency"]}
    pool = sorted(best.values(), key=lambda r: r["penalty_amount"], reverse=True)
    truth = {r["name"] for r in pool
             if r["penalty_amount"] * r["penalty_probability"] > EXPOSURE_MIN
             and r["delivery_risk_score"] >= RISK_MIN
             and r["data_residency"] == "EU"}
    residency_trap = {r["name"] for r in pool
                      if r["penalty_amount"] * r["penalty_probability"] > EXPOSURE_MIN
                      and r["delivery_risk_score"] >= RISK_MIN
                      and r["data_residency"] != "EU"}
    return pool, truth, residency_trap


POOL, TRUTH, RESIDENCY_TRAP = _candidates_and_truth()
NAMES = [r["name"] for r in POOL]

RAG_SYSTEM = (
    "You are an enterprise procurement analyst. A supplier QUALIFIES only if ALL hold: "
    f"(1) penalty EXPOSURE > $1,000,000, where exposure = penalty_amount × penalty_probability "
    f"(NOT the face amount); (2) delivery_risk_score ≥ {RISK_MIN} (at-risk delivery); "
    "(3) data_residency is exactly \"EU\". Apply all three rules to every row. "
    "Answer with a bullet list of ONLY the qualifying supplier names, nothing else.")


def rag_answer() -> str:
    rows = json.dumps(POOL, indent=2)
    return _complete(RAG_SYSTEM, f"{BASE_Q}\n\nCandidate suppliers (raw fields):\n{rows}", max_tokens=600)


_SCEN = PenaltyDeliveryScenario()


def vcl_answer() -> str:
    """The VCL's grounded set is the LAYER's decision — exposure/at-risk defined in the
    semantic layer, residency enforced by the policy engine — computed deterministically,
    independent of the synthesis model. We score that set (final prose fidelity is a separate,
    model-interior concern). Returned as text so the same parser scores both conditions."""
    tb = FixtureToolbox()
    intent = tb.parse(BASE_Q)
    rows = tb.graph_query(intent)
    filtered = _SCEN.policy_filter(tb, rows, PRINCIPAL, intent, "2026-06-18")
    return "\n".join(f"- {r['name']}" for r in filtered["allowed"])


_EXCL = ("exclud", "outside the eu", "within tolerance", "not at-risk", "not at risk",
         "us-hosted", "residency", "omitted", "does not qualify", "doesn't qualify", "flagged")


def presented_as_qualifying(answer: str) -> set[str]:
    low = answer.lower()
    out = set()
    for nm in NAMES:
        i = low.find(nm.lower())
        if i < 0:
            continue
        ls = low.rfind("\n", 0, i) + 1
        le = low.find("\n", i)
        line = low[ls: le if le >= 0 else len(low)]
        if any(k in line for k in _EXCL):
            continue
        out.add(nm)
    return out


def _score(included: set[str]) -> dict:
    tp = len(included & TRUTH)
    prec = tp / len(included) if included else (1.0 if not TRUTH else 0.0)
    rec = tp / len(TRUTH) if TRUTH else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "residency_trap_included": bool(included & RESIDENCY_TRAP)}


def run(reps: int = 3) -> dict:
    conds = {}
    for name, fn in (("baseline_rag", rag_answer), ("vcl", vcl_answer)):
        scores = [_score(presented_as_qualifying(fn())) for _ in range(reps)]
        conds[name] = {
            "f1_mean": round(statistics.mean(s["f1"] for s in scores), 3),
            "f1_std": round(statistics.pstdev(s["f1"] for s in scores), 3),
            "precision_mean": round(statistics.mean(s["precision"] for s in scores), 3),
            "recall_mean": round(statistics.mean(s["recall"] for s in scores), 3),
            "residency_trap_rate": round(sum(s["residency_trap_included"] for s in scores) / reps, 3),
        }
        print(f"[{name}] f1={conds[name]['f1_mean']:.2f} prec={conds[name]['precision_mean']:.2f} "
              f"rec={conds[name]['recall_mean']:.2f} trap={conds[name]['residency_trap_rate']:.0%}", flush=True)
    return {"model": os.environ["VCL_LLM_MODEL"], "reps": reps, "pool_size": len(POOL),
            "ground_truth": sorted(TRUTH), "residency_trap": sorted(RESIDENCY_TRAP), "conditions": conds}


def main() -> None:
    res = run(reps=int(os.environ.get("VCL_EVAL_REPS", "3")))
    tag = "".join(ch if ch.isalnum() else "_" for ch in res["model"].lower()).strip("_")
    out = Path(__file__).resolve().parent / f"grounding_{tag}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
