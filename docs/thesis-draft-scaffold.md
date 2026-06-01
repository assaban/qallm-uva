# Execution-Based Quality Assessment of AI-Generated Code in Jupyter Notebooks

**A thesis draft scaffold.** This is a structural starting point, not finished
prose. Each section states its purpose, the claim or content it must carry,
and where the supporting evidence comes from in the QALLM system. Placeholders
in [brackets] mark numbers to be filled from real runs. The point is a
foundation that is honest about what has been shown and what has not.

Throughout, dashes are avoided as punctuation per the author's convention;
commas, semicolons, and colons are used instead.

---

## Abstract

[To be written last.] One paragraph: research software is increasingly written
or assisted by large language models, often in Jupyter notebooks; static
analysis is the standard quality gate but cannot observe runtime behaviour;
this thesis presents QALLM, an execution-based, quality-model-guided
improvement pipeline that treats static findings as hypotheses and execution
as the judge; across [N] notebooks it found that [X]% of code passing static
analysis still contained execution-reproducible defects (the verification
gap), confirmed [Y]% of static findings by execution, and provably fixed
[Z]% of confirmed findings; the contribution is the method, the open
implementation, and the empirical characterisation of the gap.

## 1. Introduction

Purpose: motivate the problem and state the contribution.

- Research software quality matters and is under-served; notebooks especially
  (exploratory, rarely tested, increasingly LLM-authored).
- Static analysers (Bandit, Radon, SonarQube) are the de facto quality gate.
  They are valuable and necessary, and this work builds on them rather than
  competing with them. Their structural limit: they reason about source text,
  not runtime behaviour, so they miss defects that only manifest on execution
  and they raise findings that may not be reproducible.
- The gap this leaves: code can pass static analysis and still be wrong. This
  is the "verification gap".
- Contribution, stated plainly:
  1. A method that treats each static finding as a hypothesis and uses
     execution to confirm, refute, or supplement it, then to verify fixes.
  2. An open implementation (QALLM) realising the method end to end.
  3. An empirical characterisation of the verification gap on AI-generated
     notebook code, with three reproducible metrics.
- Research questions (carried from the proposal, refined):
  - RQ1: To what extent does execution-based assessment reveal defects that
    static analysis of AI-generated notebook code misses?
  - RQ2: How reliably can individual static findings be confirmed or refuted
    by automatically generated, executed tests?
  - RQ3: When a repair is applied, can the fix be verified by execution, and
    how often does a repair that satisfies static analysis fail to fix the
    underlying defect?

## 2. Background and related work

Purpose: situate the work; show the gap in the literature is real.

- Static analysis for Python and for research software; what each tool sees.
- Quality models: ISO/IEC 25010, and the role and lifecycle-aware framing of
  Volentir et al. (QRS 2025), on which QALLM's quality profiles build
  (EVERSE, FAIR4RS, ISO 25010). [Cite and summarise.]
- LLMs for code generation and for test generation; the reliability problem.
- Execution-based / dynamic approaches and search-based test generation;
  position QALLM relative to them.
- The under-addressed point: using execution specifically to adjudicate
  static findings and to verify repairs, on notebook code. [This is the gap.]

## 3. Method

Purpose: describe the QALLM method precisely enough to reproduce.

### 3.1 Overview

The pipeline: select a quality model, establish a baseline (Round 0: analyse
and verify the original code, no repair), then N improvement rounds (repair,
re-analyse, verify, judge accept or abandon), then a final report. The LLM
acts as test generator and code repairer via an API with quantitative
feedback; it is not trained. [Frame as iterative prompting with feedback, not
model training.]

### 3.2 Static analysis as hypotheses

Findings from Bandit, Radon, and SonarQube are normalised into a common
finding model (tool, type, severity, line, message, rule). Each finding is a
hypothesis to be adjudicated by execution, not an end state.

### 3.3 Execution-based verification

Test generation oracles (crash, property, metamorphic), the sandboxed
executor, and the FROZEN+GROW test-accumulation policy that gives a stable,
growing oracle and enforces no-regression across rounds. The ERROR vs BUG
distinction: only a test that ran and failed is evidence of a defect; a test
that errored never ran and is excluded from all defect counts. Generated
tests are AST-validated before running (undefined fixtures are dropped), so
the signal is not polluted by tests that could never execute.

### 3.4 The verification gap

Per round, each static finding's line is mapped to its enclosing function;
the finding is classified as confirmed (the function has an execution-found
bug), unconfirmed (tested, no bug), or untested (no test ran). The gap is the
set of execution-found bugs in functions with no static finding: defects
static analysis missed entirely. [Define the verification-gap rate formally.]

### 3.5 Confirm and refute individual findings

For a finding whose type execution can judge (reliability, security), a
targeted test is generated to reproduce that specific finding. Type-aware:
for reliability, a failing test confirms the bug; for security, a passing
exploit test confirms reachability. Complexity and maintainability findings
are properties of the source, not runtime behaviour, and are explicitly not
execution-testable. [Define the confirmation rate; state its honest limit:
confirmation is corroboration at the targeted level, refutation is evidence
of a candidate false positive, not proof.]

### 3.6 Verified fixes

When a finding was confirmed by a reproducing test, the same test is re-run
against the repaired code. The fix is verified when the test that
demonstrated the defect now shows it gone (a reliability test that now passes,
a security exploit test that now fails). A repair that removes the static
finding without fixing the underlying defect is detected as "not fixed".
[Define the verified-fix rate.]

### 3.7 Research method (TAR)

Technical Action Research: the artifact (QALLM) is built and then exercised
across iterations from controlled to realistic conditions. [Tie to Wieringa
and Moralı; mirror the proposal's framing.]

## 4. Implementation

Purpose: enough detail that the system is credible and reproducible.

- Architecture: ingestion, analysis, verification (loop, executor, reward,
  generator, sandbox), reporting. [Map to the package structure.]
- Models: local (Ollama, gemma family) and hosted (OpenAI) via one interface.
- Static tools integrated: Bandit, Radon, Ruff, TruffleHog, SonarQube.
- Reproducibility: every run persists per-round source, static findings, and
  verification results; the three metrics are exported per session (JSON and
  CSV) and aggregated across sessions, count-weighted. [This is the evidence
  pipeline for Chapter 5.]
- Open source; commit history; the web interface for inspection.

## 5. Evaluation

Purpose: answer the research questions with the metrics, honestly.

### 5.1 Setup

Dataset: [Li's 2,796 notebooks from 277 projects, or the subset used.]
Models: [which, and why]. Quality profile(s): [which]. Budget caps: [values].
Procedure: for each unit, run the pipeline; record the per-session metrics;
aggregate. [State exactly what was run, so it is reproducible.]

### 5.2 RQ1: the verification gap

Report the verification-gap rate across the dataset: of all
execution-found defects, the share that no static tool flagged.
[Verification-gap rate = X%, N = ...]. This is the headline empirical result.
Break down by finding type and by oracle. Discuss what kinds of defects
execution catches that static analysis does not.

### 5.3 RQ2: confirming and refuting findings

Report the confirmation rate: of static findings execution could test, the
share it reproduced. [Confirmation rate = Y%.] Report how many findings were
not execution-testable (complexity, maintainability) and why excluding them
from the rate is correct. Discuss refuted findings as candidate false
positives, with the caveat that refutation is not proof.

### 5.4 RQ3: verifying fixes

Report the verified-fix rate: of confirmed findings re-tested after repair,
the share provably fixed. [Verified-fix rate = Z%.] Report the "not fixed"
cases: repairs that satisfied the static tool but did not fix the defect.
[This is a distinct, citable finding: static-only pipelines would mark these
resolved.]

### 5.5 Threats to validity

- Construct: confirmation is corroboration, not per-line causation; test
  generation quality bounds what can be confirmed; refutation depends on the
  generator finding a triggering input.
- Internal: model nondeterminism; budget caps truncating rounds; the
  ERROR/discarded exclusions (argue these strengthen, not bias, the gap rate).
- External: notebook dataset representativeness; model choice; Python only.
- Conclusion: count-weighted aggregation choices; sample size.

## 6. Discussion

What the gap rate means for how research software should be quality-gated;
where QALLM complements rather than replaces static analysis; cost and
practicality; the role of local vs hosted models.

## 7. Conclusion and future work

Restate the contribution and the headline numbers. Future work: per-round
verified-fix tracking, larger and multi-language datasets, tighter
per-finding causal linking, integration into CI.

---

## Appendix: metric definitions (authoritative)

Stated here once, precisely, and referenced from the text.

- **Verification-gap rate** = execution_only / (confirmed_findings +
  execution_only), where execution_only is the count of execution-found bugs
  in functions with no static finding, and confirmed_findings is static
  findings whose function had an execution-found bug. Excludes errored and
  discarded tests.
- **Confirmation rate** = confirmed / (confirmed + refuted), over findings
  whose type execution can test. Not_execution_testable findings are excluded
  from the denominator.
- **Verified-fix rate** = verified_fixed / (verified_fixed + not_fixed), over
  confirmed findings re-tested after repair. Inconclusive results excluded.

All three are produced per session and aggregated count-weighted across
sessions by the QALLM metrics export, so every number in Chapter 5 is
reproducible from the persisted run artefacts.
