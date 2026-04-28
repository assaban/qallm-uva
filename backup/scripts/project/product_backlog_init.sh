#!/usr/bin/env bash
# qallm-uva: Proper DevOps Backlog Initialization

echo "Establishing repository labels..."
gh label create "foundation" --color "ededed" --description "Base setup and CI/CD" --force
gh label create "ingestion"  --color "0052cc" --description "Unified Ingestion Layer" --force
gh label create "stage-1"    --color "006b75" --description "Quantitative Quality Engine (QQE)" --force
gh label create "stage-2"    --color "e99695" --description "LLM Refinement Engine (LRE)" --force

echo "Creating Product Backlog Issues..."

# --- Sprint 1: Foundation & Ingestion ---
gh issue create --title "DEV-01: CI/CD Pipeline Setup" \
    --body "Establish GitHub Actions with Ruff and Pytest to ensure NFR1 (Robustness)[cite: 156, 165]." \
    --label "foundation"

gh issue create --title "FEAT-01: Unified Ingestion Layer" \
    --body "Implement parsers to extract code units and attach metadata. Must strip Jupyter magics to form a coherent evidence package." \
    --label "ingestion"

# --- Sprint 2: Stage 1 (Metrics) ---
gh issue create --title "FEAT-02: Quantitative Quality Engine (QQE)" \
    --body "Integrate static analysis tools (Pylint, Radon, jscpd) to formalize artifacts into structured diagnostics[cite: 171, 190]." \
    --label "stage-1"

gh issue create --title "FEAT-03: Lifecycle-Aware Normalizer" \
    --body "Implement mapping logic for EOSC lifecycle stages: Initialization, Implementation, and Publication[cite: 143, 170]." \
    --label "stage-1"

# --- Sprint 3: Stage 2 (LLM Feedback) ---
gh issue create --title "FEAT-04: Prompt Construction Module" \
    --body "Transform structured diagnostics into compact evidence bundles for LLM inference[cite: 215, 217]." \
    --label "stage-2"

gh issue create --title "FEAT-05: Iterative Verify-Rescore Loop" \
    --body "Implement the 4-5 iteration loop where refined code is re-evaluated to verify improvements[cite: 173, 280]." \
    --label "stage-2"

echo "Backlog successfully initialized."