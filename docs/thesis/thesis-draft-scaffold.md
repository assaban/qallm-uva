# Execution-Based Quality Assessment of AI-Generated Code in Jupyter Notebooks

**A thesis draft scaffold.** This is a structural starting point, not finished
prose. Each section states its purpose, the claim or content it must carry,
and where the supporting evidence comes from in the QALLM system. Placeholders
in [brackets] mark numbers to be filled from real runs. The point is a
foundation that is honest about what has been shown and what has not.

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

Research software quality matters and is under-served, and notebooks are the
sharpest case: they are exploratory, rarely tested, and increasingly authored by
language models. Static analysers (Bandit, Radon, SonarQube, and others) are the
de facto quality gate for such code. They are valuable and necessary, and this
work builds on them rather than competing with them. Their structural limit is
that they reason about source text, not runtime behaviour, so they miss defects
that only manifest on execution, and they raise findings that may not be
reproducible. The gap this leaves is simple to state and consequential: code can
pass static analysis and still be wrong. This is the verification gap, and
measuring it on AI-generated notebook code is the subject of this thesis.

The work makes three contributions:

1. **The verification-gap method.** Each static finding is treated as a
   hypothesis that execution adjudicates: confirm it, refute it, or supplement it
   with defects no analyser flagged, and then verify that a repair actually
   removed a demonstrated defect. The verification gap is defined formally and
   measured.
2. **An EVERSE-aligned judge.** Repairs are accepted or rejected by a
   lexicographic ordering over research-software quality dimensions, so a
   higher-priority concern (security, then reliability) is never traded for a
   lower one, and results can be reported per dimension.
3. **Mutation-based oracle confidence.** Each gap finding carries a confidence
   grounded in how well the test that found it detects injected faults, a
   positive soundness check that answers whether the execution-found defects are
   real.

These are realised end to end in an open implementation, QALLM, and characterised
empirically with reproducible metrics and per-finding confidence. The iterative
generation loop that runs through all three is iterative prompting with
quantitative feedback over an external LLM API, not the training of a custom
model; this is stated here to fix the scope precisely.

Research questions (carried from the proposal, refined):

- **RQ1**: To what extent does execution-based assessment reveal defects that
  static analysis of AI-generated notebook code misses?
- **RQ2**: How reliably can individual static findings be confirmed or refuted
  by automatically generated, executed tests?
- **RQ3**: When a repair is applied, can the fix be verified by execution, and
  how often does a repair that satisfies static analysis fail to fix the
  underlying defect?

These refine the proposal's questions. The object of study, execution-based
assessment of AI-generated notebook code, is unchanged; the questions are stated
in the measurable form the implementation made possible, namely the size of the
verification gap (RQ1), the reliability of confirming or refuting individual
findings (RQ2), and the verifiability of repairs (RQ3). The longer justification
is recorded in docs/thesis/rq-evolution.md.

## 2. Background and related work

Purpose: situate the work; show the gap in the literature is real.

### 2.1 Static analysis and its blind spot

Static analysers reason about source code without running it. For Python, tools
such as Bandit (security), Radon (complexity and maintainability), Ruff (style
and a broad class of correctness lints), and TruffleHog (secrets), together with
industrial platforms like SonarQube, cover whole categories of issue cheaply and
at scale. [Cite the tools and a survey of static analysis for Python.] Their
strength is also their limit: because they never execute the code, they cannot
observe behaviour. A function can be free of every lint and security finding and
still return the wrong value on ordinary inputs. This blind spot is the space the
present work measures.

### 2.2 Quality models for research software

Assessing research software needs a notion of quality that goes beyond "does it
lint cleanly". ISO/IEC 25010 provides a general software product quality model,
and the research-software community has developed frameworks that foreground the
properties that matter for reproducible science, notably EVERSE and FAIR4RS, with
a lifecycle-aware framing developed by Volentir et al. (QRS 2025) on which
QALLM's quality profiles build. [Cite and summarise ISO 25010, EVERSE, FAIR4RS,
and Volentir et al.] QALLM adopts these dimensions directly: it tags every
finding with the dimension it concerns and orders its judge lexicographically
over them, so the quality model is not a backdrop but an operative part of the
method (Section 3.8).

### 2.3 LLMs for code and test generation

Large language models now generate both production code and tests. Their use for
research code is the motivation for this work: AI-generated code is plausible and
often passes static analysis, yet its behavioural correctness is not guaranteed.
[Cite LLM code-generation and the reliability concern.] LLMs are also used to
generate tests, which is the mechanism QALLM relies on, but a generated test is
only useful if it is a sound and sensitive oracle. The literature on LLM test
generation gives less attention to whether the generated oracle can actually
distinguish correct from incorrect behaviour, which is precisely the question
QALLM's mutation-based confidence answers (Section 3.9). [Cite LLM test
generation; Islam and Zhao's lifecycle-aware LLM feedback work as a theoretical
foundation.]

### 2.4 Execution-based and search-based testing

Dynamic and search-based test-generation approaches (for example property-based
testing and search-based test generation) execute code to find faults, and QALLM
shares their execution-first stance. [Cite property-based testing and
search-based test generation.] What distinguishes QALLM is the target of
execution: rather than maximising coverage or finding arbitrary faults, it uses
execution specifically to adjudicate static findings (treating each as a
hypothesis) and to verify that a repair removed a demonstrated defect.

### 2.5 The under-addressed point

Across these strands, the specific combination QALLM occupies is
under-addressed: using execution to adjudicate static findings and to verify
repairs, on notebook code, with a confidence on each verdict. Prior work stops
short on at least one of these axes, it confirms findings without verifying
fixes, generates tests without measuring their adequacy as oracles, or targets
scripts rather than the notebook form in which research code is actually written.
This is the gap the thesis addresses. [Position precisely against the closest
prior work, including Li's notebook dataset work and the QRS 2025 metrics
framework.]

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

### 3.8 The judge and the EVERSE quality model

A repair round produces a candidate variant of a function; the pipeline must
decide whether that variant is an improvement over its parent before accepting
it into the lineage. A single blended quality score would obscure the kind of
trade that matters most: a change that tidies style while breaking behaviour
must never be accepted. QALLM therefore judges variants with a lexicographic
ordering over the quality dimensions of the EVERSE research-software quality
model, so a higher-priority dimension is never sacrificed for a lower one.

The dimensions, in priority order, are Security, Reliability, Maintainability,
Reproducibility, and FAIRness. The order encodes an engineering judgement about
research software. Security is first because a vulnerability blocks use
outright. Reliability is next, because code that returns the wrong answer is not
useful regardless of how readable it is. Maintainability and Reproducibility
support the long-term health of the software but do not, on their own, block a
release. FAIRness, the findability and documentation properties, is hygiene that
should not override a behavioural concern. The judge compares a variant to its
parent dimension by dimension; the first dimension on which they differ decides
the verdict, and a regression on any dimension is never compensated by a gain on
a lower one.

The quality model does more than rank variants. Each static finding is tagged
with the EVERSE dimension it concerns when it is normalised, and that tag routes
the work: it selects which gate the evidence must pass and frames the repair
prompt for the relevant concern. It also makes the results legible to a
research-software audience, the verification gap can be reported per dimension
(for example, concentrated in Reliability), which is a sharper and more
defensible claim than a single blended rate and which speaks the language of the
framework the community is adopting. Quality profiles are keyed to the EOSC
software lifecycle stage, so the set of dimensions evaluated can differ by stage;
the implementation-stage profile is the default in this work.

### 3.9 Oracle confidence by mutation testing

The verification gap rests on a claim that invites immediate scrutiny: that an
execution-found defect is a real defect and not an artifact of a weak generated
test. The guards described above are all conservative filters; they remove
unsound tests (an incoherent oracle, a test that fails the original baseline in
a repair round) but they do not provide positive evidence that a surviving test
is a sensitive detector. A test can pass every filter and still be too weak to
distinguish correct from incorrect behaviour, the canonical example being an
oracle that only checks the return type and so accepts any value of that type.

To supply that positive evidence, QALLM mutation-tests the oracle itself.
Mutation testing is the established technique for measuring whether a test suite
can detect faults: small, semantics-changing faults are injected into the code
under test, and the suite is judged by how many it catches. QALLM applies this
to each function it flags. It generates mutants of the function using a set of
classic operators, arithmetic operator replacement (covering the common numeric
forms including modulo, floor division, and power), relational operator
replacement, boolean operator swaps, constant replacement, and return-value
replacement, mutating only the target function and bounding the number of
mutants per operator so the cost stays proportional to the function's size. It
then runs the function's generated test suite against each mutant. A mutant is
killed if at least one test fails (the suite detected the injected fault) and
survives if every test passes. A mutant that errors on every test is treated as
not viable and excluded, because it measures the suite's tendency to crash, not
its power to discriminate.

The mutation score, the fraction of viable mutants the suite kills, becomes a
confidence for the gap finding the suite produced: high when the suite kills most
injected faults, low when it kills few. The effect is to distinguish, without
human inspection, exactly the strong-from-weak oracle case that is otherwise hard
to catch. On a representative reliability function whose correct definition is an
inclusive count, an oracle asserting exact return values kills every mutant and
scores high, whereas an oracle that only checks the return type kills only the
mutant that returns None and scores low. The headline gap rate can then be
reported twice, over all findings and restricted to high-confidence findings; if
the two are close, that is direct evidence that the gap reflects real defects
rather than test noise. This is a positive, quantitative soundness check layered
on top of the conservative filters, and it is the pipeline's strongest answer to
the question of whether its execution-found defects are real.

## 4. Implementation

Purpose: enough detail that the system is credible and reproducible.

### 4.1 Architecture

QALLM is a staged pipeline orchestrated per code unit. Ingestion turns a Python
file or a Jupyter notebook into code units (one per `.py` file or per notebook
cell), each holding the functions defined within it. The analysis stage runs the
static analysers through a registry and normalises their output into a single
finding model tagged with an EVERSE dimension. The verification stage generates
tests, executes them in a sandbox, and accumulates results across rounds; the
repair stage proposes fixes for findings and for runtime failures; the judge
accepts or rejects each repaired variant against its parent. A reporting layer
persists per-round artefacts and exports the metrics. The packages map onto these
stages directly (`ingestion`, `analysis`, `verification`, `repair`, `judge`,
with `orchestrator` as the conductor and `metrics_export`/`stats` for reporting),
and a React/TypeScript web UI exposes runs, the gap view, the confirmation and
verified-fix actions, the oracle-confidence view, and the documentation.

### 4.2 Models behind one interface

The pipeline talks to language models through a single provider interface, so
local models (the project default is FedLLM, an EGI-hosted `gpt-oss-120b` that is
free for VO users) and hosted models (OpenAI, Anthropic) are interchangeable.
This makes the model a configuration choice rather than a code change and is what
would make a cross-model comparison (future work) inexpensive.

### 4.3 Static analysers

Five analysers are integrated through the registry: Bandit (security), Radon
(complexity and maintainability), Ruff (style and correctness lint), TruffleHog
(secrets), and SonarQube (a broad industrial platform). Each analyser's raw
output is normalised into the common finding model, so the judge and the gap
analysis treat findings uniformly regardless of source. The registry design
means adding an analyser is a local change.

### 4.4 The sandbox and test accumulation

Generated tests run in an isolated subprocess sandbox with a wall-clock timeout,
so a misbehaving generated test cannot stall or compromise a run. Across repair
rounds, the verified test suite follows a FROZEN+GROW policy: tests that have
passed are retained and new tests are added, so a repair must satisfy the
accumulated evidence rather than a single round's tests.

### 4.5 Reproducibility and the evidence pipeline

Every run persists, per round, the source under test, the static findings, the
verification results, the judge decisions, and the generated tests. The three
metrics (verification gap rate, confirmation rate, verified-fix rate) are exported
per session as JSON and CSV and aggregated across sessions, count-weighted, with
bootstrap 95% confidence intervals. Each run also writes a provenance manifest
capturing the commit hash, branch and dirty-tree flag, package version,
Python/platform, and a dataset fingerprint, so any reported number traces back to
exact conditions. The runner is resumable and parallel, and writes a live,
per-worker log. This is the evidence pipeline that Chapter 5 reports from.

### 4.6 Availability

QALLM is open source; the commit history records its development, and the web
interface provides an inspection surface for any run, live or historical.

## 5. Evaluation

Purpose: answer the research questions with the metrics, honestly.

### 5.1 Setup

Datasets are used in two tiers. The lab dataset (four hand-built files with a
documented answer key) is the instrument: because its defects are known, it
establishes that QALLM's verdict is correct before any claim is made on real
code. The headline corpus is real research notebooks (the ENVRI corpus, and for
scale Li's notebook dataset of roughly 2,800 notebooks). [State the exact ENVRI
slice and the Li subset used.]

Models: [which, and why; the project default is FedLLM]. Quality profile(s):
[which; implementation-stage default]. Budget caps: [values]. The oracle is the
correctness oracle at single-sample generation, the calibrated setting
(Section 3.3 and the calibration result below); consensus by union was
investigated and set aside (Section 5.5).

Procedure: calibration first, then the headline. For each unit, the pipeline is
run, the per-session metrics are recorded, and results are aggregated
count-weighted with bootstrap 95% confidence intervals. Every run is
provenance-stamped. The exact commands, environment, and reporting checklist are
in the reproducible experiment protocol (docs/experiments/protocol.md) and the
experiment plan (docs/thesis/experiment-plan.md); this section reports the
results of following them.

Calibration result (instrument validation): on the lab set the correctness
oracle recovers all five seeded reliability defects (5/5), reports zero
execution-only bugs on the clean control and on the complex-but-correct file
beyond at most one false positive on a deliberately under-specified function, and
flags zero execution-only bugs on the security file (whose findings are handled
under RQ2). This is the evidence that the measuring instrument is sound, and it
is reported before the headline so the headline can be trusted.

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

Construct validity. Confirmation is corroboration by demonstration, not a proof
of per-line causation: a finding is confirmed when a generated test reproduces
the behaviour it predicts, which establishes the behaviour is real, not that the
flagged line is its sole cause. What can be confirmed is bounded by the quality
of the generated tests, and refutation depends on the generator finding a
triggering input. Two design choices mitigate this. First, the incoherent-oracle
filter removes tests whose oracle is evaluated at a different input than the call
under test, so a confirmed defect is not an artefact of an unsound test, and the
number of tests dropped this way is reported as a generated-test-quality measure.
Second, the mutation-based oracle confidence (Section 3.9) gives each finding a
confidence grounded in the oracle's demonstrated power to detect injected faults,
so the gap rate can be reported restricted to high-confidence findings.

A related construct point is the asymmetry between defect classes. Execution
adjudicates reliability (wrong-value) defects strongly, because a correctness
test reproduces the defect directly. Security findings are weaker: demonstrating
that an `eval` or shell call is genuinely exploitable, safely and observably,
under the sandbox is hard, so security findings frequently land inconclusive
rather than confirmed. This is reported honestly rather than forced to a number;
it shows QALLM is conservative exactly where execution-based confirmation is
least reliable.

Internal validity. Model nondeterminism could move the numbers; provenance
stamping (commit, model, environment, dataset fingerprint) and the
single-sample calibrated setting make a run reproducible and the conditions
explicit. Consensus by union was investigated and set aside: because samples test
different inputs, votes are never cast and union accumulates stray assertions
that hurt clean code, so single-sample is the principled choice, not a shortcut.
Budget caps can truncate repair rounds, which can only reduce the verified-fix
rate, not inflate it. The ERROR and discarded-test exclusions are conservative:
they remove cases that cannot be soundly judged, which tightens rather than
inflates the gap denominators.

A limitation of the confidence measure itself: a trivially simple function with
almost no mutable structure yields no viable mutant and so scores "unknown"
rather than high or low. This is reported as unknown rather than hidden; it
reflects that an oracle cannot be stress-tested when there is nothing to mutate,
and it does not affect functions with ordinary structure.

External validity. The findings are bounded by the representativeness of the
notebook corpus, the choice of model, and the focus on Python. The calibration-
first protocol and a scale run on a larger corpus address representativeness in
part; cross-model generality is named as future work.

Conclusion validity. Rates are aggregated count-weighted, so larger units weigh
proportionally, and are reported with bootstrap 95% confidence intervals so the
sample size is reflected in the stated uncertainty.

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
- **Mutation score** (oracle confidence) = killed / (killed + survived), the
  fraction of viable injected mutants of a function that its generated test
  suite catches. Mutants that error on every test are not viable and excluded.
- **Confidence label** maps the mutation score: high for score >= 0.8, medium
  for 0.5 <= score < 0.8, low for score < 0.5, and unknown when no viable
  mutant can be produced (a function with no mutable structure).

All metrics are produced per session and aggregated count-weighted across
sessions by the QALLM metrics export, with bootstrap 95% confidence intervals
on the rates, so every number in Chapter 5 is reproducible from the persisted
run artefacts and its provenance manifest.
