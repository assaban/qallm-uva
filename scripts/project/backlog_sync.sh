#!/usr/bin/env bash
# qallm-uva: Updated Thesis Backlog (April 28, 2026)
# Run from the repo root: bash backlog_sync.sh
# Requires: gh cli authenticated (gh auth login)

set -e

echo "=== Setting up labels ==="
gh label create "done"         --color "0e8a16" --description "Completed and merged"         --force
gh label create "engineering"  --color "0052cc" --description "Implementation work"           --force
gh label create "research"     --color "d93f0b" --description "Experiment and analysis work"  --force
gh label create "writing"      --color "e99695" --description "Thesis and paper writing"      --force
gh label create "blocked"      --color "b60205" --description "Waiting on external input"     --force
gh label create "RQ1"          --color "006b75" --description "RL effectiveness comparison"   --force
gh label create "RQ2"          --color "1d76db" --description "Verification gap analysis"     --force
gh label create "RQ3"          --color "5319e7" --description "Workflow integration"           --force
gh label create "P0"           --color "b60205" --description "Critical path"                 --force
gh label create "P1"           --color "d93f0b" --description "Important"                     --force
gh label create "P2"           --color "fbca04" --description "Nice to have"                  --force

echo ""
echo "=== Closing completed issues ==="

# These are done and merged in FEAT-06
for title in \
    "FEAT-01: Unified Ingestion Layer" \
    "FEAT-02: Quantitative Quality Engine" \
    "FEAT-03: Lifecycle-Aware Normalizer" \
    "FEAT-04: Prompt Construction Module" \
    "FEAT-05: Iterative Verification Loop" \
    "FEAT-06: Merged Architecture with RL Loop" \
    "FEAT-06: Oracle Implementation (Crash/Property/Metamorphic)" \
    "FEAT-07: RL Reward Function and Multi-round Loop"
do
    echo "  [DONE] $title"
done

echo ""
echo "=== Creating active backlog ==="

# ────────────────────────────────────────────────────
# WEEK 5: Hypothesis baseline + pilot experiments
# ────────────────────────────────────────────────────

gh issue create \
    --title "FEAT-07: Hypothesis Baseline Generator" \
    --body "## What
Implement Strategy (a) from thesis Section 4.2: property-based testing
using Hypothesis as the non-LLM control group for RQ1.

## Acceptance Criteria
- [ ] \`hypothesis_baseline.py\` generates @given tests from type annotations
- [ ] Fallback strategy for functions without type hints
- [ ] Two test types per function: crash oracle (no unhandled exceptions) and deterministic oracle (same input = same output)
- [ ] Runs through the same \`executor.run_tests()\` as the LLM strategies
- [ ] \`--strategy hypothesis\` flag in CLI
- [ ] Unit tests for type mapping and test generation
- [ ] Pilot run on \`model.py\` produces comparable output to LLM runs

## References
- Proposal Section 4.2, Strategy (a)
- Hypothesis docs: https://hypothesis.readthedocs.io/" \
    --label "engineering,RQ1,P0"

gh issue create \
    --title "FEAT-08: Strategy Router in Orchestrator" \
    --body "## What
Add \`--strategy\` flag to CLI and route to the correct generator:
- \`hypothesis\`: no LLM, Hypothesis baseline
- \`oneshot\`: LLM with rounds=1, no feedback
- \`rl\`: LLM with N rounds and feedback (existing default)

## Acceptance Criteria
- [ ] CLI accepts \`--strategy hypothesis|oneshot|rl\`
- [ ] Orchestrator routes correctly for all three
- [ ] Summary JSON includes \`strategy\` field
- [ ] One-shot is just rl with rounds=1 (no new code needed)" \
    --label "engineering,RQ1,P0"

gh issue create \
    --title "RESEARCH-01: Pilot Three-Strategy Comparison" \
    --body "## What
Run all three strategies on \`model.py\` (8 functions) to validate
the experimental methodology before scaling to Li's dataset.

## Commands
\`\`\`bash
qallm model.py --strategy hypothesis
qallm model.py --strategy oneshot --llm openai --model gpt-4o-mini
qallm model.py --strategy rl --llm openai --model gpt-4o-mini --rounds 5
\`\`\`

## Acceptance Criteria
- [ ] All three produce comparable JSON output
- [ ] Bug-finding rate, coverage, and test validity are comparable across strategies
- [ ] Results saved in outputs/experiments/pilot/

## Metrics (Table 4 in proposal)
- Bug-finding rate per strategy
- Branch coverage per strategy
- Test validity rate per strategy" \
    --label "research,RQ1,P0"

# ────────────────────────────────────────────────────
# WEEK 6: Dataset acquisition + scale experiments
# ────────────────────────────────────────────────────

gh issue create \
    --title "DATA-01: Acquire Li's Validated Notebook Dataset" \
    --body "## What
Get the 2,796 notebooks from 277 projects used in Li (2025).
Check QCDIS/Software_Quality_Control_LLM repo on GitHub.
If not public, ask Nafis directly.

## Acceptance Criteria
- [ ] Dataset downloaded and stored in data/li_dataset/
- [ ] Curated subset of 200 notebooks selected (5 domains, 3 complexity tiers)
- [ ] Selection criteria documented in data/README.md
- [ ] .gitignore excludes the raw notebooks (too large for git)

## Blocked By
Access to the dataset (check with Nafis)" \
    --label "research,RQ1,RQ2,P0,blocked"

gh issue create \
    --title "RESEARCH-02: Full RQ1 Experiment (200 Notebooks)" \
    --body "## What
Run the three-strategy comparison across 200 notebooks from Li's dataset
using three LLM providers: gpt-4o-mini, gpt-5-mini, gemma3:4b.

## Experiment Matrix
3 strategies x 3 models x 200 notebooks = 1,800 runs
(Hypothesis baseline: 1 x 200 = 200 runs, no model variation)

## Acceptance Criteria
- [ ] All runs completed and JSONs saved
- [ ] Results aggregated into a single CSV for statistical analysis
- [ ] Wilcoxon signed-rank tests computed (paired, non-parametric)
- [ ] Cliff's delta effect sizes reported
- [ ] Token usage and cost tracked per strategy per model

## Budget Estimate
~200 notebooks x 8 functions avg x 5 rounds x 3 models = ~24,000 API calls
At ~500 tokens per call (gpt-4o-mini): ~12M tokens ~ EUR 3-5

## Depends On
DATA-01, FEAT-07, FEAT-08" \
    --label "research,RQ1,P0"

# ────────────────────────────────────────────────────
# WEEK 7-8: RQ2 Analysis
# ────────────────────────────────────────────────────

gh issue create \
    --title "RESEARCH-03: False Confidence Rate Analysis (RQ2)" \
    --body "## What
Compute the false confidence rate: proportion of cells rated 'clean' by
static analysis that have >= 1 test failure under execution-based verification.

## Method
For each notebook cell in the 200-notebook dataset:
1. Run static analysis (Bandit + Radon) via existing pipeline
2. Identify cells with zero static warnings ('clean')
3. Run RL verification on those cells
4. Count how many have >= 1 failing test

false_confidence_rate = cells_with_failures / cells_rated_clean

## Acceptance Criteria
- [ ] Script to compute FCR from existing session JSONs
- [ ] Breakdown by severity (HIGH/MEDIUM/LOW static findings)
- [ ] Statistical comparison: static-only vs static+RL (Wilcoxon)
- [ ] Results formatted for thesis Table (RQ2)

## Depends On
RESEARCH-02" \
    --label "research,RQ2,P1"

# ────────────────────────────────────────────────────
# WEEK 9-12: Expert validation + RQ3
# ────────────────────────────────────────────────────

gh issue create \
    --title "RESEARCH-04: Expert Validation Study (RQ2 + RQ3)" \
    --body "## What
Conduct mixed-methods validation with 10-15 experts per proposal Section 4.2.

## Instrument
1. Five example notebook analyses (static-only vs static+RL)
2. Likert-scale: usefulness, trust, actionability
3. Comparative judgement: which condition gives more confidence
4. Integration questions: trigger point, detail level, adoption barriers
5. Open-ended: how would you use this in practice

## Acceptance Criteria
- [ ] Ethics approval or exemption documented
- [ ] Survey instrument finalized
- [ ] 10-15 responses collected
- [ ] Thematic analysis completed for RQ3
- [ ] Design recommendations written

## Participants
UvA researchers, MNS group, KdG colleagues, industry contacts

## Depends On
RESEARCH-02 (need results to show)" \
    --label "research,RQ2,RQ3,P1"

# ────────────────────────────────────────────────────
# WEEK 13-14: Quality metrics + Jupyter trigger
# ────────────────────────────────────────────────────

gh issue create \
    --title "FEAT-09: Verification-Based Quality Metrics" \
    --body "## What
Define and implement 3-5 new quality metrics for Volentir et al.
framework compatibility:
- Functional Correctness Score (test pass rate)
- Verification Coverage (branch coverage from generated tests)
- False Confidence Rate (cells clean by static but failing by execution)
- Security Assessment Score (CWE coverage from crash oracle tests)

## Acceptance Criteria
- [ ] Metrics computed from session JSONs
- [ ] Output compatible with Volentir et al. framework format
- [ ] Documented in thesis Chapter 5" \
    --label "engineering,RQ2,P1"

gh issue create \
    --title "FEAT-10: Jupyter Frontend Trigger" \
    --body "## What
Build a lightweight ipywidgets button that runs QALLM from within
a notebook. Requested by Dr. Zhao.

## Acceptance Criteria
- [ ] Single cell: \`from qallm import check; check()\`
- [ ] Displays progress bar during analysis
- [ ] Shows summary in notebook output cell
- [ ] Links to full JSON report

## Priority
P2: useful for demo and defence, not required for thesis results." \
    --label "engineering,RQ3,P2"

# ────────────────────────────────────────────────────
# WEEK 15-18: Writing + Defence
# ────────────────────────────────────────────────────

gh issue create \
    --title "THESIS-01: Write Methodology Chapter" \
    --body "## Sections
- TAR approach and three validation cycles
- Three-strategy comparison design
- Evaluation metrics (Table 4)
- Data sources and selection criteria
- Statistical methods (Wilcoxon, Cliff's delta)

## Depends On
RESEARCH-01 (pilot validates methodology)" \
    --label "writing,P1"

gh issue create \
    --title "THESIS-02: Write Results Chapter" \
    --body "## Sections
- RQ1: Three-strategy comparison tables and analysis
- RQ2: False confidence rate and verification gap quantification
- RQ3: Expert validation findings and design recommendations
- Threats to validity discussion

## Depends On
RESEARCH-02, RESEARCH-03, RESEARCH-04" \
    --label "writing,P1"

gh issue create \
    --title "THESIS-03: Defence Preparation" \
    --body "## Deliverables
- [ ] Slide deck (15-20 slides)
- [ ] Live demo of QALLM on a notebook
- [ ] Dashboard visualization of results
- [ ] Prepared answers for expected questions

## Timeline
Week 17-18" \
    --label "writing,P2"

echo ""
echo "=== Backlog created ==="
echo ""
echo "Summary:"
echo "  P0 (Critical path):  FEAT-07, FEAT-08, RESEARCH-01, DATA-01, RESEARCH-02"
echo "  P1 (Important):      RESEARCH-03, RESEARCH-04, FEAT-09, THESIS-01, THESIS-02"
echo "  P2 (Nice to have):   FEAT-10, THESIS-03"
echo ""
echo "Next: Go to github.com/assaban/qallm-uva/projects"
echo "  1. Create project: 'QALLM Thesis Sprint Board' (Board template)"
echo "  2. Columns: Backlog | In Progress | In Review | Done"
echo "  3. Add all issues to the project board"
