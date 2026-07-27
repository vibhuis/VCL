# VCL: claims → evidence audit

What the paper *claims*, what the reference implementation and evaluation now *demonstrate*,
and — stated plainly — what remains argument or future work. Grading is deliberately harsh, the
way a skeptical reviewer would read it. Evidence files are under `eval/`.

Legend: ✅ demonstrated · 🟡 partial / measured-but-narrow · ⚠️ weak or near-tautological ·
◻️ argued only (not empirically shown).

## Load-bearing claim

> Governed, instrumented enterprise context makes agentic AI **verifiable at enterprise scale**.

| Facet | Evidence | Grade |
|---|---|---|
| A verifiable artifact exists (inspectable, tamper-evident trace; `/verify`, W3C-PROV `/prov`) | `evaluate.py` C: tamper **40/40 detected, 0 FP** | ✅ |
| Governance stays tractable "at scale" | `scale.py`: single-digit µs/row to 100k rows, **sub-second** governance at 100k | ✅ |
| "Verifiable" in the *formal* sense (grounding constraints machine-checked) | not implemented — the layer *exposes* the primitive; we don't run a formal verifier | ◻️ |

## The five components

| Component | Claim | Evidence | Grade |
|---|---|---|---|
| Semantic layer | Grounds answers in *defined* metrics | `grounding.py`: VCL **F1 1.0** vs fully-informed RAG **~0.85**, deterministic vs stochastic | ✅ |
| Context graph | Lineage as an audit artifact | Neo4j graph + cross-system identity resolution + PROV export in the trace | ✅ |
| Governance & policy engine | RBAC/ABAC, residency, PII, retention, audit at runtime | `evaluate.py` A: 15/15 blocked, 0 false-block; `adversarial.py`: **0% structural leak** | ✅ |
| Agent/tool runtime | MCP surface, observable for monitors | MCP gateway (`test_mcp_live`), per-step observable trace | 🟡 (observable; no external monitor consumes it) |
| Feedback loop | Traces, **drift signals**, continuous assurance | `drift.py`: **98% drift detection, 8% FP**, ~25-event latency (minimal detector) | 🟡 (was ◻️ before — now demonstrated, minimally) |

## The four properties

| Property | Evidence | Grade |
|---|---|---|
| **Verifiability** | tamper 40/40, 0 FP; governed trace inspectable | ✅ |
| **Governance-by-default** (workload inherits governance) | `adversarial.py`: guardrail leaks 28–60% on small models, VCL 0% because policy is in the layer | ✅ |
| **Model-agnosticism** | same code across deterministic, llama3.2:3b, llama3.1:8b, mistral:7b, gpt-4o — no architectural change | ✅ |
| **Additivity** (composes over vendor stacks without re-platforming) | argument only — no integration with a real vendor EIL stack built | ◻️ |

## Regulatory / deployment

| Claim | Evidence | Grade |
|---|---|---|
| Trace carries auditor-checkable field per obligation | `evaluate.py` B: 6/6 required fields present in trace (reframed: *auditable against*, not *satisfies*) | 🟡 |
| Cost/latency overhead is bounded | `evaluate.py` D: governance ≈20 ms (22% of traced path); `scale.py`: linear-ish, sub-second at 100k | ✅ |
| 4 deployment topologies (cloud/hybrid/on-prem/edge) | one local stack demonstrated; others architectural | ◻️ |

## The strategic finding: VCL matters most for small / open-weight models

The adversarial and grounding studies converge on one point that reframes the paper's
motivation. Prompt-based guardrails and prompted reasoning are **model-dependent and
uncertifiable**:

| Model | Adversarial contact-PII leak | Grounding residency-trap error |
|---|---|---|
| llama3.2:3b (open-weight) | 28% | — |
| llama3.1:8b (open-weight) | 44% | 40% (F1 0.85) |
| mistral:7b (open-weight) | 56% | 20% (F1 0.59) |
| gpt-4o (hosted frontier) | 0% | ~0% |
| **VCL (any model)** | **0%** | **0% (F1 1.0)** |

Enterprises are trending toward **small, fine-tuned, self-hosted open-weight models** for cost,
latency, and **data sovereignty** — and that is exactly the regime where model-interior
guardrails are weakest *and* where regulated data cannot leave the boundary to reach a stronger
hosted model. So the buyer who most needs governance is pushed onto the models that leak most.
The VCL's guarantee is **structural and model-independent** (the data/definitions are not in the
model's hands); the *urgency* is what the model trend makes acute. This is a "yes, and" — it
sharpens the motivation without narrowing the architectural claim.

## What still needs work (do not overclaim)

- **Additivity / multi-topology** — architectural argument; not empirically integrated. Scope
  as future work.
- **Formal verification** — the layer exposes the primitives; wiring an actual verifier
  (VeriGuard-style grounding constraints) is future work.
- **Drift** — a real capability now, but a minimal detector; production needs a mature
  change-point method over several metrics.
- **Scale of the graph store** — `scale.py` isolates the *governance* layer; end-to-end graph
  query latency at 100k+ is a property of the data platform, not measured here.
