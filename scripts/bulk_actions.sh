#!/usr/bin/env bash
# bulk_actions.sh
#
# Bulk-action script for the QALLM backlog audit, 2026-05.
# Generated from docs/backlog-audit-2026-05.md.
#
# Three phases, run independently:
#   PHASE=close   ./bulk_actions.sh
#   PHASE=edit    ./bulk_actions.sh
#   PHASE=create  ./bulk_actions.sh
#
# All phases run in DRY-RUN by default. To actually execute, set EXECUTE=1:
#   EXECUTE=1 PHASE=close ./bulk_actions.sh
#
# Recommended order:
#   1. PHASE=close   in dry-run, eyeball output.
#   2. EXECUTE=1 PHASE=close to close issues.
#   3. PHASE=edit    in dry-run, eyeball.
#   4. EXECUTE=1 PHASE=edit
#   5. PHASE=create  in dry-run, eyeball.
#   6. EXECUTE=1 PHASE=create
#
# The create phase tracks itself in /tmp/qallm-audit-created.txt so a
# re-run will skip already-created issues. Delete that file to start over.
#
# Requirements:
#   * gh CLI installed and authenticated (`gh auth status` should be OK).
#   * Run from any directory; the script targets assaban/qallm-uva explicitly.
#   * Labels used: engineering, research, writing, RQ1, RQ2, RQ3, P1, P2,
#     blocked, documentation. All should exist on the repo. The default
#     GitHub `documentation` label is sometimes pre-created; if NEW-10
#     creation fails with "label not found", run once:
#         gh label create documentation --repo assaban/qallm-uva \
#             --color "0075ca" --description "Documentation work"

set -euo pipefail

REPO="assaban/qallm-uva"
PHASE="${PHASE:-help}"
EXECUTE="${EXECUTE:-0}"
CREATE_LOG="/tmp/qallm-audit-created.txt"

# ---------- helpers ----------

# Run a gh command. In dry-run, print only. In execute, run and print.
run() {
    if [[ "$EXECUTE" == "1" ]]; then
        echo "    EXEC: $*"
        "$@"
    else
        echo "    DRY:  $*"
    fi
}

# Print a phase header.
header() {
    echo ""
    echo "================================================================"
    echo "  $1"
    echo "================================================================"
    if [[ "$EXECUTE" != "1" ]]; then
        echo "  DRY-RUN. Set EXECUTE=1 to apply."
    else
        echo "  EXECUTING. No going back beyond what gh permits."
    fi
    echo ""
}

# ---------- PHASE: close ----------

phase_close() {
    header "PHASE: close (6 issues)"

    # #7  RESEARCH-01: Baseline Implementation (Hypothesis)
    echo "[1/6] #7  Hypothesis baseline (done, superseded by #19)"
    run gh issue close 7 --repo "$REPO" --comment \
"Implemented in PR #31. Code lives at \`src/qallm/verification/hypothesis_baseline.py\`. Also superseded in the newer backlog by #19. Closing."

    # #10 RESEARCH-02: False Confidence Rate Analysis (old version)
    echo "[2/6] #10 FCR analysis (duplicate of #24)"
    run gh issue close 10 --repo "$REPO" --comment \
"Superseded by #24, which has the full methodology and acceptance criteria. Closing as duplicate."

    # #11 FEAT-08: Jupyter Frontend Trigger (old version)
    echo "[3/6] #11 Jupyter trigger (duplicate of #27)"
    run gh issue close 11 --repo "$REPO" --comment \
"Superseded by #27, which has the same scope with full acceptance criteria. Closing as duplicate."

    # #19 FEAT-07: Hypothesis Baseline Generator
    echo "[4/6] #19 Hypothesis baseline generator (done)"
    run gh issue close 19 --repo "$REPO" --comment \
"Implemented and merged in PR #31. \`--strategy hypothesis\` is available in the CLI and orchestrator. Pilot results across 31 functions confirm the baseline runs and produces comparable JSON output. Closing."

    # #20 FEAT-08: Strategy Router
    echo "[5/6] #20 Strategy router (done)"
    run gh issue close 20 --repo "$REPO" --comment \
"All acceptance criteria met. CLI accepts \`--strategy hypothesis|oneshot|rl\`; orchestrator routes correctly (\`src/qallm/orchestrator.py\` line 44); summary JSON includes the \`strategy\` field (line 143). Closing."

    # #21 RESEARCH-01: Pilot Three-Strategy Comparison
    echo "[6/6] #21 Pilot three-strategy comparison (done with expanded scope)"
    run gh issue close 21 --repo "$REPO" --comment \
"Completed with expanded scope: 31 functions across 5 files (not just \`model.py\`), three models (gpt-4o-mini, gpt-5-mini, gemma3:4b), statistically significant results (all pairwise Wilcoxon p < 0.005). 91.3% false confidence rate. This is the pilot cited in the midterm presentation. Closing."

    echo ""
    echo "Close phase complete."
}

# ---------- PHASE: edit ----------

phase_edit() {
    header "PHASE: edit (4 issues)"

    # #22 DATA-01: status comment only, no body edit
    echo "[1/4] #22 DATA-01: add comment noting Nafis request sent"
    run gh issue comment 22 --repo "$REPO" --body \
"Audit note (2026-05): dataset request has been made to Nafis. Keeping the \`blocked\` label until the dataset arrives. No body edit; status unchanged."

    # #24 RESEARCH-03: add comment about pilot-scale FCR
    echo "[2/4] #24 FCR: add comment about pilot result"
    run gh issue comment 24 --repo "$REPO" --body \
"Audit note (2026-05): pilot-scale FCR already computed at 91.3% over 31 functions, 5 files, 3 models (basis of midterm presentation finding). Full 200-notebook FCR awaits DATA-01."

    # #25 RESEARCH-04: flag for supervisor discussion
    echo "[3/4] #25 Expert validation: flag for Nafis discussion"
    run gh issue comment 25 --repo "$REPO" --body \
"Audit note (2026-05): the expert validation study is meaningful work (ethics, instrument, ~15 participants, thematic analysis). For a single-author MSc thesis under time pressure, this may need to be either confirmed as in-scope (with a clear timeline) or softened to future work (in which case RQ3's actionability claim also needs softening). Flag for Nafis discussion at the next 1:1."

    # #26 FEAT-09: edit body to narrow scope; downgrade to P2
    echo "[4/4] #26 Quality metrics: narrow scope to CWE work, downgrade to P2"
    # Read the new body from a heredoc, write to a temp file, then use gh
    NEW_BODY_26=$(cat <<'EOF'
## Audit note (2026-05)
Three of the four originally listed metrics are already produced by the pipeline:

- Functional Correctness Score: produced as `test_pass_rate` in the Reliability indicator (`qallm.evaluation`).
- Verification Coverage: produced as coverage delta in the verification session (`qallm.verification`).
- False Confidence Rate: computed at pilot scale (see #24).

The fourth metric, Security Assessment Score with CWE coverage, has not been built. The issue is narrowed to just that work and downgraded from P1 to P2, since CWE coverage is not on the critical path for the thesis claim.

## What (remaining)
Add a Security Assessment Score that measures CWE coverage from the crash-oracle tests generated by the verification loop.

## Acceptance criteria
- [ ] Mapping from generated test failure modes to CWE categories.
- [ ] Score expressed as `covered_CWEs / total_relevant_CWEs` for the function under study.
- [ ] Output integrated into `summary.json` per session.
- [ ] Documented in thesis Chapter 5.
EOF
)
    # Note: gh issue edit requires the body via --body-file or --body
    # Use a temp file for safety with multi-line content.
    TMP_BODY=$(mktemp)
    echo "$NEW_BODY_26" > "$TMP_BODY"

    run gh issue edit 26 --repo "$REPO" --body-file "$TMP_BODY"
    run gh issue edit 26 --repo "$REPO" --remove-label "P1" --add-label "P2"

    # Comment trail
    run gh issue comment 26 --repo "$REPO" --body \
"Audit note (2026-05): scope narrowed to just the Security Assessment Score with CWE coverage (the other three metrics in the original body are already produced by the pipeline). Priority downgraded from P1 to P2 because CWE coverage is not on the critical path."

    # Clean up temp file in execute mode
    if [[ "$EXECUTE" == "1" ]]; then
        rm -f "$TMP_BODY"
    else
        echo "    DRY: temp body file at $TMP_BODY (not removed in dry-run; inspect with 'cat \$TMP_BODY')"
    fi

    echo ""
    echo "Edit phase complete."
}

# ---------- PHASE: create ----------

create_issue() {
    # Usage: create_issue <id> <title> <labels> <body_file>
    local id="$1"
    local title="$2"
    local labels="$3"
    local body_file="$4"

    if [[ -f "$CREATE_LOG" ]] && grep -q "^$id\b" "$CREATE_LOG"; then
        echo "[skip] $id already created in a previous run"
        return 0
    fi

    echo "[create] $id: $title"
    if [[ "$EXECUTE" == "1" ]]; then
        local url
        url=$(gh issue create --repo "$REPO" \
            --title "$title" \
            --body-file "$body_file" \
            --label "$labels")
        echo "    -> $url"
        echo "$id $url" >> "$CREATE_LOG"
    else
        echo "    DRY:  gh issue create --repo $REPO --title \"$title\" --body-file $body_file --label \"$labels\""
        echo "    body preview (first 5 lines):"
        head -5 "$body_file" | sed 's/^/      /'
    fi
}

write_body() {
    # Writes the body for an issue to a temp file and prints the path.
    local content="$1"
    local path
    path=$(mktemp --suffix=.md)
    printf '%s' "$content" > "$path"
    echo "$path"
}

phase_create() {
    header "PHASE: create (10 new issues)"

    if [[ -f "$CREATE_LOG" && "$EXECUTE" == "1" ]]; then
        echo "Note: previous create log exists at $CREATE_LOG."
        echo "Issues listed there will be skipped. Delete the file to recreate them."
        echo ""
    fi

    # NEW-01
    BODY=$(write_body '## What
Implement persistence of generated test suites per code unit, supporting both configurable strategies from workflow design v3 section 4.5:

- `frozen` (default): tests are bound to the code unit and accumulate across rounds; never removed or replaced.
- `per_round` (alternative): each round has its own independent suite.

## Why
Without this, cross-round comparisons of variants are invalid because the RL loop can generate easier tests for worse variants. See `docs/workflow-design.md` section 4.5 for the full discussion.

## Acceptance criteria
- [ ] New module `qallm.verification.test_persistence` with a `TestSuiteStore` keyed by `(session_id, code_unit_id)`.
- [ ] `test_stability` parameter in orchestrator config (frozen | per_round), default `frozen`.
- [ ] Frozen strategy: each round appends tests, applies full union to next variant.
- [ ] Per-round strategy: each round stores its suite independently.
- [ ] Unit tests cover both strategies.
- [ ] `summary.json` reflects which strategy was used.

## Estimated effort
80-100 lines plus tests.

## References
`docs/workflow-design.md`, section 4.5.
')
    create_issue "NEW-01" "FEAT: Test suite persistence per code unit, with configurable strategy" "engineering,RQ1,P1" "$BODY"

    # NEW-02
    BODY=$(write_body '## What
Implement the judge component that decides whether a repaired variant is an improvement over its parent in the lineage.

## Strategies
- `lexicographic`: ordered dimensions (default: Security > Reliability > Maintainability > Reproducibility > FAIRness); regressions in higher-priority dimensions block acceptance.
- `strict`: any regression in any indicator means abandonment.
- `model`: judge LLM decides freely, with explanation. Default for v1.

## Judge inputs
Both profile output and raw verification numbers (test pass/fail, bug list, coverage delta). See workflow design v3 section 5.4.

## Acceptance criteria
- [ ] New module `qallm.judge` with `JudgeStrategy` enum and dispatcher.
- [ ] Three concrete strategies implemented.
- [ ] Judge model is independently configurable from the repair model.
- [ ] Verdict storage: every judgement records both model output and the raw numerical comparison (for thesis-chapter validation, see section 5.2).
- [ ] Unit tests for each strategy.

## Estimated effort
~150 lines plus tests.

## References
`docs/workflow-design.md`, sections 5 and 9.1 to 9.3.
')
    create_issue "NEW-02" "FEAT: Judge module with lexicographic, strict, and model strategies" "engineering,RQ2,P1" "$BODY"

    # NEW-03
    BODY=$(write_body '## What
The reliability indicators in `qallm.evaluation` currently return None (deferred stubs from the original PR). Connect them to actual verification session output so `evaluate_profile` produces real numbers for Reliability.

## Acceptance criteria
- [ ] `qallm.verification.pass_rate` evaluator reads from the latest verification session for the given code unit.
- [ ] `qallm.verification.bugs` evaluator reads the bug list.
- [ ] Test coverage for the wiring.

## Estimated effort
~40 lines plus tests.

## References
`src/qallm/evaluation.py` (existing deferred stubs).
`docs/workflow-design.md`, section 11.
')
    create_issue "NEW-03" "FEAT: Wire reliability indicators in evaluation to verification output" "engineering,RQ2,P1" "$BODY"

    # NEW-04
    BODY=$(write_body '## What
Implement the FAIRness dimension indicators per workflow doc section 9.4.

## Indicators (initial set)
- Presence of a licence file in the project root.
- Presence of a citation file (CITATION.cff, CITATION.bib).
- Presence of a README with required sections (description, install, usage).
- Documented function signatures (docstring coverage above threshold).

## Acceptance criteria
- [ ] New module `qallm.fairness` with four evaluator functions.
- [ ] Evaluators registered in `qallm.evaluation`.
- [ ] FAIRness dimension added to `IMPLEMENTATION_DEFAULT` profile.
- [ ] Unit tests with fixture projects (with and without each artefact).

## Estimated effort
~100 lines plus tests.

## References
`docs/workflow-design.md`, section 9.4.
')
    create_issue "NEW-04" "FEAT: FAIRness indicators (licence, citation, README, docstrings)" "engineering,RQ2,P1" "$BODY"

    # NEW-05
    BODY=$(write_body '## What
Implement hard budget caps in the orchestrator loop control, enforced at round boundaries. Caps must take precedence over env-var configuration up to defined ceilings.

## Caps
- Max rounds (default 5, ceiling 10).
- Max total tokens (default 500k, ceiling 2M).
- Max wall-clock seconds (default 1800, ceiling 3600).
- Max per-round seconds (default 600).
- Max estimated cost in USD (default 5.00, ceiling 25.00).

## Acceptance criteria
- [ ] New module `qallm.cost` with per-model price table and a session cost estimator.
- [ ] Price table maintained in `qallm.config`, documented as needing manual updates.
- [ ] Orchestrator calls cost check at every round boundary.
- [ ] Cap trip halts the loop and writes the cap reason to `summary.json`.
- [ ] Unit tests for each cap.

## Estimated effort
~50 + 80 lines.

## References
`docs/workflow-design.md`, sections 6 and 9.6.
')
    create_issue "NEW-05" "FEAT: Hard budget caps (rounds, tokens, time, dollars) with cost estimation" "engineering,RQ1,P1" "$BODY"

    # NEW-06
    BODY=$(write_body '## What
Bring the orchestrator main loop in line with the v3 workflow specification. Round 0 baseline, then iterate accept-or-abandon per round, halt on budget or convergence, log accepted variants to lineage and abandoned ones separately.

## Acceptance criteria
- [ ] Round 0 produces baseline with no repair.
- [ ] Each subsequent round runs repair, analyse, verify, judge in that order.
- [ ] Accepted variants extend lineage; rejected variants go to abandoned log.
- [ ] Loop halts on any of: budget cap, model verdict says stop, convergence.
- [ ] Manual and auto modes produce identical artefacts (section 8).
- [ ] Integration test covering the full loop with a stubbed judge.

## Estimated effort
~100 lines.

## References
`docs/workflow-design.md`, sections 3 and 8.
')
    create_issue "NEW-06" "FEAT: Orchestrator loop implements the v3 analyse-repair-verify-judge cycle" "engineering,RQ1,P1" "$BODY"

    # NEW-07
    BODY=$(write_body '## What
The reporter must emit the artefacts defined in workflow doc section 10.

## Acceptance criteria
- [ ] `lineage/round_<n>/` directory per accepted round with: source, tests, static.json, verification.json, profile.json, judge.json.
- [ ] `abandoned/round_<n>/` directory per abandoned variant, same shape.
- [ ] `summary.json` as the canonical record; sufficient to reconstruct the session.
- [ ] `report.md` and `report.html` generated from `summary.json` as human views.
- [ ] Schema documented in a short `docs/output-schema.md`.

## Estimated effort
~100 lines plus a schema doc.

## References
`docs/workflow-design.md`, section 10.
')
    create_issue "NEW-07" "FEAT: Extend reporter with lineage, abandoned log, summary.json canonical" "engineering,RQ2,P1" "$BODY"

    # NEW-08
    BODY=$(write_body '## What
Auto mode in the web UI currently halts after one round. Update it to drive the v3 loop end-to-end, matching manual mode behaviour.

## Acceptance criteria
- [ ] Auto mode runs analyse, repair, verify, judge cycles to completion or budget exhaustion.
- [ ] Manual and auto produce identical session artefacts on the same input.
- [ ] Progress events stream to the UI per round.
- [ ] No regression on existing manual-mode flow.

## Estimated effort
Small change, depends on NEW-06.

## References
`docs/workflow-design.md`, section 8.
')
    create_issue "NEW-08" "FIX: Auto mode drives the v3 loop (currently stops after one round)" "engineering,RQ3,P1" "$BODY"

    # NEW-09
    BODY=$(write_body '## What
A secondary validation experiment using OpenAI HumanEval as ground truth. Inject bugs into reference solutions, run QALLM against the mutants, measure detection and repair rates.

## Why
This experiment gives the thesis a ground-truth-backed methodology validation in addition to the EVERSE-aligned Li-dataset experiment. Requested by Zhao through Nafis at the weekly meeting.

## Acceptance criteria
- [ ] Mutation catalogue documented (categories of bugs to inject).
- [ ] Driver script that loads HumanEval, applies mutations, runs QALLM.
- [ ] Metrics: detection rate, repair rate, false-positive rate per mutation category.
- [ ] Results report in a separate notebook or markdown file.

## Estimated effort
A few days of focused setup; independent of the main pipeline.

## References
`docs/workflow-design.md`, section 9.5.
https://huggingface.co/datasets/openai/openai_humaneval
')
    create_issue "NEW-09" "RESEARCH: HumanEval-with-injected-bugs validation experiment" "research,RQ1,RQ2,P1" "$BODY"

    # NEW-10
    BODY=$(write_body '## What
The current `useAutoRunner` hook drives the front-end auto mode. The author has flagged not fully understanding the end-to-end behaviour. Once the new loop lands (NEW-06, NEW-08), document the front-end orchestration in a short note under `docs/`.

## Acceptance criteria
- [ ] Markdown doc explains: trigger, polling pattern, error handling, screen transitions.
- [ ] Diagram (Mermaid) of the front-end state machine.

## Estimated effort
~30 minutes once NEW-08 is done.
')
    create_issue "NEW-10" "DOC: Document the auto-mode useAutoRunner workflow" "documentation,RQ3,P2" "$BODY"

    echo ""
    echo "Create phase complete."
    if [[ "$EXECUTE" == "1" && -f "$CREATE_LOG" ]]; then
        echo "Created issues log: $CREATE_LOG"
        echo "Re-running this phase will skip already-created issues."
    fi
}

# ---------- entry ----------

case "$PHASE" in
    close)
        phase_close
        ;;
    edit)
        phase_edit
        ;;
    create)
        phase_create
        ;;
    all)
        phase_close
        phase_edit
        phase_create
        ;;
    help|*)
        cat <<EOF
Usage:
    PHASE=close   ./bulk_actions.sh           # 6 issues closed with comments
    PHASE=edit    ./bulk_actions.sh           # 4 issues edited (body or comment)
    PHASE=create  ./bulk_actions.sh           # 10 new issues created
    PHASE=all     ./bulk_actions.sh           # all three phases in order

Add EXECUTE=1 to actually run; otherwise the script prints what it would do.

Recommended workflow:
    1. PHASE=close   ./bulk_actions.sh                   # dry-run, eyeball
    2. EXECUTE=1 PHASE=close ./bulk_actions.sh           # do it
    3. Repeat with edit, then create.

Notes:
    * Repo is hardcoded to assaban/qallm-uva.
    * Create phase tracks itself in $CREATE_LOG for safe re-runs.
    * Close and edit are naturally idempotent.
    * All issues are created from the v3 workflow design (\`docs/workflow-design.md\`).
EOF
        ;;
esac
