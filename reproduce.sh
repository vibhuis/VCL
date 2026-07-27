#!/usr/bin/env bash
# Reproduce the VCL evaluation from a clean checkout.
#
# Two tiers:
#   OFFLINE  (default) — regenerates the seeded synthetic data and runs every study that needs
#                        no running services: governance-vs-scale, drift detection, grounding
#                        accuracy, and the adversarial policy-enforcement leak study. The LLM
#                        studies use a local Ollama model (no API key); set VCL_LLM_MODEL.
#   LIVE     (--live)  — additionally runs the systems studies that require the Docker stack
#                        (policy coverage, trace-evidence coverage, tamper-evidence, latency).
#
# Usage:
#   ./reproduce.sh                                  # offline studies, default local model
#   VCL_LLM_MODEL=ollama/llama3.1:8b ./reproduce.sh # pick the model for the LLM studies
#   ./reproduce.sh --live                           # also run the stack-dependent studies
set -euo pipefail
cd "$(dirname "$0")"

export VCL_LLM_MODEL="${VCL_LLM_MODEL:-ollama/llama3.1:8b}"
echo "== VCL evaluation reproduction =="
echo "LLM for grounding/adversarial studies: $VCL_LLM_MODEL"
echo

echo "== 1. Regenerate seeded synthetic data (SEED=20599942, deterministic) =="
uv run python data/synthetic/generate.py
echo

echo "== 2. Offline studies (no services required) =="
echo "-- governance overhead vs scale --";      uv run python eval/scale.py
echo "-- feedback-loop drift detection --";      uv run python eval/drift.py
echo "-- grounding accuracy: RAG vs VCL --";     uv run python eval/grounding.py
echo "-- adversarial policy enforcement --";     uv run python eval/adversarial.py
echo

if [[ "${1:-}" == "--live" ]]; then
  echo "== 3. Live studies (require: docker compose up -d) =="
  uv run python eval/evaluate.py
else
  echo "(skipping stack-dependent studies A–D; pass --live after 'docker compose up -d' to include them)"
fi
echo
echo "Done. Results written under eval/*.md and eval/*.json."
