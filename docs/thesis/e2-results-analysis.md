# E2 results analysis: the full ENVRI forest corpus run

**Run**: `runs/e2_final`, completed 2026-07-10. Dataset: `datasets/envri_forest`,
1,843 notebooks across 285 projects (path manifest sha256 `dd3ad6a7...`).
Configuration: feedback strategy, 5 rounds, correctness oracle, single sample,
lexicographic judge, confirm and mutation confidence on, 4 workers,
fedllm gpt-oss-120b. Every number below is produced by
`scripts/analyze_gap_results.py` from `results.jsonl`; the shipped
`aggregate.json` of this run predates the roll-up fixes (MD-008) and its
headline fields must not be quoted.

Sessions: 1,814 analyzed, 29 errored (1.6%), zero corrupt rows.

## RQ1: the verification gap

**Headline**: 732 of 4,298 execution-verified functions that pass static
analysis fail a generated correctness test: a count-weighted gap rate of
**17.0% (95% CI [14.7%, 19.6%]**, session-resample bootstrap, 10,000 draws).

**Project-weighted view**: over the 112 projects with at least five verified
functions, the macro-average gap rate is **21.2%**, the median **11.1%**, and
the IQR **[0%, 35%]**. Thirty-nine of the 112 projects show zero gaps; the
maximum is 100%. The spread spans two orders of magnitude, and project size
does not predict it (Spearman rho 0.06): gap prevalence is a property of
engineering practice, not of scale.

**Dominance sensitivity**: one repository, `sentinel-tree-cover`, contributes
948 verified functions, 22% of the entire denominator, at a 1.1% gap rate.
Excluding it, the count-weighted rate is **21.6%**. All three views (count-
weighted, project-weighted, and the exclusion sensitivity) are reported
together in the thesis; each alone misleads in a different direction.

**Oracle confidence**: all 732 gap findings were mutation-scored. 533 (73%)
high confidence, 86 medium, 79 low, 34 unknown. The conservative headline
variant, counting only high-confidence findings, is 533/4,298 = **12.4%**.
Reporting both the full and the high-confidence-only figure bounds the claim
from above and below.

Context counts: 41,773 units analyzed; 629 functions not execution-testable;
11 incoherent oracles dropped before execution (MD-002); 2,281 static findings
across the corpus.

## RQ2: confirmation, as counts

**747 confirmed reliability defects**, each with a persisted reproducing test
against the round-0 baseline. Static findings: 0 confirmed, 0 refuted, 265
inconclusive. The zeros are by design, not failure: the static analysers emit
security, complexity, and maintainability findings, none of which the
execution path can adjudicate, and security is inconclusive by design
(MD-006). Refutation is structurally near-impossible, so no confirmation
rate is reported (MD-007); the count and its reproducing tests are the result.

## RQ3: verified fixes

**391 of 669 confirmed defects with a fix attempt were provably fixed:
58.4% (95% CI [53.1%, 63.9%])**, where "provably" means the defect's own
reproducing test passes against the repaired code. Unlike the gap rate, the
fix rate is homogeneous across the corpus: 58.1% in the first 1,376 sessions,
58.4% at completion. Repairability appears to be a property of the defect
class; prevalence is a property of the project.

## The truncation vignette (for threats to validity)

The 75%-complete partial (1,376 sessions) showed a 24.6% gap rate. The
completed corpus shows 17.0%. The difference is entirely compositional: the
resumed tail comprised 42 projects untouched by the first batch, processed in
discovery order, including the dominant low-gap repository. Had the partial
been reported as final, the headline would have been off by 7.6 points. This
is the standing non-random-truncation rule made concrete, and it is reported
as a worked example rather than hidden.

## Provenance

The run spans two commits: sessions before the disk-space interruption at
`064ddc7`, the resumed tail and the recorded manifest at `c7c0581`
(`dirty: false` in both cases). The only source difference between the two is
`src/qallm/experiments/humaneval_metrics.py`, which the gap pipeline does not
import; every code path this experiment executed is single-version (MD-008).
The interruption itself truncated the final `results.jsonl` line mid-write;
the sanitized file has zero corrupt rows and the interrupted input was re-run
on resume.

## What feeds the thesis where

- Results chapter, RQ1 section: the three-view gap-rate presentation and the
  confidence-bounded variant.
- Results chapter, RQ2/RQ3 sections: counts framing and the fix rate with CI.
- Threats to validity: the truncation vignette and the provenance note.
- Reproducibility statement: `scripts/analyze_gap_results.py` plus the run
  manifest; every reported number regenerates from `results.jsonl`.
- LaTeX: `docs/thesis/e2-numbers.tex` carries every figure as a macro.
