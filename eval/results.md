# VCL evaluation results

Reproduce: `docker compose up -d && python eval/evaluate.py`. Deterministic on the seeded synthetic data.

## A. Policy-enforcement coverage
| Metric | VCL | Ungoverned baseline |
|---|---|---|
| Prohibited actions blocked | 15/15 (100%) | 0% |
| Benign actions permitted | 8/8 | — |
| False-block rate | 0% | — |

## B. Trace-evidence coverage (does the trace carry the auditor-checkable field?)
For each obligation, whether the trace carries the specific machine-checkable field(s) an
auditor needs to evaluate it — *auditable against*, not *satisfies*.

Trace-evidence present with VCL: **6/6 (100%)** · baseline (no governed trace): 0%

| Obligation | Required field present in trace |
|---|---|
| EU AI Act Art. 9 (risk management) | yes |
| EU AI Act Art. 10 (data governance) | yes |
| EU AI Act Art. 12 (record-keeping) | yes |
| EU AI Act Art. 13 (transparency) | yes |
| EU AI Act Art. 14 (human oversight) | yes |
| NIST RMF MEASURE-2.7 (security/resilience) | yes |

## C. Tamper-evidence
- Tamper detection rate: **40/40 (100%)**
- False-positive rate on intact trails: 0% (0/40)

## D. Governance latency overhead
- End-to-end query latency (n=30, deterministic mode): mean 126.3 ms, median 122.4 ms, p95 147.2 ms
- In-pipeline governance (precheck + per-row policy filter, 18 decisions): **20.27 ms (22% of the traced path)**
- OPA decision latency (keep-alive): 2.653 ms/decision

Per-step latency (representative trace):

| Step | ms |
|---|---|
| semantic_layer:parse_intent | 8.78 |
| policy_engine:precheck_allow_supplier_query | 7.06 |
| agent:plan_queries | 22.23 |
| semantic_layer:governed_query | 10.93 |
| context_graph:query_supplier_contracts | 25.77 |
| policy_engine:per_row_filter | 10.54 |
| response:synthesise_response | 5.63 |
