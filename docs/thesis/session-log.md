# QALLM session log

Newest first. Append-only.

---

## 2026-06-17 (reporter dir separation: experiments stop bloating the web-UI dir)

The orchestrator hardcoded outputs/quality_reporter as its reporter base, so
experiment runs (one session subdir + lineage per file) bloated the web-UI
session directory and filled the VM disk. Added a reporter_dir param to the
orchestrator (defaults to settings.QALLM_SESSIONS_DIR). The web UI does not
override it; the gap runner now writes reporter artefacts under its own
--output/reports (self-contained per run), and the HumanEval runner uses
QALLM_EXPERIMENT_REPORTER_DIR (default outputs/experiment_reporter). New config
setting + doc update in sessions-vs-experiments.md. +3 tests. Suite 724.

Also gave Mohssin the fast-delete recipe for the already-bloated dir (mv to
.trash then background rm; or rsync --delete an empty dir over it).


## 2026-06-17 (HumanEvalFix: parallel runner + clearer purpose)

- run_humaneval.py / humaneval_runner.py now take --workers N: combinations run
  in a ThreadPoolExecutor, results written as each completes under a lock,
  resumption unaffected. Each combo is independent (own orchestrator, temp dir,
  LLM calls) so it is safe. Measured ~5.4x on 6 stub problems with 4 workers.
  Web-UI launcher accepts workers too. +3 tests.
- docs/experiments/humaneval.md: added a "Why this experiment exists" section
  making the role explicit, it is the GROUND-TRUTH calibration that backs the
  real-notebook headline (which has no labels). It checks that generated tests
  discriminate buggy from canonical, and that repairs pass the benchmark's
  hidden tests (an oracle QALLM never sees, so no circularity). Also clarified
  we use bigcode/humanevalpack (HumanEvalFix), not openai/openai_humaneval,
  because the latter has no bugs and so cannot measure detection. Documented
  --workers.


## 2026-06-17 (audit P1/P2: errored-units, ingestion fix, consensus retired, sandbox renamed)

Executed the three greenlit items in headline-protecting order.

1. Errored-units surfaced + ingestion bug fixed: aggregate.json now has an
   "inputs" block (total/measured/errored/errored_fraction/error_types); fixed
   NotebookAdapter.parse assuming dict cells and list source (the 'str' object
   has no attribute 'get' bug behind 186 of 203 E1 errors). +4 tests.
2. Consensus apparatus retired: deleted consensus_vote.py, _merge_samples, the
   samples>1 branch, both consensus tests; superseded the two consensus docs;
   aligned the lab MANIFEST. Suite 734 -> 718.
3. sandbox.py renamed to extraction.py (it never sandboxed); docstrings
   downgraded to the truth; execution-safety threats paragraph added to scaffold
   5.5.

Three commits; suite 718; ruff clean. Still on Mohssin: rotate the SonarQube
token; send the new E1 aggregate; run E2 (--confirm) for the real gap rate.

---

## 2026-06-15 (thesis: drafted the results-independent sections)

### Delivered for review (`docs/thesis-results-independent-draft`)
Drafted as thesis-ready prose (no headline numbers needed), replacing the
bracketed outlines:
- Ch1 Introduction: the three-contribution framing (verification-gap method,
  EVERSE judge, mutation confidence) and the RL-as-iterative-prompting scope
  clarification.
- Ch2 Background: 2.1 static-analysis blind spot, 2.2 quality models
  (ISO 25010/EVERSE/FAIR4RS/Volentir), 2.3 LLMs for code/test gen, 2.4
  execution/search-based testing, 2.5 the under-addressed point. Citation
  placeholders kept.
- Ch4 Implementation: 4.1 architecture, 4.2 model interface, 4.3 analysers,
  4.4 sandbox + FROZEN+GROW, 4.5 reproducibility/evidence pipeline + provenance,
  4.6 availability.
- 5.1 Setup: calibration-first protocol + the lab calibration result; dataset/
  model specifics left bracketed for E1.
- 5.5 Threats: full prose incl. the real threats (incoherent-oracle filter,
  single-sample/consensus, security-inconclusive asymmetry, mutation "unknown"
  on trivial functions).
- Appendix: added mutation-score and confidence-label definitions.
Status tracker updated; writing convention respected (no dash punctuation).

### Remaining (need E1 results)
5.2/5.3/5.4 (RQ1/RQ2/RQ3 numbers), 5.6 scale, Ch6 Discussion, Ch7 Conclusion,
Abstract (written last).

## 2026-06-15 (docs/UI reality audit)

### Delivered for review (`docs/reality-audit-and-enrichment`)
- Roadmap items 0 and 1 corrected: they still said "confirm consensus running"
  and --samples 5; reality is consensus abandoned, samples=1 is the calibrated
  setting (5/5 recall), and item 1 (ENVRI) is in progress with the right flags.
- README index: added verification-repair-reward-design.md and (re)added the
  security-confirmation-scope decision aid (restored; its PR was not merged).
- About screen: added the mutation-confidence story (a "How do we know the bugs
  are real?" card + a "Score confidence" pipeline step), so the UI reflects the
  third contribution that is now live in the gap panel.
- New: docs/thesis/enrichment-ideas.md, candidate features and experiments to
  enrich QALLM, each with value/effort/risk, separated into thesis-scope vs
  future-work.

## 2026-06-15 (web UI: oracle-confidence view)

### Delivered for review
- **Gap-confidence in the UI (`feature/ui-gap-confidence`)**: new endpoint
  GET /api/session/{id}/gap-confidence mutation-scores the session's gap
  functions and returns per-function confidence + distribution. GapPanel gains a
  "How trustworthy are these findings?" card: a Score-confidence button, a
  high/medium/low/unknown summary, and per-function cards (confidence, score,
  killed/viable). Pure execution, no LLM. Frontend builds; backend 723 tests.

### For the demo
This is the most compelling number we have, the gap finding count is now
qualified by how sensitive the oracle that found each one is. Shows live in the
tool.

## 2026-06-15 (RQ2 diagnosis: findings confirm but land inconclusive, now legible)

### Diagnosis from lab_calibration_06151708 (the run with diagnostics)
The confirm path is NOT broken in plumbing: it found baseline units and findings
(security: 4 SECURITY findings; complexity: 1 COMPLEXITY finding), and 3 of the 4
security findings map to functions (line 10 is module-level import, correctly
unmapped). So confirm_findings ran on 3 testable SECURITY findings. The reason
RQ2 read 0 confirmed / 0 refuted: every targeted security test came back
INCONCLUSIVE (the exploit test errors or cannot demonstrate the unsafe effect in
the sandbox), and inconclusive was never surfaced. The aggregate only exposed
confirmed/refuted, so "all inconclusive" looked identical to "nothing to
confirm". That was a legibility bug, not a confirmation bug.

### Delivered for review (`fix/surface-confirm-inconclusive`)
- SessionMetrics + aggregate now carry inconclusive and not_execution_testable
  (in summary.json, metrics.csv, aggregate.json). RQ2 is now legible: confirmed
  / refuted / inconclusive / not-testable are all visible.
- confirm_verify logs the verdict breakdown per session.

### Real RQ2 finding (for the thesis, not a bug)
Security findings on the lab set are reachable-but-not-trivially-demonstrable by
a generated exploit under the sandbox, so they land inconclusive. This is itself
a result: execution can strongly adjudicate RELIABILITY (wrong-value) findings,
but SECURITY confirmation via generated exploit is weaker and often inconclusive.
Worth stating in RQ2 and threats-to-validity. The reliability path (the headline)
is unaffected.

## 2026-06-15 (lab full-run analysis: two fixes + confirm diagnostics)

### Analysis of lab_full_rq1553
RQ1 healthy: reliability 5/5, security 0, clean/complexity 1 FP each (matches
calibration), gap rate 1.0. Two problems found:
- gap_confidence mostly "unknown" (6/7): the scorer recorded 0 mutants for
  functions whose test file lived in a unit not defining them, and a few real
  functions had too few mutable sites (no % operator).
- RQ2/RQ3 still 0: confirm ran (baseline found, so round_00 fix works) but
  mapped 0 findings to functions; needs the artefacts to pin, so added
  diagnostics.

### Delivered for review (`fix/gap-confidence-and-confirm-diagnostics`)
- gap_confidence: only score a function against the unit whose source actually
  defines it (was recording false "unknown" for functions living elsewhere);
  score each function once; report unresolved gap functions separately so the
  distribution is not polluted by lookup misses.
- mutation engine: added %, //, ** to arithmetic operators so parity/integer
  code (e.g. first_even's n % 2) yields viable mutants instead of "unknown".
- confirm_verify: diagnostic logging (baseline unit count, findings count,
  and an explicit line when findings exist but none map to a function) to
  pinpoint the RQ2/RQ3 0/0 on the next run.

## 2026-06-10 (analyzer-adapter pinning tests: Tier 2 item 5)

### Delivered for review
- **Finding-shape pinning tests (`test/analyzer-finding-shape`)**: the findings
  the whole gap metric depends on are now pinned against known raw tool output.
  radon_normalizer 59 -> 100% (CC > 5 threshold, MI < 70 threshold, both
  severity bands, combined, empty/malformed json), trufflehog mapper 65 -> 93%
  (JSONL secret -> issue shape, multi-line, blank-line skip, missing-metadata
  default), bandit _safe_parse fully covered (ANSI strip + recover JSON from
  noisy output), util.get_snippet 33 -> 89% (target-line marker, start clamp,
  bad-input None). Analysis-package coverage 80 -> 87%. A tool output drift now
  fails a test instead of silently changing the gap metric.

### Roadmap
Tier 2 item 5 substantially done. Next: generator/repair coverage (item 7),
then broad-except triage (item 6).

## 2026-06-10 (provenance manifest: Tier 1 complete)

### Delivered for review
- **Provenance manifest (`feature/provenance-manifest`)**: Tier-1 item 4, the
  last one. experiments/provenance.py captures commit/branch/dirty, package
  version, Python/platform, and a dataset fingerprint (count + sha256 over
  sorted paths). gap_runner folds it into manifest.json under "provenance".
  Best-effort: never blocks a run (a missing field is None/unknown). The
  dirty-tree flag is recorded honestly as a reproducibility caveat.

### Milestone
Tier 1 is now complete: calibrated instrument (5/5), CIs, mutation confidence,
test-quality metric, RQ2/RQ3 unblocked, provenance. Remaining Tier-1 item (the
ENVRI headline run) is execution, not code. Focus shifts to Tier 2 (load-bearing
untested code: analyzer adapters, generator/repair coverage) for finalization.

### Next validation
Lab full run: --confirm --mutation-confidence to validate RQ2/RQ3 populate and
gap findings score high-confidence on ground truth.

---

## 2026-06-10 (RQ2/RQ3 unblocked + run-level gap confidence)

### Delivered for review (3rd commit on the mutation branch)
- **confirm/verify round_00 fix**: _baseline_units read lineage/round_0 but the
  reporter writes round_00 (round_{n:02d}), so confirm/verify found no baseline
  and returned 0 confirmed / 0 refuted. Resolved tolerantly (round_00, then
  round_0). The masking test fixture (which used round_0/round_1) now uses real
  zero-padded naming; back-compat and empty-baseline tests added. Recorded as
  MD-003. RQ2/RQ3 should be re-run.
- **Run-level gap confidence in the aggregate**: --mutation-confidence now folds
  per-session confidence distributions into aggregate.json
  (gap_confidence.distribution + high_confidence_gap_bugs), so the headline can
  be reported filtered to high-confidence findings.

### Tests
+3 (confirm round_00 + legacy + empty baseline) and +1 (aggregate folds
confidence). Suite 689; ruff clean on touched files.

## 2026-06-10 (oracle confidence wired into the gap pipeline)

### Delivered for review (on the mutation branch, builds on the engine)
- **Gap-confidence wiring (`feature/oracle-confidence-mutation`, 2nd commit)**:
  --mutation-confidence flag. After the gap is measured, the runner reads each
  execution-only function's round-0 source and generated suite from disk,
  mutation-scores the oracle (gap_confidence.score_gap_confidence_from_dir), and
  attaches a per-function confidence + aggregate distribution to the result row.
  Forces full retention (reads artefacts), scores only gap functions. Tolerates
  round_00 / round_0 naming. Verified end-to-end: strong oracle -> high, weak
  oracle -> low through the artefact path.

### Note discovered while wiring
confirm_verify.py reads lineage/round_0, but the reporter writes round_00
(round_{n:02d}). This mismatch likely explains the 0 confirmed / 0 refuted we
saw, confirm/verify may be finding no baseline dir. Worth fixing in the RQ2/RQ3
investigation (gap_confidence already tolerates both names).

### Thesis framing
Report the gap rate twice: all findings, and high-confidence only. If close,
that is direct evidence the gap is real, not test noise.

## 2026-06-10 (game-changer: oracle confidence by mutation testing)

### What
A positive soundness check for the verification gap. Until now every guard was
negative (remove bad tests); none gave evidence that a surviving test is a
sensitive detector. New: mutation-test the ORACLE. For a flagged function,
inject semantics-changing mutants (AOR/ROR/COI/CRP/RVR) and run the generated
suite against each; mutation score (killed/viable) becomes a CONFIDENCE for the
gap finding (high/medium/low/unknown).

### Why it is a game-changer
It is the rigorous answer to the examiner's first question, "how do you know
your execution-found bugs are real?". It also automatically distinguishes the
exact failure mode that cost us many calibration runs: on inclusive_range_count,
an exact-value oracle scores 1.0 (HIGH) while an isinstance-only oracle scores
0.25 (LOW), no human inspection needed. Every gap finding can now carry a
confidence, and the headline rate can be reported filtered to high-confidence.

### Delivered for review
- **Mutation-based oracle confidence (`feature/oracle-confidence-mutation`)**:
  mutation.py (AST mutation engine, bounded, target-only, 5 operators) and
  mutation_score.py (run suite vs mutants -> MutationScore with score +
  confidence + viability handling). Concept doc with diagram and the
  strong-vs-weak table. Reuses run_tests; no new infra.
- Wiring the confidence into the gap report and the aggregate distribution is
  the documented next PR.

### Tests
+16: operator coverage, target-only mutation, bounding, syntax/unknown-fn
safety, strong-oracle->high, weak-oracle->low, empty/no-mutant->unknown,
confidence thresholds.

## 2026-06-10 (input discovery hardened against backups)

### Delivered for review
- **Backup/cruft exclusion (`fix/discovery-exclude-backups`)**: input discovery
  now skips not just .ipynb_checkpoints dirs but also loose *-checkpoint.ipynb,
  macOS ._ sidecars, and editor backups (~, .bak, .orig, .tmp, .swp). Prevents
  double-counting and junk inputs on a real dataset, so the ENVRI run uses only
  canonical files. Done to support the live experiment.

## 2026-06-10 (test-quality metric surfaced)

### Delivered for review
- **Generated-test-quality metric (`feature/test-quality-metric`)**: Tier-1
  roadmap item 3. Incoherent-oracle drops (and total drops) are now surfaced as
  numbers, not just logs: incoherent_oracles_dropped and tests_dropped_total in
  summary.json, and incoherent_oracles_dropped as a column in metrics.csv. This
  backs the threats-to-validity argument (MD-002) with a measured figure.
  GeneratedTest gains incoherent_oracle_tests (kept separate from
  discarded_tests); the VM accumulates both counts; the consensus merge
  propagates them. Also fixed a latent gap: incoherent drops were previously
  logged but not recorded on the returned GeneratedTest at all.

### Roadmap status
Tier 1: item 0 (lab calibration) confirmed sound; item 2 (bootstrap CI) already
wired; item 3 (this) done. Remaining Tier 1: item 1 (ENVRI headline, user runs)
and item 4 (provenance manifest: commit hash, model, seed).

## 2026-06-10 (parallel session-id collision, fixed)

### Bug (data corruption)
With --workers 4, all workers started in the same second and the orchestrator's
fallback run_id was a bare %Y%m%d_%H%M%S, so all four got the SAME id, shared one
report directory, and cross-contaminated metrics. lab_cal_voted_4 showed all
four sessions with identical exec_only=7, gap=0.7 (impossible for four different
files), the corruption signature. The tmp run happened to show truer per-file
numbers (clean_control 1, complexity 1, reliability 5, security 0), matching the
known single-sample result, but it still shared one id.

### Fix
The orchestrator fallback run_id now appends a uuid8 suffix (matching the
reporter's own scheme), so runs are unique even at identical timestamps.

### Delivered for review
- **Run-id uniqueness (`fix/parallel-session-id-collision`)**: uuid suffix on
  the fallback run_id; tests that four orchestrators in the same frozen second
  get unique ids and that an explicit run_id is still respected.

### Note on the two runs
tmp is the trustworthy one: reliability 5/5, security 0, two false positives on
clean_control(safe_mean) and complexity(cryptic), consistent with the
single-sample correctness oracle. lab_cal_voted_4 is collision-corrupted and
should be discarded.

### Still open (Observation 5)
Sessions still land in outputs/quality_reporter, not under the run output dir.
Placing them under runs/<name>/sessions/ would improve traceability; separate PR.

## 2026-06-10 (parallel workers were silent, fixed)

### Bug
Running with --workers 4 produced no logs during processing: run.log had only
the start lines, then nothing until completion. Cause: ProcessPoolExecutor
workers are fresh interpreters (spawn) and do NOT inherit the main process's
logging config, so all per-file work logged to nowhere. The user could not
observe a parallel run.

### Delivered for review
- **Worker logging (`fix/parallel-worker-logging`)**: a pool initializer
  configures logging in each worker to the SAME run.log (and stderr) with a
  [pid NNNN] prefix so interleaved lines are attributable; idempotent. log_level
  added to the config and threaded so workers honour --log-level. Now a parallel
  run is observable live (tail -f run.log).

### Note to user
Re the earlier "what to do next": option 1 (run ENVRI now at samples=1,
--workers 4) was THE recommendation; options 2 (fixed-input voting) and 3
(logging normalisation pass) were optional offers, not required steps.

## 2026-06-10 (parallel runner + consensus-voting finding)

### Finding: voting rarely triggers (samples test different inputs)
With consensus genuinely running (--samples 5), lab gave clean_control 2 (worse
than single-sample), complexity 1, reliability 5. run.log: ZERO votes cast all
run. Call-keyed voting only prunes when samples disagree on the SAME call, but
samples pick DIFFERENT inputs, so there is nothing to vote on; union then
accumulates every stray wrong assertion, hurting clean code. Honest position:
reliability recall 5/5 does NOT depend on consensus; consensus-by-union does not
improve precision and should stay at samples=1 until fixed-input voting (propose
inputs once, vote on outputs per input) is implemented. Documented as the real
fix in oracle-variance-and-consensus.md (its own future PR).

### Delivered for review
- **Parallel runner (`feature/parallel-gap-runner`)**: --workers N (default 1 =
  sequential, unchanged). >1 processes files concurrently via
  ProcessPoolExecutor; each file is an independent orchestrator/session so it is
  safe; resumable (completed files skipped); aggregate is order-independent.
  Threaded CLI -> config -> manifest. Tests cover all-files-processed, manifest,
  sequential default, and parallel resume.
- Logging conventions added to the documentation style guide (INFO = milestones,
  DEBUG = per-iteration detail; per-round test-exec is DEBUG, round verdict is
  INFO; uniform verb-first messages; no secrets). Supports the logging
  normalization started in executor.py and verification_manager.py.
- running-experiments.md documents --workers.

### Next
- Re-run ENVRI can now use --workers 4 for a near-linear speedup.
- Fixed-input voting is the real consensus fix (own PR); until then samples=1.
- ENVRI RQ1 headline remains the priority (--oracle correctness, samples=1,
  tmux, metrics_only, --workers 4, report gap rate with 95% CI).

## 2026-06-10 (consensus was silently disabled, fixed)

### Finding
The voted run (--samples 5) STILL showed clean_control 1 and complexity 1. The
artifacts had no per-sample namespacing: consensus never ran. Root cause: the
manager attaches an EMPTY session before the first generate(), and the consensus
guard tested `existing_session is not None`, so round 0 was misclassified as a
feedback round and fell back to a single sample. So consensus + voting were
disabled in every run so far; run 2's clean_control 0 was a single-sample lucky
draw, not the merge.

### Delivered for review
- **Fix consensus guard (`fix/consensus-empty-session-guard`)**: the guard now
  tests whether the session has prior ROUNDS (a real feedback round), matching
  the prompt selector. With this, --samples 5 actually generates five samples at
  round 0 and votes. Regression test added for the empty-session-at-round-0
  case. Calibration doc and roadmap updated.

### Re-run (now genuinely exercising consensus) + ENVRI
Re-run lab --oracle correctness --samples 5: this is the FIRST run where
consensus + voting actually execute; expect clean_control 0, complexity 0,
reliability 5. Then ENVRI for the RQ1 headline.

### Pending (updated)
- Confirm lab calibration with consensus running (the gate, do first).
- ENVRI RQ1 headline (--oracle correctness --samples 5, tmux, metrics_only, CI).
- Surface incoherent_oracles_dropped count in summary.json (test-quality metric).
- Add CI/bootstrap to the gap rate (examiners expect an interval).
- RQ2/RQ3 confirm path produced 0 confirmed/0 refuted on the lab set; investigate.
- Verify execution sandbox imports heavy ML deps for ENVRI, or use a light subset.
- Observation 4 (progress label: file N/M + fn N/M) and Observation 5 (session
  dirs under the run output) still pending, lower priority than ENVRI.

## 2026-06-10 (calibration milestone + assertion voting)

### Result: the correctness oracle works (5/5)
Two lab runs after the oracle-threading fix:
- Run 1 (correctness, samples=1): reliability_gap 5/5, clean_control 1,
  complexity_findings 1 (cryptic false positive), security 0 exec.
- Run 2 (correctness, samples=5 consensus): reliability_gap 5/5,
  clean_control 0, complexity_findings 1 (cryptic), security 0 exec.
The earlier 1 to 2 of 5 was entirely the threading bug; the correctness oracle
catches all five seeded reliability bugs once it actually runs at round 0.
Recorded in docs/experiments/lab-calibration-result.md.

### The cryptic false positive and the fix
complexity_findings `cryptic` (returns 3x; docstring "doubles then offsets" is
deliberately vague and states behaviour is correct) drew a wrong-guess
assertion from the oracle. Union consensus kept it (union maximises recall but
not precision). Implemented assertion-level majority voting
(qallm.verification.consensus_vote): the minority wrong expected value is
outvoted and dropped before the union, removing the false positive while keeping
5/5 recall.

### Delivered for review
- **Assertion voting (`feature/consensus-assertion-voting`)**: consensus_vote
  module (majority_expected, drop_outvoted_assertions) wired into the generator
  merge; calibration-result doc; variance doc updated to "implemented".

### Re-run + ENVRI
Re-run lab --oracle correctness --samples 5: expect clean_control 0,
complexity_findings 0, reliability_gap 5 (full target). Then ENVRI for the RQ1
headline with --oracle correctness --samples 5.

## 2026-06-10 (oracle threading bug + consensus generation)

### Major finding
While building consensus, found a latent bug: VerificationManager recorded
self.oracle on the session but never PASSED oracle to generator.generate(), so
round-0 generation used the default "crash" oracle regardless of --oracle. The
session summaries show a mix of "correctness" and "crash" in a single
--oracle correctness run. So the correctness oracle was not actually exercised
at the gap-measurement pass; the erratic 2/5 recall and the prompt-tuning
whack-a-mole were largely this bug. Fixed: the VM now passes oracle and samples
to generate.

### Delivered for review
- **Consensus test generation + oracle fix (`feature/consensus-test-generation`)**:
  (1) the oracle-threading fix above; (2) a --samples K knob (default 1, no
  change) that generates the correctness suite K times and merges the valid
  samples (union, test names namespaced per sample) to cut single-shot
  variance. Threaded CLI -> config -> factory -> orchestrator -> VM -> generator.
- Design doc docs/experiments/oracle-variance-and-consensus.md: the three-run
  variance evidence (different samples catch different bugs; union 3/5), the
  oracle-threading correction, and the consensus design with diagrams.

### Regression gate (re-run needed, now meaningful)
First: --oracle correctness --samples 1 to see the correctness oracle ACTUALLY
working at round 0 (the bug is fixed). Then --samples 5 to measure the
consensus lift. Gate: reliability_gap -> ~5, clean_control -> 0.

## 2026-06-10 (correctness oracle, withhold body)

### Diagnosis (from artifacts 20260610_010643)
First correctness-oracle run: reliability_gap 1 -> 2 of 5, clean_control held at
0. Three bugs still missed. The artifacts show the model still derived expected
values from the buggy body despite the warning: the inclusive_range_count test
literally asserted `result == end - start  # expected buggy behavior`.
safe_divide asserted a raise (mirroring the crash) when the spec says return 0;
accumulate's mutable-default bug needs multiple calls but every test called once.

### Delivered for review
- **Withhold body in correctness oracle (`feature/correctness-oracle-signature-only`)**:
  the correctness prompt now shows only the SIGNATURE + docstring, never the
  body, so the model must compute expected values from the spec. Adds explicit
  guidance for cross-call/stateful defects (accumulate class) and for
  return-not-raise edge behaviour (safe_divide class).
- New illustrated doc `concepts/oracles-and-defect-classes.md` (which oracle
  catches which defect class; why the body is withheld), linked in the index.
- Removed the "Dashes avoided per convention" lines from docs (convention now
  applied silently).

### Regression gate (re-run needed)
Re-run lab calibration `--oracle correctness`: expect reliability_gap -> ~5,
clean_control -> 0, complexity_findings -> 0. That is the recall gate before the
ENVRI headline.

## 2026-06-09 (later, correctness oracle)

### Diagnosis (from the pipeline artifacts)
Calibration after the round-0 fix: clean_control 0 (good), but reliability_gap
fell to 1 of 5 seeded bugs. The artifacts show why: the default CRASH oracle
only checks "does not raise", but the reliability bugs are WRONG VALUES from
non-crashing functions. The generated tests asserted isinstance(result, int)
(type, not value) and even encoded the bug as expected (safe_divide test
asserted ZeroDivisionError, which the docstring says should be a returned 0).
Two causes: oracle-type mismatch (crash cannot catch wrong values) and
implementation-biased generation (LLM asserts what the buggy code does).
Full write-up: docs/experiments/reliability-oracle-findings.md.

### Delivered for review
- **Correctness oracle (`feature/correctness-oracle`)**: a new oracle type
  whose prompt treats the DOCSTRING as the source of truth, warns the
  implementation may be buggy, and demands exact-value assertions (not
  isinstance/type checks). Wired into OracleType, the generator dispatch, and
  all --oracle CLI choices. Crash oracle unchanged (still right for crash-class
  defects).

### Regression gate (re-run needed)
Re-run lab calibration with --oracle correctness: expect reliability_gap -> ~5,
clean_control -> 0, complexity_findings -> 0. This is the recall test for
reliability defects.

## 2026-06-09 (later, repair-on-verification-failure)

### Delivered for review
- **Repair on verification failure (`feature/repair-on-verification-failure`)**:
  Observation 2. A function with no static finding but a runtime defect (a
  logical flaw caught by a failing test) is now routed to repair. The
  orchestrator captures per-function verification failures after each verify
  and feeds the previous round's failures into the next round's repair;
  RepairRequest gains a verification_failures field; the repair-skip
  short-circuit skips only when there are neither findings nor runtime
  failures; the repair agent prompt includes the failing test as evidence and
  is told to fix the code, not the test.

### Calibration status (post round-0 fix, from metrics.csv)
- clean_control: 1 exec_only bug (target 0), one residual false positive.
- complexity_findings: 0 (correct).
- reliability_gap: 2 exec_only bugs (target ~5), now UNDER-counting; round-0
  generated tests catch only 2 of 5 seeded bugs.
- security_findings: 0 exec_only (static findings present, correct).
- The gross over-counting is fixed; remaining gaps are round-0 test-generation
  QUALITY (one false positive, three missed bugs), a precision/recall matter,
  not a counting bug. Worth a focused look with the run.log next.

## 2026-06-09 (later, gap-at-round-0)

### Delivered for review
- **Gap measured at round 0 (`fix/gap-measured-at-round-0`)**: the lab
  calibration after Bug 2 still showed clean_control with 12 false bugs. Root
  cause: the gap metric read the FINAL round (and summed execution_only across
  ALL rounds), folding in GROW test noise from repair rounds. The gap is a
  round-0 property of the ORIGINAL code. Fixed both paths:
  `_executions_from_verification` reads the baseline (lowest round_number) round;
  `build_session_metrics` takes execution_only from the round-0 gap report only,
  not summed. Verified on the calibration shape: clean_control -> 0,
  reliability_gap -> 5.
- **Design doc** `docs/architecture/verification-repair-reward-design.md`:
  source-of-truth analysis with diagrams for all five observations (repair on
  verification failure, per-function vs per-unit coverage/reward, the unit-1/1
  label, per-file sessions/traceability), and the round-0 gap fix.

### OPEN items added this session (from the five observations)
- **Repair on verification failure** (observation 2): a function with no static
  findings but a round-0 runtime defect (logical flaw) should be routed to
  repair using the failing test as evidence. Designed, not yet implemented; own
  PR. Trigger lives in the orchestrator per-unit flow.
- **Progress label** (observation 4): add file position in dataset (file 7/289)
  and function position (fn 2/4) to the context; "unit 1/1" alone is
  uninformative for single-unit .py files. Small, own PR.
- **Session layout** (observation 5): keep one session per file (isolation is
  valuable) but place session dirs under the run output
  (runs/<name>/sessions/<file_stem>_<uuid>) and name them by file stem, so the
  run-to-session link is visible. Persistence-path change; own PR; must keep
  confirm/verify and the web UI working.
- **Per-function vs per-unit (observation 3)**: DECISION recorded, no loop
  change. Coverage/bugs stay per-function (correct granularity for RQ1/2/3 and
  the reward loop); aggregation to unit/run happens only at reporting time.

### Re-run after this merges
Lab calibration is again the gate: clean_control -> ~0, complexity_findings ->
~0, reliability_gap -> ~5. If those hold, the gap rate is trustworthy and ENVRI
can run for the headline.

---



### Merged this session (PRs in order)
- Fetcher: never prompt for git credentials; per-clone timeout (private/removed
  repos no longer hang the ENVRI crawl).
- Experiment file logging: both runners write `run.log` to the output dir, so
  `tail -f runs/<name>/run.log` gives live logs independent of screen/tmux.
- Gap-report Finding-object fix: `build_gap_report` accepted dicts but the
  in-memory metrics_only path passes `Finding` objects; crashed on any unit
  with static findings. Now normalises both. (Unblocked ENVRI: real notebooks
  almost all have static findings.)
- Observability + efficiency: per-unit progress prefix on every log line
  (`[unit 3/47 file.ipynb::7]` via contextvar + logging filter); repair skips
  the LLM when there are zero findings (saves credits); ingestion excludes
  `.ipynb_checkpoints` (both the gap-runner rglob and the directory scanner).

### Delivered for review (this session, pending merge confirmation)
- **Bug 2 baseline gate (`fix/baseline-gate-oracle-quality`)**: the
  oracle-quality fix. In repair rounds (round >= 1) a freshly generated test
  that fails against the original baseline is stripped (not a valid
  bug-detector). Does NOT run at round 0 (round 0 is the gap-detection pass;
  gating it would erase the bugs we measure). This targets the inflated gap
  rate (1.0 with clean-control false positives) and 0% HumanEval detection.
- **Docs sync (`docs/sync-state-fedllm-default`)**: FedLLM as the documented
  default everywhere; jupyter magic default changed from `openai` to `fedllm`
  (code + doc + test); README LLM section and CLI examples lead with FedLLM;
  workflow-design diagram fixed (round 0 is analyse+verify, not static-only;
  `--strategy feedback --llm fedllm`). Added this session log.

### Experiment findings to date (from runs the user shared)
- Lab calibration (pre-Bug-2): gap rate pegged at 1.0; clean_control reported
  11-16 false-positive "bugs"; reliability_gap over-reported (24 vs 5 seeded).
  Diagnosis: generated tests over-fire on correct code. Bug 2 is the fix.
- HumanEvalFix: 0% detection across all strategies, but 25 "bugs reported" per
  problem at 100% coverage; tests fail canonical solutions too. Same cause.
- The run.log (after file-logging shipped) was the key diagnostic: round 0
  clean functions `failed=0` (correct), round 1 `failed=2` on unchanged correct
  code (the over-counting), plus a 60s test timeout on a clean function.

### OPEN items (resume here)
1. **Re-run lab calibration after Bug 2 merges** (the regression gate):
   expect clean_control -> ~0, complexity_findings -> ~0, reliability_gap -> ~5.
   This is what makes the gap rate trustworthy. Command:
   `python scripts/run_gap_experiment.py --dataset datasets/lab
   --output runs/lab_calibration --pattern "*.py" --llm fedllm --rounds 5 --confirm`
2. **ENVRI headline run** once calibration is clean: full corpus, tmux,
   resumable, metrics_only retention, `--pattern "*.ipynb"`. Report gap rate
   with its 95% CI.
3. **RQ2/RQ3 confirm path** still produced 0 confirmed/0 refuted on the lab set
   even with `--confirm`. Investigate after Bug 2; the security findings should
   confirm. (Confirmed != 0 was null in output, so the path may not populate.)
4. **Verify the execution sandbox can import heavy ML deps** (tensorflow/torch)
   for ENVRI notebooks, or run a dependency-light subset; otherwise they ERROR.
5. **VM locale warning** (cosmetic): `echo 'export LANG=C.UTF-8' >> ~/.bashrc`
   on the VM is the zero-sudo fix.
6. **Credits**: user may hit FedLLM credit limits; resets ~2h. The repair-skip
   and checkpoint-exclusion changes reduce waste.

### Decisions worth remembering
- The baseline gate is round-aware by design: round 0 keeps gap-detecting
  tests, round >= 1 strips tests that regress against the baseline. Under the
  default FROZEN+REPLAY_ONLY policy (generate once at round 0, replay after),
  the gate mainly guards the GROW policies, which is where over-firing appeared.
- FedLLM (`fedllm:gpt-oss-120b`) is the project default everywhere; cost $0.00
  is correct (free for VO users), not a bug.

### Deferred / future (not blocking the thesis)
- In-app live metrics page; conference one-pager; per-round verified-fix
  tracking (PhD tier); wiring the fixed TruffleHog into a security defect-class
  study; multi-model HumanEval run for external validity.
