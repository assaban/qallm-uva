# QALLM session log

An append-only, dated record of what changed each working session and what is
outstanding. Purpose: preserve context across chat sessions so a new session
can pick up without re-deriving state. Newest entries at the top. This is a
log, not a plan; for priorities see `roadmap.md`, for design rationale see
`methodology-decisions.md`.

Conventions: each entry lists MERGED work (what landed), OPEN items (what is
left, with enough detail to resume), and any DECISIONS worth remembering.

---

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
