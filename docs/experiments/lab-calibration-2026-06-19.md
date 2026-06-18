# Lab calibration evaluation: 2026-06-19 run

Run: `scripts/run_gap_experiment.py --dataset datasets/lab --output
runs/lab_calibration --pattern "*.py" --llm fedllm --rounds 5 --oracle
correctness --samples 1 --confirm --mutation-confidence`. Four lab files, one
session each, gpt-oss-120b (FedLLM, free). This is the first full calibration
under the current build, with confirm and mutation-confidence both on.

## Verdict: the instrument is calibrated

Every file lands where the MANIFEST answer key says it should. Nothing
surprising, which for a calibration run is exactly the point.

| File | Static | Gap bugs | Confidence | Expected | Match |
| --- | --- | --- | --- | --- | --- |
| reliability_gap.py | 0 | 5 | 5 high | 5 seeded wrong-value bugs caught | yes |
| clean_control.py | 0 | 1 | 1 high | ~0, one known safe_mean test FP | yes |
| complexity_findings.py | 1 | 1 | 1 high | weak-oracle artefact on cryptic | yes |
| security_findings.py | 4 | 0 | n/a | 3 inconclusive, 0 confirmed | yes |

### Reliability (the core claim)

All 5 seeded wrong-value bugs are caught by the correctness oracle as gap bugs,
and all 5 score high mutation confidence (every mutant killed). This is the
headline calibration result: the bugs static analysis misses are caught by
execution, and the oracle that caught them is provably sensitive. The
mutation-confidence fix from the previous session is confirmed working on a
fresh pipeline run, not just retroactively: the run log shows 5/5, 6/6, 7/7
mutants killed per function and a run-level distribution of {high: 7}.

### Clean control

One gap bug on safe_mean. This is the documented false positive: the generated
test asserts a wrong expectation, the code is correct. It is the known limitation
recorded in the MANIFEST, not a regression. Worth a sentence in the thesis as an
honest account of generated-test noise, and a reason the mutation-confidence
qualifier matters (a sensitive oracle is not the same as a correct expectation).

### Complexity

cryptic produces one gap bug, the expected weak-oracle artefact: a generated
test encodes a wrong expected value for an obscure function. high mutation
confidence here is consistent: the suite is internally sensitive even when its
expectation is off, which is precisely why mutation confidence is a sensitivity
measure and not a correctness guarantee. State this limitation explicitly.

### Security

4 static findings, 0 confirmed, 3 inconclusive, 0 refuted. This matches the
documented position: security confirmation via generated exploit is out of
scope, so inconclusive is the honest result. The metrics now surface
inconclusive explicitly, so three inconclusive findings no longer look like
zero findings.

## The aggregate verification_gap_rate of 1.0 is the known degenerate artefact

Do not report 1.0 as a headline. With confirm on but every gap bug being
gap-by-construction (reliability) or inconclusive (security), the confirmed
count is 0 and the rate collapses to bugs/bugs. This is the artefact already
documented for E1: the meaningful gap rate needs a corpus where some static
findings are execution-confirmable, which the lab set is not designed to be. The
lab set validates detection and confidence, not the population-level rate; E1
and E2 on ENVRI provide the rate.

## Net

The lab calibration passes cleanly. Detection recall is 5/5 on the seeded bugs,
mutation confidence is high across all 7 gap bugs with no unknowns, the known
clean-control FP appears exactly once as expected, security is inconclusive by
design, and the only aggregate oddity (gap rate 1.0) is the already-understood
degenerate case. The instrument is ready for the headline runs.
