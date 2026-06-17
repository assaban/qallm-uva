# QALLM lab dataset

A small, curated, version-controlled set of fixtures for repeatable lab tests
of the QALLM pipeline. Unlike the ENVRI/Li validation set (scraped at run time,
see `scripts/fetch_envri_dataset.py`), this set is committed and stable, so a
lab run is fully reproducible and has a documented answer key.

Run the whole set:

```
python scripts/run_gap_experiment.py \
    --dataset datasets/lab --output runs/lab --pattern "*.py" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --confirm --mutation-confidence
```

The fixtures are organised by what they exercise. Findings below were verified
against the actual analyzers (Bandit, Radon) and by executing the code, so this
manifest is an answer key, not an aspiration.

## reliability_gap.py: the verification gap (RQ1)

Lint-clean, low-complexity functions that are wrong at runtime. Static analysis
passes them; execution should find the defect.

| Function | Intended runtime defect | Verified |
| --- | --- | --- |
| `inclusive_range_count` | off-by-one (`inclusive_range_count(1,5)` returns 4, should be 5) | yes |
| `normalise_unit` | divides by max only, minimum does not map to 0 | yes |
| `accumulate` | mutable default argument shares state across calls | yes |
| `safe_divide` | guards `b is None` instead of `b == 0`, still divides by zero | yes |
| `first_even` | uses `n % 2 == 1`, returns the first ODD number | yes |

Expected: static analysis reports no reliability bug; execution-based
verification finds defects in all five. These drive the verification-gap rate.

## security_findings.py: confirmation (RQ2)

Code Bandit flags. Execution decides which are genuinely reachable.

| Function | Bandit finding (verified) | Execution-confirmable |
| --- | --- | --- |
| `evaluate_expression` | B307 use of eval (Medium) | yes, an injected call runs |
| `run_echo` | B602 subprocess shell=True (High), B404 (Low) | yes, shell interpolation |
| `build_query` | B608 string-formatted SQL (Medium, low confidence) | no DB oracle in the lab set; tests the not-directly-confirmable path |

Expected: security findings present; confirm/refute corroborates the eval and
shell cases, and `build_query` exercises the path where a finding has no
execution oracle.

## complexity_findings.py: not execution testable

Findings about source structure, not behaviour. The code is correct.

| Function | Finding (verified) | Note |
| --- | --- | --- |
| `deeply_nested` | Radon cyclomatic complexity B (6) | correct behaviour; complexity is structural, so confirm/refute should mark it not execution testable |
| `cryptic` | low maintainability (poor names/structure); Radon CC is A (1), so this is a maintainability, not a complexity, finding | correct behaviour; no runtime defect |

Expected: complexity/maintainability findings present; no runtime bug; these
classify as not execution testable, exercising that branch.

## clean_control.py: negative control

Correct, simple, secure functions. A sound pipeline finds nothing here.

Expected: no runtime defects, no security findings. Any bug QALLM reports on
this file is a false positive worth investigating, this file is the canary for
over-reporting (and for the incoherent-oracle and false-bug protections).

## How to use this as an answer key

After a lab run, check the aggregate against expectations:

- The verification-gap rate should be high (reliability_gap.py contributes
  execution-only defects with no matching static finding).
- Confirmation should corroborate the eval/shell security findings.
- clean_control.py should contribute zero bugs; if it does not, investigate
  before trusting a larger run.

This set is deliberately small (a handful of functions per category) so a full
`--confirm` lab run is quick and cheap, suitable for a smoke test after any
pipeline change, before committing to the large ENVRI run.
