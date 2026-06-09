# QALLM session log

An append-only, dated record of what changed each working session and what is
outstanding. Purpose: preserve context across chat sessions so a new session
can pick up without re-deriving state. Newest entries at the top. This is a
log, not a plan; for priorities see `roadmap.md`, for design rationale see
`methodology-decisions.md`.

Conventions: each entry lists MERGED work (what landed), OPEN items (what is
left, with enough detail to resume), and any DECISIONS worth remembering.

---

## 2026-06-09

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
