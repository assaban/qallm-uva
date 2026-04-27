#!/usr/bin/env bash
# qallm-uva: Thesis Research Backlog Extension

echo "Creating Thesis-Specific Research Issues..."

# --- RQ1: RL Effectiveness & Baselines ---
gh issue create --title "RESEARCH-01: Baseline Implementation (Hypothesis)" \
    --body "Implement Strategy (a): Property-based testing using Hypothesis as a non-trivial baseline[cite: 730]." \
    --label "stage-2"

gh issue create --title "FEAT-06: Oracle Implementation (Crash/Property/Metamorphic)" \
    --body "Implement the three oracle types to handle functional correctness without formal specs [cite: 761-770]." \
    --label "stage-2"

gh issue create --title "FEAT-07: RL Reward Function & Multi-round Loop" \
    --body "Implement the scalar reward logic (+1.0 bug, +0.5 coverage) and orchestrate 5-10 rounds[cite: 666, 734]." \
    --label "stage-2"

# --- RQ2: Verification Gap ---
gh issue create --title "RESEARCH-02: False Confidence Rate Analysis" \
    --body "Develop the metric to identify cells rated 'clean' by static analysis that fail verification[cite: 742, 789]." \
    --label "stage-1"

# --- RQ3: Workflow Integration ---
gh issue create --title "FEAT-08: Jupyter Frontend Trigger (ipywidgets)" \
    --body "Build the 'Run Check' button for in-notebook initiation as requested by Dr. Zhao[cite: 654, 667]." \
    --label "foundation"