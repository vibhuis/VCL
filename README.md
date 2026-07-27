# VCL Reference Implementation

A working, local, end-to-end demonstration of the **Verifiable Context Layer (VCL)**
pattern — the five-component architecture from the companion paper
*The Verifiable Context Layer* (on [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6900918)).

It answers a real enterprise question with an LLM agent while **enforcing written policy
at runtime**, **tracing every decision**, and producing a **regulator-addressable audit
trail** that maps to EU AI Act Articles 9/12/13 and the NIST AI RMF.

> **The worked use case** (from Section 5 of the paper):
> *"Which Q3 supplier contracts have penalty-clause exposure greater than one million
> dollars, and which of those suppliers have at-risk delivery performance based on the
> last six months of operational telemetry?"*
>
> The agent resolves the penalty-exposure metric and the delivery-risk score across three
> systems of record (contract management / ERP / MES), **excludes** a supplier whose data
> is hosted outside the EU, **redacts** specific commercial terms, **masks** supplier
> contact PII, and shows you exactly why — step by step, in a tamper-evident audit trail.
>
> *(A second governance scenario — EMEA / PII / GDPR consent, from the build spec §6 —
> remains in the codebase and test suite to exercise the residency/consent/secrets
> policies, but the demo leads with the paper's Section 5 query.)*

---

## The five components (paper Figure 3)

| # | Component | Tool | Port | Role |
|---|-----------|------|------|------|
| 1 | Semantic layer | Cube.dev (+ DuckDB) | 4000 | business question → governed query |
| 2 | Context graph | Neo4j Community | 7474 / 7687 | entity relationships + provenance |
| 3 | Policy engine | Open Policy Agent | 8181 | enforce 5 written policies per access |
| 4 | Agent runtime | LangGraph + FastAPI + LLM | 8000 | orchestrate, reason, emit traces |
| 5 | Feedback loop | OpenTelemetry-shaped → SQLite (hash-chained) | 8200 | persist, replay & **verify** every decision |
| 5b | MCP gateway | Model Context Protocol | 9000 | exposes the VCL tools over MCP (paper §4.2) |
| — | Demo UI | Streamlit | 8501 | query · response · trace viewer · PDF export |

---

## Quick start (clone → demo in under 10 minutes)

**Prerequisites:** Docker Desktop (or any Docker engine with Compose v2).

```bash
# 1. Configure (optional — works without a key, see note below)
cp .env.example .env
#   pick a model with VCL_LLM_MODEL and paste the matching provider key

# 2. Bring up the whole stack
docker compose up --build        # first run pulls images; allow a few minutes

# 3. Open the demo
open http://localhost:8501
```

Then in the browser:

1. The query box is **pre-filled** with the worked-use-case query — click **Run**.
2. Read the policy-filtered answer (note the `[redacted: policy …]` markers).
3. Click **Show audit trace** to walk every step: semantic parse → policy precheck →
   graph query → per-row policy filter → synthesis → final audit event.
4. Click **Export compliance report (PDF)** to download the regulator-addressable report.

> **Bring your own LLM.** The agent uses [LiteLLM](https://docs.litellm.ai), so you pick
> the model with `VCL_LLM_MODEL` and supply the matching provider key —
> OpenAI (`gpt-4o`, default), Anthropic, Google (`gemini/…`), Groq, a local
> `ollama/…` model, etc. The LLM both *understands* the question and *writes* the answer.
> **No key at all?** The demo still runs end-to-end via a deterministic fallback; the
> governance path (semantic → graph → policy → trace) is identical either way. See
> [DECISIONS.md](DECISIONS.md) D5/D9.

---

## Verifying it works

```bash
# Unit + acceptance tests (run natively; no stack required — clients are injectable)
uv sync --extra dev
uv run pytest -q

# Policy tests against the real OPA binary
docker compose up -d policy-engine
uv run pytest services/policy-engine/tests -q
```

The acceptance test `services/agent-runtime/tests/test_worked_use_case.py` verifies all
ten steps of the worked use case from spec §6.

---

## Evaluation

**Headline finding — why enforcement belongs *outside* the model.** We put a real LLM agent
under adversarial prompting (data-echo, contact-sheet, CSV-export, debug-dump, jailbreak) and
asked it to leak supplier contact PII, two ways: (a) *prompt-based guardrail* — raw data in
context plus a system prompt saying "never reveal PII"; (b) *VCL* — restricted values redacted
before the model sees them. Four models — three open-weight (two families) via Ollama, one
hosted frontier — 5 vectors × 5 runs each. Full method + limitations in
[eval/adversarial_results.md](eval/adversarial_results.md):

| Model | Class | Prompt-guardrail leak | VCL leak |
|---|---|---|---|
| llama3.2:3b | open-weight | **28% ± 30%** | **0%** |
| llama3.1:8b | open-weight | **44% ± 32%** | **0%** |
| mistral:7b | open-weight | **56% ± 23%** | **0%** |
| gpt-4o | hosted frontier | **0% ± 0%** | **0%** |

Prompt guardrails are **model-dependent and uncertifiable**: across two open-weight families,
small self-hosted models leaked 28–56% of adversarial attempts; gpt-4o held on these vectors —
but that guarantee is behavioral, unauditable, and (for this EU-residency scenario) only
available by sending regulated PII to a US-hosted model. The VCL leaks **0% on every model,
structurally**, because the data is never in the model's context.

> **Why this matters for the enterprise trend.** Teams are moving to small, self-hosted,
> open-weight models for cost, latency, and data sovereignty — exactly the regime where
> model-interior guardrails are weakest *and* where regulated data can't leave the boundary to
> reach a stronger hosted model. The VCL's guarantee is model-independent; the urgency is what
> the model trend makes acute.

**Grounding accuracy** ([`eval/grounding.py`](eval/grounding.py)) — even *told every rule in the
prompt*, small models apply defined metrics/policies inconsistently (RAG-style F1 **0.59–0.85**,
wrongly including an out-of-EU supplier up to **40%** of the time); the VCL decides the set in
the layer (**F1 1.0, 0%**), deterministically. Full results in
[eval/grounding_results.md](eval/grounding_results.md).

**Systems properties** — deterministic harnesses on the seeded data
([eval/results.md](eval/results.md), [eval/scale_results.md](eval/scale_results.md),
[eval/drift_results.md](eval/drift_results.md)):

| Study | Result |
|---|---|
| **Tamper-evidence** | 40/40 tampered audit trails detected (100%), 0% false positives |
| **Governance latency** | ~126 ms/query; in-pipeline governance ≈20 ms (22%); OPA ≈2.7 ms/decision |
| **Governance vs scale** | single-digit µs/row from 100 → 100k rows; **sub-second governance at 100k** |
| **Feedback-loop drift detection** | 98% detection, 8% false-positive, ~25-event latency (minimal detector) |
| **Policy-enforcement coverage** | 15/15 prohibited actions blocked, 0% false-block (deterministic check) |
| **Trace-evidence coverage** | 6/6 obligations have their auditor-checkable field present in the trace |

```bash
./reproduce.sh            # regenerate data + run all offline studies (local model, no key)
./reproduce.sh --live     # also run the stack-dependent studies (needs docker compose up -d)
```

Latency figures are machine-dependent; the tamper-evidence, scale, drift, and coverage results
are deterministic and reproduce exactly. See [eval/claims-to-evidence.md](eval/claims-to-evidence.md)
for the per-claim audit of what is demonstrated vs. argued vs. future work.

---

## Repository layout

```
vcl-ref-impl/
├── docker-compose.yml        single-command stack bring-up
├── DECISIONS.md              architecture decisions & deviations from the spec
├── data/synthetic/           synthetic supplier-contract data + generator
├── services/
│   ├── agent-runtime/        FastAPI + LangGraph (the agent)
│   ├── semantic-layer/       Cube.dev model
│   ├── context-graph/        Neo4j + seed loader
│   ├── policy-engine/        OPA + vcl.rego (5 policies)
│   ├── feedback-loop/        audit collector (SQLite)
│   └── ui/                   Streamlit demo
└── docs/                     architecture · demo-script · EU AI Act mapping
```

## Status & scope

This is a **reference implementation** — a runnable proof of the VCL pattern and a starting
point you fork, **not** a turnkey product. It has no auth, no multi-tenancy, and uses
synthetic data by default (spec §9). The engine (pipeline, tamper-evident audit, MCP,
policy, feedback) is domain-agnostic; the business logic lives behind a small
[`Scenario`](services/agent-runtime/app/scenarios/) extension point. To point it at your own
data, follow [docs/adapting-to-your-domain.md](docs/adapting-to-your-domain.md). What's done
and what's next is in [docs/roadmap.md](docs/roadmap.md).

## Documentation

- [docs/architecture.md](docs/architecture.md) — component map and the governed request flow
- [docs/demo-script.md](docs/demo-script.md) — exact 10-minute walkthrough (commands + clicks)
- [docs/eu-ai-act-mapping.md](docs/eu-ai-act-mapping.md) — which trace field satisfies which obligation
- [docs/adapting-to-your-domain.md](docs/adapting-to-your-domain.md) — fork it onto your own data
- [docs/roadmap.md](docs/roadmap.md) — what's done and what's next
- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, code map, conventions
- [DECISIONS.md](DECISIONS.md) — architecture decisions and deviations from the spec

## Build phases

This repo was built in the eight phases of `00-VCL-Prototype-Build-Spec.md` §7.
Each phase is a self-contained, runnable commit. See the git history and
[DECISIONS.md](DECISIONS.md).

## License

Apache-2.0. This is a reference implementation, not a production system (see spec §1.2).
