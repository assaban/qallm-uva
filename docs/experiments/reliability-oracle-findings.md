# Why the reliability bugs are missed: an oracle-type mismatch

From the lab calibration artifacts (session 20260609_220309, reliability_gap.py).
This is the most important finding since the round-0 fix.

## The numbers

reliability_gap.py has 5 seeded bugs, one per function, all lint-clean and
non-crashing (wrong values, not exceptions). Round-0 verification result:

| Function | Seeded bug | round-0 failed |
| --- | --- | --- |
| inclusive_range_count | off-by-one (`end - start`, should be `+1`) | 0 |
| normalise_unit | divides by max only, not (max - min) | 0 |
| accumulate | mutable default argument | 0 |
| safe_divide | guards `b is None` instead of `b == 0` | 0 |
| first_even | uses `n % 2 == 1`, returns first ODD | 1 |

Only 1 of 5 bugs caught. clean_control is now 0 (good), but reliability_gap is
badly under-detecting.

## Root cause: the crash oracle cannot catch wrong-value bugs

The generated tests assert the wrong thing. Examples from the artifacts:

- `inclusive_range_count`: every test is `assert isinstance(result, int)`. The
  function returns 10 for (0,10) when it should return 11, but the test only
  checks the TYPE, not the value, so it passes on buggy code.
- `safe_divide`: the test is `with pytest.raises(ZeroDivisionError):
  safe_divide(5, 0)`. The docstring says it should RETURN 0 on a zero divisor;
  the buggy code crashes; the test asserts the crash is correct. The test
  encodes the bug as expected behaviour.

Two compounding causes:

1. **Oracle-type mismatch.** The default oracle is `crash`, whose prompt
   literally says "test whether the function handles edge cases without raising
   unhandled exceptions." That is a robustness oracle. The reliability bugs are
   wrong VALUES from functions that do not crash, so a crash oracle
   structurally cannot catch them. This is not a prompt typo; it is the oracle
   doing exactly what it is designed to do.

2. **Implementation-biased generation.** The prompt shows the function SOURCE
   and asks the LLM to test it. The model reads the (buggy) implementation and
   asserts what the code DOES, not what the docstring SAYS it should do. That
   is why `safe_divide`'s test expects the crash: the model saw the code crash
   and encoded that as the expectation.

`first_even` was caught only incidentally: one of its value assertions happened
to contradict the buggy behaviour.

## Why this matters for the thesis

The verification gap claim is "execution finds defects static analysis misses."
For that to hold on RELIABILITY defects (the most common real-world class),
QALLM needs an oracle that checks CORRECTNESS, not just crash-freedom. Right
now, on the very dataset built to demonstrate the gap, QALLM misses 4 of 5
reliability bugs because the default oracle and the implementation-biased prompt
both steer away from value correctness. An examiner running the lab set would
see this immediately. It must be fixed before the ENVRI headline.

## The fix (design)

Two changes, the first is the substantive one.

### 1. A specification-based correctness oracle
Add a `correctness` oracle (or strengthen the crash-oracle prompt) that:
- Derives expected outputs from the DOCSTRING and the function's stated intent,
  NOT from the implementation. The prompt should present the docstring as the
  source of truth and explicitly warn: "the implementation may be wrong; assert
  what the docstring promises, not what the code does."
- Requires exact-value assertions for concrete inputs (`assert f(0, 10) == 11`),
  not type/shape checks.
- Optionally withholds or de-emphasises the implementation so the model is not
  anchored on buggy behaviour. (Showing the signature + docstring + a few
  argument examples may be enough; the body biases the oracle.)

### 2. Make it the default for the gap experiment
The reliability gap is a correctness question, so the gap experiment should run
the correctness oracle (or a crash+correctness combination), not crash alone.
The crash oracle remains valuable for the crash-class defects; this is about
matching the oracle to the defect class under study.

### Regression gate
Re-run lab calibration with the correctness oracle:
- reliability_gap -> ~5 (the seeded bugs caught by value assertions)
- clean_control -> 0 (correct code passes value assertions)
- complexity_findings -> 0 (structural, no runtime defect)
- security_findings -> static findings confirmed where executable

That is the instrument working: high recall on real reliability bugs, no false
positives on clean code.

## Update (after the first correctness-oracle run): the body anchors the model

Adding the correctness oracle improved recall (reliability_gap 1 -> 2 of 5,
clean_control held at 0), but three bugs were still missed. The artifacts show
why: even with the docstring presented as the source of truth and an explicit
"the implementation may be wrong" warning, the model still derived expected
values from the code. The clearest evidence, the generated test for
inclusive_range_count contained:

```python
assert result == end - start  # expected buggy behavior
```

The model read the buggy body, computed `end - start`, and even labelled it
"expected buggy behavior". Two more:
- safe_divide: asserted `pytest.raises(ZeroDivisionError)` for b=0, mirroring
  the buggy crash, when the docstring says it should return 0.
- accumulate: the mutable-default bug only surfaces across MULTIPLE calls; every
  generated test passed a fresh bucket and called once, so it never triggered.

### Fix: withhold the implementation body
The correctness oracle now shows only the SIGNATURE and docstring, never the
body. With no code to anchor on, the model must compute expected values from
the spec. The prompt also adds explicit guidance for stateful/cross-call
behaviour (the accumulate class) and clarifies that an edge input the spec says
should RETURN a value must be asserted as a return, not a raise (the safe_divide
class).

### Regression gate
Re-run lab calibration with --oracle correctness; expect reliability_gap -> ~5
(all seeded bugs caught), clean_control -> 0. If a bug is still missed, its
artifact shows whether the model mis-derived the expected value from the spec,
which is a prompt-refinement signal, not a structural one.

## Honest framing

The round-0 counting fix was necessary and correct, but it exposed that the
DETECTION itself was weak for reliability defects, previously masked by the
over-counting noise. This is good: the calibration set has now isolated the real
problem (oracle quality for wrong-value bugs), which is a precise, fixable
target and a genuinely interesting thesis point (oracle design determines which
defect classes the verification gap can surface).
