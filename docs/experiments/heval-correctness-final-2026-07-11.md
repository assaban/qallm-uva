# HumanEvalFix correctness arm: final results (2026-07-11)

Run `runs/heval_correctness_20260710`: 492/492 problem-strategy pairs, zero
errors. Oracle correctness, seed 42, rounds 5, fedllm gpt-oss-120b. Pairs
with the completed crash arm (`runs/heval_v2_20260709`) as the oracle
ablation: identical configuration, one variable.

## Per strategy (n = 164 each)

| strategy | detected | repaired | mean coverage |
|---|---|---|---|
| hypothesis | 8 (4.9%) | 40 (24.4%) | 94.9% |
| oneshot | 3 (1.8%) | 40 (24.4%) | 93.7% |
| feedback | 7 (4.3%) | 44 (26.8%) | 95.4% |

Detection is differential and strict: generated tests must fail the buggy
version and pass the canonical one. Repair is adjudicated by the benchmark's
hidden tests.

## Strategy comparisons (McNemar exact, paired per problem)

Detection: feedback vs hypothesis p = 1.00; feedback vs oneshot p = 0.22.
Repair: feedback vs either baseline p = 0.39. No significant differences;
the detected sets are nearly disjoint, the signature of floor-level noise.

## Oracle ablation (crash vs correctness, paired within strategy)

| strategy | detection crash -> corr (p) | repair crash -> corr (p) |
|---|---|---|
| hypothesis | 5 -> 8 (0.58) | 20 -> 40 (0.005) |
| oneshot | 7 -> 3 (0.29) | 21 -> 40 (0.007) |
| feedback | 7 -> 7 (1.00) | 21 -> 44 (0.001) |

The matched oracle significantly roughly doubles repair within every
strategy and does not move differential detection. Mechanism consistent
with both observations: implementation anchoring (see
`reliability-oracle-findings.md`). Scoping consequence, stated in the
thesis: QALLM is a reliability instrument, not a functional-equivalence
checker. Thesis anchors: tab:ablation, sec:benchmark, sec:an-benchmark
(MD-009 records the statistics decision).
