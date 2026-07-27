# Grounding accuracy: encoded layer (VCL) vs prompted reasoning (RAG-style)

**Question:** does encoding metric definitions and governance rules in a *layer* produce more
reliable answers than a fully-informed model reasoning over raw records?

**Method.** Task: *which suppliers have penalty **exposure** > $1M and at-risk delivery, hosted
in the EU?* — where `exposure = penalty_amount × penalty_probability` (a defined metric),
at-risk = `delivery_risk_score ≥ 0.5`, and residency must be `EU`. The candidate pool contains
traps: high face-amount / low-probability contracts whose *exposure* is under $1M, a US-hosted
supplier, and not-at-risk suppliers. Ground truth is computed independently from the fixtures.

- **RAG-style baseline** — the model gets the raw fields and is **told every definition and rule
  in the prompt** (maximally fair), then must apply them across the pool.
- **VCL** — exposure and at-risk come pre-computed from the semantic layer; residency from the
  policy engine. The qualifying set is decided by the layer, not re-derived by the model.

5 reps per model. We score the set each condition presents as qualifying (F1) and flag whether
it wrongly includes the US-hosted supplier (the residency trap).

## Result

| Model | Class | RAG-style F1 | RAG residency-trap | VCL F1 | VCL trap |
|---|---|---|---|---|---|
| llama3.1:8b | open-weight (small) | **0.85** | **40%** | **1.00** | 0% |
| mistral:7b | open-weight (small) | **0.59** | 20% | **1.00** | 0% |

## Reading the result

- Even **fully told the rules**, small open-weight models applied them inconsistently: they
  mis-derived exposure (using the face amount instead of amount × probability) and, in
  llama-8b's case, included the US-hosted supplier **40% of the time despite an explicit
  residency instruction**. Accuracy is also **model-dependent** (F1 0.59 vs 0.85 across two
  models) and **stochastic** (varies run to run).
- The **VCL is correct by construction (F1 1.0, 0% trap), deterministically**, because the
  definitions and policies live in the layer and are computed once — not re-derived by the
  model on every call. This is the semantic-layer / context-graph claim, *measured* rather than
  cited.

This reinforces the study's strategic finding (see `adversarial_results.md`): the models
enterprises increasingly self-host — small, open-weight — are exactly the ones whose prompted
reasoning is least reliable, which is where encoding grounding and policy in a layer pays off
most.

## Limitations

Synthetic data, two small local models, a single grounding task with a handful of traps. It
demonstrates the *mechanism* — encoded definitions apply consistently, prompted reasoning does
not — not a broad accuracy benchmark. VCL's F1 1.0 reflects the layer's decision (the grounded
set); final-prose fidelity by the synthesis model is a separate, model-interior concern.

Reproduce: `VCL_LLM_MODEL=ollama/llama3.1:8b python eval/grounding.py`
