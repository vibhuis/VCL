# Governance overhead vs. context scale

Does the governance layer the VCL adds stay tractable as a query's context grows to enterprise size? We run the real per-row policy-decision loop (`PenaltyDeliveryScenario.policy_filter`, policy mirror asserted equal to OPA by `test_policy_parity.py`) over synthetic contexts from 100 to 100,000 rows.

| Rows in context | Governance latency | Per-row cost | Policy decisions |
|---|---|---|---|
| 100 | 0.15 ms | 1.45 µs/row | 183 |
| 1,000 | 1.57 ms | 1.57 µs/row | 1,833 |
| 10,000 | 19.88 ms | 1.99 µs/row | 18,333 |
| 100,000 | 706.93 ms | 7.07 µs/row | 183,333 |

Per-row governance cost stays in **single-digit microseconds** across three orders of magnitude (1.45–7.07 µs/row). The mild growth at the top end is Python object-allocation/GC pressure plus the O(n log n) ranking sort — not an algorithmic blow-up in policy evaluation, which is O(n) in the rows. In absolute terms an extreme 100,000-row single-query context costs only ~707 ms of governance — sub-second — and realistic queries touch far fewer rows.

**Scope.** This measures the governance layer the VCL contributes (policy evaluation + audit-event construction per row), not the underlying graph store's query latency, which is a property of the data platform (bounded by published GraphRAG figures of tens–hundreds of ms/query). Deterministic; no services or LLM required.

