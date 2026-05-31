# Learning from SonarQube and surpassing it: a design

The goal is not to out-rule SonarQube. Sonar has hundreds of person-years
of static rules; QALLM will never beat it at pattern-matching source code,
and trying to is a losing game. QALLM's advantage is the thing static
analysers structurally cannot do: it *executes* the code and *closes a
loop with an LLM*. So "surpassing" the static tools means treating their
findings as one input signal, then doing what they cannot: confirm or
refute each finding by running the code, and repair with feedback until
the evidence says the code is actually better.

This document lays out how to get there, in three moves: consume the
static tools as evidence, verify and out-perform them by execution, and
turn fix quality and UX into the reasons people choose QALLM. It is a
design to react to, not built yet.

## The core reframe: static findings are hypotheses, execution is the judge

A SonarQube or Bandit finding is a *hypothesis*: "this line may be a bug."
Static tools can only ever assert the hypothesis; they cannot test it.
QALLM can. For every static finding, QALLM can attempt to generate a test
that *demonstrates* the finding is a real, triggerable defect.

That single idea reorganises everything:

* A finding QALLM can reproduce with a failing test is **confirmed**: real,
  with a concrete reproduction. This is worth far more than Sonar's
  assertion alone.
* A finding QALLM cannot reproduce after honest effort is **unconfirmed**:
  possibly a false positive, or untriggerable in practice. Sonar floods
  users with these; QALLM can rank them down.
* A failure QALLM finds by execution that *no* static tool flagged is the
  **verification gap** made concrete: the thesis claim, per finding.

So the headline capability is a **confirmation rate** and a **gap rate**
per run: of the static findings, how many did execution confirm; and how
many real defects did execution find that static analysis missed. Those
two numbers are the case for QALLM over Sonar, in the product itself.

## Move 1: consume the static tools as evidence (not as competitors)

Right now QALLM runs Bandit, Radon, and (optionally) SonarQube and lists
their findings. The next step is to *use* those findings as signal:

* **Findings as test targets.** Feed each static finding to the
  test-generation step as a hypothesis to try to trigger: "Sonar says line
  42 may dereference None; write a test that makes it happen." This focuses
  generation on the suspect code instead of the whole surface, which raises
  bug-detection per token spent.
* **Findings as repair priors.** Feed confirmed findings to the repair
  prompt as known-good context: "the following defects are confirmed by
  failing tests; fix these specifically." A repair guided by a reproduced
  failure is far more likely to be correct than one guided by a static
  warning alone.
* **A unified evidence model.** Each finding carries where it came from
  (which tool, or execution), whether execution confirmed it, the
  reproducing test if any, and the repair outcome. This is the data
  structure the whole product hangs off.

## Move 2: out-perform the static tools by execution

This is where QALLM does what Sonar cannot.

* **Confirm/refute every static finding.** For each Sonar/Bandit finding,
  attempt a reproducing test. Report the confirmation rate. A tool that
  tells you "of Sonar's 40 findings, 12 are confirmed-reproducible, 28 we
  could not trigger" is more useful than either tool alone, because it
  triages the noise static analysers are notorious for.
* **Find what they missed.** Keep generating tests beyond the static
  findings (crash, property, metamorphic oracles) and surface every failure
  no static tool predicted. This is the gap, and it is the differentiator.
* **Prove the fix, do not assert it.** Sonar's AI CodeFix proposes a change
  and tells you it looks right. QALLM proposes a change, *re-runs the
  tests*, and tells you the previously-failing test now passes and nothing
  else broke. A verified fix beats a suggested fix every time, and it is
  the single clearest reason to choose QALLM.
* **Mutation-tested confidence.** When QALLM reports "no bugs found,"
  back it with a kill rate: mutate the code, confirm the generated tests
  catch the mutants. This turns a weak "we found nothing" into a
  quantified "the tests are sensitive enough to trust this verdict," which
  is exactly the critique any test-generation tool must answer.

## Move 3: make fix quality and UX the reason people stay

A tool people *choose* has to be dramatically better to use, not just
better on a metric. The following are aimed squarely at that.

### Fix quality

* **Minimal, reviewable diffs.** A repair should be the smallest change
  that makes the failing test pass, not a rewrite. Constrain the repair
  prompt to minimal diffs and reject repairs that change more than the
  defect requires. Developers trust a three-line fix; they distrust a
  fifty-line rewrite.
* **Never regress.** Every repair is gated on the full test set, not just
  the one failing test: the fix must turn the target test green *and* keep
  every previously-passing test green. The judge already does accept/abandon;
  make "no regression" an explicit, surfaced gate.
* **Explain the fix.** For each accepted repair, a one or two sentence
  rationale tied to the reproducing test: "the function returned the
  product as 0 because the accumulator started at 0 instead of 1; the test
  test_normal_positive_integers now passes." This is what turns a black-box
  patch into something a researcher will cite and a developer will merge.
* **Minimised counterexample.** Shrink each failing input to the smallest
  that still fails. A one-line minimal reproduction is the most useful
  artefact QALLM can hand a developer, and static tools have no equivalent.

### User experience

* **The gap dashboard.** Front and centre: confirmed findings, unconfirmed
  (likely-false-positive) findings, and execution-found defects the static
  tools missed, with the reproducing test one click away. This single view
  is the product's argument for itself.
* **Side-by-side with Sonar.** A column for "what Sonar said" next to "what
  execution proved." Where they agree, confidence. Where execution found
  more, that is the value. Where Sonar flagged and execution could not
  trigger, that is noise QALLM saved the user from chasing.
* **Trust signals.** Show the cost before a run, the mutation-kill-rate
  behind a clean verdict, and the no-regression gate on every fix. People
  adopt tools they trust; trust comes from the tool showing its work.
* **Fast, incremental, in-workflow.** Run on a diff in CI and post the
  confirmed defects plus minimal reproductions as a PR comment; run on a
  cell from the notebook. The contrast with Sonar's static PR comments is
  the pitch: QALLM's comments are execution-verified.

## What this looks like as a metric story (for the thesis and the user)

Per run, QALLM can report four numbers that no static tool can produce
together:

1. **Static-finding confirmation rate**: of the static findings, the
   fraction execution reproduced. (Triage value.)
2. **Verification-gap rate**: defects execution found that no static tool
   flagged, over total defects. (The thesis claim.)
3. **Verified-fix rate**: repairs that turned a reproduced failure green
   with no regression. (Fix quality.)
4. **Verdict confidence**: mutation kill rate behind a clean result. (Trust.)

These four, shown in the UI and exported for a paper, are simultaneously
the research contribution and the reason a developer would pick QALLM over
running Sonar alone.

## Suggested build order

1. **Unified evidence model**: every finding carries source tool, execution
   confirmation, reproducing test, repair outcome. The prerequisite.
2. **Confirm/refute static findings**: feed static findings as test
   targets; compute and surface the confirmation rate. Highest-value first
   step, directly uses the SonarQube integration we just got working.
3. **Verified-fix gating + explanations + minimal diffs**: make fix quality
   visible and trustworthy.
4. **The gap dashboard and the side-by-side-with-Sonar view**: make the
   advantage legible in the UI.
5. **Mutation-based confidence and minimised counterexamples**: the deeper
   evidence that answers the hardest critiques.

Each step is independently valuable and ships on its own. The through-line:
static analysers guess, QALLM proves, and the product's job is to make that
difference impossible to miss.
