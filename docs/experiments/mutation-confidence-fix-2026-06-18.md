# Mutation confidence: why it scored unknown, and the fix

## Symptom

With --mutation-confidence on, gap functions came back confidence=unknown
(score=None, killed=0) for most functions, even seeded reliability bugs whose
suites clearly detect the defect. On the reliability_gap lab session the
distribution was {high: 1, unknown: 3}.

## Cause

The mutation scorer writes the code under test to a temporary module and runs
the generated suite against each mutant. The generated tests import the function
from a specific module name, for example:

    from source_reliability_gap_c0 import inclusive_range_count

The scorer wrote the source under a different filename (the default
"source_module"), so every mutant run failed at import. With no test able to
run, no mutant could be killed; the scorer correctly judged the run
uninformative and returned unknown. A compounding bug in the scoring-source
selection ran the same broken import check and fell back to the buggy ORIGINAL
source, which has fewer mutable sites, so even the few scores produced were off.

This is the same class of issue fixed earlier in cross-evaluation: the source
must be written under the exact module name the tests import from.

## Fix

Derive the module name from the tests' import line and write the source under
it. score_oracle now defaults module_name to the derived name (falling back to
source_module when no import is present), and the scoring-source check in
gap_confidence uses the same derivation. No change to mutant generation or the
kill logic.

## Result

On the same lab session, all four gap functions now score high (1.0), every
mutant killed: {high: 4}. The seeded reliability bugs have sensitive oracles, so
their gap findings are high-confidence, which is the expected and correct
outcome.

## Why it matters for the thesis

The headline gap rate can be reported twice: over all findings, and restricted
to high-confidence findings. That restricted figure is the direct evidence the
gap reflects real defects rather than weak-oracle artefacts. Before this fix the
restricted figure was mostly unknown and unusable; now it is populated. This
should be confirmed on the E1/E2 runs (the same code path), so it is worth
fixing before those land rather than after.

## Correction to the earlier calibration note

The earlier calibration note attributed "confidence: null" to the scorer. The
null seen in judge.json is a separate field (the judge LLM's own confidence) and
is benign. The real mutation-confidence defect is the module-name mismatch
described here.
