#!/usr/bin/env python3
"""VCL evaluation harness — reproducible measurements for the paper's evaluation section.

Runs four controlled studies against the live stack and writes machine-readable results
to eval/results.json plus a Markdown report to eval/results.md:

  A. Policy-enforcement coverage  — block/mask rate on a suite of prohibited actions vs a
                                    permit rate on benign actions (VCL vs an ungoverned baseline).
  B. Trace-evidence coverage       — for each EU AI Act / NIST obligation, whether the trace
                                    CARRIES the machine-checkable field(s) that obligation
                                    requires (an auditor-inspectable record) — not a claim that
                                    a deployment *satisfies* the obligation. VCL vs no-trace.
  C. Tamper-evidence              — detection rate of a tampered audit trail (and false-positive
                                    rate on intact trails).
  D. Governance latency overhead  — end-to-end query latency and the policy/audit share.

Prerequisites: `docker compose up -d` (stack healthy). Run: `python eval/evaluate.py`.
Everything is deterministic given the seeded synthetic data, so results reproduce.
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

AGENT = os.environ.get("VCL_AGENT_URL", "http://localhost:8000")
OPA = os.environ.get("VCL_POLICY_URL", "http://localhost:8181")
FEEDBACK = os.environ.get("VCL_FEEDBACK_URL", "http://localhost:8200")
ROOT = Path(__file__).resolve().parents[1]
AUDIT_DB = ROOT / "data" / "audit.sqlite"
AS_OF = "2026-06-18"

Q_PAPER = ("Which Q3 supplier contracts have penalty-clause exposure greater than one million "
           "dollars, and which of those suppliers have at-risk delivery performance based on the "
           "last six months of operational telemetry?")
Q_GDPR = ("Show me the top five suppliers in EMEA with contracts expiring before December 2026, "
          "where the contracts contain PII clauses. Only include suppliers whose data subjects "
          "have valid GDPR consent.")


def opa(rule: str, payload: dict) -> dict:
    r = httpx.post(f"{OPA}/v1/data/vcl/{rule}", json={"input": payload}, timeout=10)
    r.raise_for_status()
    return r.json().get("result", {})


# ----------------------------------------------------------------- Study A
def study_policy_coverage() -> dict:
    """A deterministic suite of prohibited actions (must be blocked/masked) and benign actions
    (must be permitted). Reports enforcement rate under VCL and the implicit baseline (an
    ungoverned agent applies no runtime enforcement → 0% of prohibited actions blocked)."""
    prohibited, benign = [], []

    # require_residency_match: EU-subject query, data hosted outside the EU → deny
    for res in ["US", "APAC", "UK-NONEU", "IN"]:
        prohibited.append(("require_residency_match",
                           {"context": {"residency_scope": "EU"}, "resource": {"data_residency": res}}, "deny"))
    benign.append(("require_residency_match",
                   {"context": {"residency_scope": "EU"}, "resource": {"data_residency": "EU"}}, "allow"))
    benign.append(("require_residency_match",
                   {"context": {"residency_scope": "GLOBAL"}, "resource": {"data_residency": "US"}}, "allow"))

    # allow_pii_field_access: expired/missing consent → mask; no purpose → deny
    for ret in ["2026-01-01", "2025-06-01", "2024-12-31"]:
        prohibited.append(("allow_pii_field_access",
                           {"as_of": AS_OF, "principal": {"purpose": "supplier_risk_review"},
                            "resource": {"consent_retention_until": ret}}, "mask"))
    prohibited.append(("allow_pii_field_access",
                       {"as_of": AS_OF, "principal": {"purpose": "supplier_risk_review"},
                        "resource": {"consent_retention_until": None}}, "mask"))
    prohibited.append(("allow_pii_field_access",
                       {"as_of": AS_OF, "principal": {"purpose": ""},
                        "resource": {"consent_retention_until": "2027-01-01"}}, "deny"))
    benign.append(("allow_pii_field_access",
                   {"as_of": AS_OF, "principal": {"purpose": "supplier_risk_review"},
                    "resource": {"consent_retention_until": "2027-06-01"}}, "allow"))

    # mask_secrets_in_response
    prohibited.append(("mask_secrets_in_response", {"resource": {"contains_secrets": True}}, "mask"))
    benign.append(("mask_secrets_in_response", {"resource": {"contains_secrets": False}}, "allow"))

    # redact_commercial_terms: confidential term without contract-detail clearance → mask
    prohibited.append(("redact_commercial_terms",
                       {"principal": {"clearance": []}, "resource": {"commercial_confidential": True}}, "mask"))
    benign.append(("redact_commercial_terms",
                   {"principal": {"clearance": ["contract_detail"]}, "resource": {"commercial_confidential": True}}, "allow"))
    benign.append(("redact_commercial_terms",
                   {"principal": {"clearance": []}, "resource": {"commercial_confidential": False}}, "allow"))

    # mask_supplier_contact_pii
    prohibited.append(("mask_supplier_contact_pii", {"resource": {"has_contact_pii": True}}, "mask"))
    benign.append(("mask_supplier_contact_pii", {"resource": {"has_contact_pii": False}}, "allow"))

    # allow_supplier_query: out-of-scope region → deny
    for geo in ["AMER", "APAC", "LATAM"]:
        prohibited.append(("allow_supplier_query",
                           {"principal": {"org_access": ["EMEA"]}, "resource": {"geo": geo}}, "deny"))
    benign.append(("allow_supplier_query",
                   {"principal": {"org_access": ["EMEA"]}, "resource": {"geo": "EMEA"}}, "allow"))

    blocked = sum(1 for rule, inp, want in prohibited if opa(rule, inp).get("outcome") == want)
    permitted = sum(1 for rule, inp, want in benign if opa(rule, inp).get("outcome") == want)
    return {
        "prohibited_actions": len(prohibited),
        "prohibited_blocked_vcl": blocked,
        "prohibited_block_rate_vcl": round(blocked / len(prohibited), 4),
        "prohibited_block_rate_baseline": 0.0,  # ungoverned agent: no runtime enforcement
        "benign_actions": len(benign),
        "benign_permitted": permitted,
        "false_block_rate_vcl": round(1 - permitted / len(benign), 4),
    }


# ----------------------------------------------------------------- Study B
def _run(query: str) -> dict:
    return httpx.post(f"{AGENT}/query", json={"query": query}, timeout=60).json()


def _trace(trace_id: str) -> dict:
    return httpx.get(f"{FEEDBACK}/trace/{trace_id}", timeout=15).json()


def study_obligation_coverage() -> dict:
    """For each obligation, an automated check decides whether the trace CARRIES the specific
    machine-checkable field(s) an auditor would need to evaluate that obligation (e.g. a
    timestamped record for Art. 12, a residency decision for Art. 10, a stated reason for the
    redaction for Art. 13). This measures whether the trace is *auditable against* each
    obligation — NOT that a real deployment *satisfies* it. Baseline = an ungoverned agent that
    returns only an answer (no governed trace) → none of these fields exist to check."""
    d = _run(Q_PAPER)
    tr = _trace(d["trace_id"])
    events = tr["events"]
    answer = d["answer"]
    arts = {a for e in events for a in e["regulatory_mapping"]["eu_ai_act_articles"]}
    decisions = [pd for e in events for pd in e.get("policy_decisions", [])]

    checks = {
        "EU AI Act Art. 9 (risk management)":
            any(x.get("outcome") in ("deny", "mask") for x in decisions),
        "EU AI Act Art. 10 (data governance)":
            any(x.get("policy") == "require_residency_match" for x in decisions),
        "EU AI Act Art. 12 (record-keeping)":
            tr["event_count"] >= 5 and all("timestamp" in e for e in events),
        "EU AI Act Art. 13 (transparency)":
            "[redacted: policy" in answer and any(x.get("reasons") for x in decisions),
        "EU AI Act Art. 14 (human oversight)":
            "14" in arts and bool(events[0].get("principal")),
        "NIST RMF MEASURE-2.7 (security/resilience)":
            tr.get("integrity", {}).get("valid") is True,
    }
    evidenced = sum(1 for v in checks.values() if v)
    return {
        "obligations_checked": len(checks),
        "evidenced_by_trace_vcl": evidenced,
        "coverage_vcl": round(evidenced / len(checks), 4),
        "coverage_baseline": 0.0,
        "detail": {k: bool(v) for k, v in checks.items()},
    }


# ----------------------------------------------------------------- Study C
def study_tamper_evidence(n: int = 40) -> dict:
    """Post N short traces, tamper a random step in each, and measure the detection rate.
    Also measure the false-positive rate on N intact traces."""
    def post_trace(tid: str, steps: int = 6):
        for i in range(1, steps + 1):
            ev = {"trace_id": tid, "step_id": f"{tid}-{i}", "timestamp": f"2026-06-21T00:00:0{i}Z",
                  "component": "agent", "action": f"s{i}", "principal": {"user": "eval"},
                  "input": {}, "output": {"i": i}, "policy_decisions": [],
                  "regulatory_mapping": {"eu_ai_act_articles": ["12"], "nist_rmf_functions": ["MEASURE-2.7"]}}
            httpx.post(f"{FEEDBACK}/events", json=ev, timeout=5)

    if not AUDIT_DB.exists():
        return {"skipped": "audit.sqlite not reachable on host"}

    detected = 0
    for k in range(n):
        tid = f"eval-tamper-{uuid.uuid4()}"
        post_trace(tid)
        assert httpx.get(f"{FEEDBACK}/verify/{tid}", timeout=5).json()["valid"] is True
        # tamper a random middle row's payload
        con = sqlite3.connect(AUDIT_DB)
        rows = [r[0] for r in con.execute("SELECT row_id FROM trace_events WHERE trace_id=? ORDER BY row_id", (tid,))]
        target = rows[len(rows) // 2]
        con.execute("UPDATE trace_events SET payload=? WHERE row_id=?", ('{"tampered":true}', target))
        con.commit()
        con.close()
        if httpx.get(f"{FEEDBACK}/verify/{tid}", timeout=5).json()["valid"] is False:
            detected += 1

    # false positives: intact traces should verify True
    fp = 0
    for k in range(n):
        tid = f"eval-intact-{uuid.uuid4()}"
        post_trace(tid)
        if httpx.get(f"{FEEDBACK}/verify/{tid}", timeout=5).json()["valid"] is not True:
            fp += 1
    return {
        "tampered_traces": n, "detected": detected,
        "detection_rate": round(detected / n, 4),
        "intact_traces": n, "false_positives": fp,
        "false_positive_rate": round(fp / n, 4),
    }


# ----------------------------------------------------------------- Study D
def _step_latencies(events: list[dict]) -> dict:
    ts = [datetime.fromisoformat(e["timestamp"]) for e in events]
    durs = {}
    for i in range(1, len(ts)):
        label = f"{events[i-1]['component']}:{events[i-1]['action']}"
        durs[label] = round((ts[i] - ts[i - 1]).total_seconds() * 1000, 2)
    return durs


def study_latency(m: int = 30) -> dict:
    """End-to-end query latency (deterministic mode) and the in-pipeline governance share.

    Governance overhead is taken from the trace itself (the precheck + per-row-filter steps),
    i.e. the real cost inside the request path — not a naive per-call micro-benchmark, which
    over-counts by paying a fresh TCP/HTTP handshake the pipeline's keep-alive client avoids.
    """
    lat = []
    for _ in range(m):
        t0 = time.perf_counter()
        _run(Q_PAPER)
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()

    # per-step breakdown + governance share, averaged over a few representative traces
    gov, tot, steps_last = [], [], {}
    for _ in range(5):
        d = _run(Q_PAPER)
        steps_last = _step_latencies(_trace(d["trace_id"])["events"])
        g = sum(v for k, v in steps_last.items() if k.startswith("policy_engine"))
        gov.append(g)
        tot.append(sum(steps_last.values()))
    gov_ms = round(statistics.mean(gov), 2)
    trace_total = round(statistics.mean(tot), 2)

    # component micro-benchmark: per-decision OPA latency with a keep-alive connection
    with httpx.Client(timeout=10) as c:
        c.post(f"{OPA}/v1/data/vcl/require_residency_match",
               json={"input": {"context": {"residency_scope": "EU"}, "resource": {"data_residency": "US"}}})
        k = 200
        t0 = time.perf_counter()
        for _ in range(k):
            c.post(f"{OPA}/v1/data/vcl/require_residency_match",
                   json={"input": {"context": {"residency_scope": "EU"}, "resource": {"data_residency": "US"}}})
        per_decision = (time.perf_counter() - t0) * 1000 / k

    d = _run(Q_PAPER)
    return {
        "runs": m,
        "total_ms_mean": round(statistics.mean(lat), 1),
        "total_ms_median": round(statistics.median(lat), 1),
        "total_ms_p95": round(lat[int(0.95 * m) - 1], 1),
        "per_step_ms": steps_last,
        "policy_decisions_in_query": len(d["decisions"]),
        "governance_ms_in_pipeline": gov_ms,
        "governance_overhead_pct": round(gov_ms / trace_total, 4) if trace_total else None,
        "opa_ms_per_decision_keepalive": round(per_decision, 3),
    }


def main() -> None:
    httpx.get(f"{AGENT}/healthz", timeout=10).raise_for_status()
    results = {
        "as_of": AS_OF,
        "A_policy_enforcement_coverage": study_policy_coverage(),
        "B_regulatory_obligation_coverage": study_obligation_coverage(),
        "C_tamper_evidence": study_tamper_evidence(),
        "D_governance_latency": study_latency(),
    }
    out = Path(__file__).resolve().parent
    (out / "results.json").write_text(json.dumps(results, indent=2))
    _write_markdown(results, out / "results.md")
    print(json.dumps(results, indent=2))
    print(f"\nwrote {out/'results.json'} and {out/'results.md'}")


def _write_markdown(r: dict, path: Path) -> None:
    a, b, c, d = (r["A_policy_enforcement_coverage"], r["B_regulatory_obligation_coverage"],
                  r["C_tamper_evidence"], r["D_governance_latency"])
    L = ["# VCL evaluation results", "",
         "Reproduce: `docker compose up -d && python eval/evaluate.py`. Deterministic on the "
         "seeded synthetic data.", "",
         "## A. Policy-enforcement coverage",
         "| Metric | VCL | Ungoverned baseline |", "|---|---|---|",
         f"| Prohibited actions blocked | {a['prohibited_blocked_vcl']}/{a['prohibited_actions']} "
         f"({a['prohibited_block_rate_vcl']:.0%}) | {a['prohibited_block_rate_baseline']:.0%} |",
         f"| Benign actions permitted | {a['benign_permitted']}/{a['benign_actions']} | — |",
         f"| False-block rate | {a['false_block_rate_vcl']:.0%} | — |", "",
         "## B. Trace-evidence coverage (does the trace carry the auditor-checkable field?)",
         "For each obligation, whether the trace carries the specific machine-checkable field(s) "
         "an auditor needs to evaluate it — *auditable against*, not *satisfies*.", "",
         f"Trace-evidence present with VCL: **{b['evidenced_by_trace_vcl']}/{b['obligations_checked']} "
         f"({b['coverage_vcl']:.0%})** · baseline (no governed trace): {b['coverage_baseline']:.0%}", "",
         "| Obligation | Required field present in trace |", "|---|---|"]
    L += [f"| {k} | {'yes' if v else 'no'} |" for k, v in b["detail"].items()]
    L += ["", "## C. Tamper-evidence",
          f"- Tamper detection rate: **{c.get('detected','–')}/{c.get('tampered_traces','–')} "
          f"({c.get('detection_rate',0):.0%})**",
          f"- False-positive rate on intact trails: {c.get('false_positive_rate',0):.0%} "
          f"({c.get('false_positives','–')}/{c.get('intact_traces','–')})", "",
          "## D. Governance latency overhead",
          f"- End-to-end query latency (n={d['runs']}, deterministic mode): "
          f"mean {d['total_ms_mean']} ms, median {d['total_ms_median']} ms, p95 {d['total_ms_p95']} ms",
          f"- In-pipeline governance (precheck + per-row policy filter, {d['policy_decisions_in_query']} "
          f"decisions): **{d['governance_ms_in_pipeline']} ms "
          f"({d['governance_overhead_pct']:.0%} of the traced path)**",
          f"- OPA decision latency (keep-alive): {d['opa_ms_per_decision_keepalive']} ms/decision",
          "", "Per-step latency (representative trace):", "",
          "| Step | ms |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in d["per_step_ms"].items()]
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
