# VCL evaluation

Reproducible studies behind the paper's evaluation section. Everything is deterministic given
the seeded synthetic data (`data/synthetic/generate.py`, `SEED=20599942`); the LLM studies use
**local open-weight models via Ollama** (no API key), so results reproduce on any machine.

```bash
./reproduce.sh                 # regenerate data + run all offline studies (default local model)
./reproduce.sh --live          # also run the stack-dependent studies (needs docker compose up -d)
```

Each study states its own scope and limitations honestly. The point of the suite is not a
single hero number — it is to show *which* claims the architecture actually earns, and how.

## The studies

| Study | File | Needs | What it measures | Headline |
|---|---|---|---|---|
| **Adversarial policy enforcement** | `adversarial.py` | Ollama | Contact-PII leak rate under adversarial prompting: prompt-guardrail vs VCL, across models | Small open-weight models leak **28–56%**; gpt-4o 0%; **VCL 0% on all** |
| **Grounding accuracy** | `grounding.py` | Ollama | Whether a *fully-informed* RAG-style prompt applies defined metrics/rules as consistently as the VCL layer | RAG **F1 0.59–0.85, residency-trap up to 40%**; VCL **F1 1.0, 0%** |
| **Governance overhead vs scale** | `scale.py` | — | Governance-path latency as context grows 100 → 100k rows | Single-digit µs/row; **sub-second at 100k rows** |
| **Feedback-loop drift detection** | `drift.py` | — | Whether the feedback loop *detects* distributional drift (continuous assurance) | **98% detection, 8% FP**, ~25-event latency |
| **Policy coverage / trace-evidence / tamper / latency** | `evaluate.py` | Docker stack | Systems properties against the live stack | tamper **40/40, 0 FP**; governance **≈20 ms (22%)** |

## How to read the evidence (honest framing)

- The **adversarial** and **grounding** studies are the load-bearing, non-tautological
  evidence: a real model, a real baseline that fails, variance reported. They show the VCL's
  value is greatest exactly where enterprises are heading — **small, self-hosted, open-weight
  models** — because that is where prompt-based guardrails are weakest and where regulated data
  cannot leave the boundary to reach a stronger hosted model. The architecture is
  model-independent; the *urgency* is model-dependent.
- The VCL's 0% leak / F1 1.0 are **structural, not empirical** — the restricted values are not
  in the model's context and the metric/policy definitions live in the layer, so the result
  does not depend on the sample.
- The **trace-evidence** study measures whether the trace *carries the auditor-checkable field*
  each obligation requires — **not** that a deployment *satisfies* the obligation.
- The **drift** detector is deliberately minimal (a two-window test) — enough to make
  "the feedback loop detects drift" a demonstrated capability, not a promise.

## Limitations (applies to the whole suite)

Synthetic data; a small number of local models; one restricted-data type (contact PII); a
handful of attack/grounding vectors. These studies demonstrate the *mechanisms and their
failure modes*, not a broad security or accuracy benchmark. See `claims-to-evidence.md` for the
per-claim audit of what is evidenced, what is argued, and what is scoped as future work.
