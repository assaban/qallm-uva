# QALLM as a kit for researchers and developers: ideas

This is a wide-ranging set of ideas for turning QALLM from a thesis
artefact into a tool people reach for. It is grounded in what QALLM
already is: an execution-based, quality-model-guided code improvement loop
whose central empirical claim is the verification gap, that static
analysis passes code which still fails at runtime, and that running
generated tests catches what reading the code cannot.

The ideas are organised by the question they answer, not by component, so
each one starts from a real user need. Each is tagged with a rough effort
(S/M/L) and who it serves (researcher / developer / both). Nothing here is
a commitment; it is a menu to prioritise from. None of it is built yet.

A guiding principle runs through all of it: QALLM's distinctive value is
execution-based evidence. Ideas that deepen, surface, or make that
evidence more trustworthy are worth more than ideas that add surface area.

---

## 1. Make the core claim impossible to miss

The verification gap is the reason QALLM exists, yet a new user has to
infer it. Make it the first thing they see and feel.

* **Gap-front-and-centre dashboard** (M, both). A single headline on the
  results and session views: "N functions passed static analysis; M of
  those failed under execution." That ratio is the false-confidence rate,
  the thesis's number. Showing it per session turns every run into
  evidence for the claim.
* **Static-vs-execution diff view** (M, both). Side by side: what Bandit
  and Radon (and SonarQube, when on) reported, versus what the generated
  tests found by running the code. The cases where the right column has
  bugs the left column missed are the product in one screen.
* **"Why static analysis was not enough" explainer per bug** (S,
  researcher). For each execution-found bug, a one-line statement of why no
  static tool could have caught it (it depends on a runtime value, a state
  interaction, a specific input). This is thesis-grade material and also
  teaches developers what they are getting.

## 2. Deepen the evidence (the moat)

These make the execution evidence richer and more trustworthy, which is
where QALLM is differentiated.

* **Minimised failing input** (M, both). When a generated test fails,
  shrink the input to the smallest one that still fails (delta-debugging /
  Hypothesis-style shrinking). A one-line minimal counterexample is far
  more useful than a complex one, and it is exactly the kind of artefact a
  developer pastes into a bug report.
* **Root-cause localisation** (L, both). Combine the failing test, the
  coverage trace, and the source to point at the most suspect line(s)
  (spectrum-based fault localisation: lines executed by failing-but-not-
  passing tests rank highest). "The bug is most likely here" is a large
  step up from "a test failed".
* **Mutation testing as a confidence score** (L, researcher). Run the
  accepted tests against mutated versions of the code; the kill rate tells
  you how much to trust a "no bugs found" verdict. This directly addresses
  the obvious critique of any test-generation tool: absence of failures is
  weak evidence unless the tests are known to be sensitive.
* **Differential testing against the canonical** (M, researcher). Where a
  reference implementation exists (as in HumanEvalFix), run both on the
  same inputs and report divergences. This is a stronger oracle than
  crash-only and is already partly modelled by the metamorphic/property
  oracles.
* **Flaky-test detection** (S, both). Re-run a passing/failing test a few
  times; flag non-determinism. A flaky generated test is noise that
  pollutes the false-confidence number, so detecting it protects the core
  metric.

## 3. Meet developers where they work

QALLM is most useful if it fits an existing workflow rather than asking for
a detour.

* **CI / pre-commit integration** (M, developer). A `qallm check` mode that
  runs the pipeline on changed files and fails CI (or a pre-commit hook)
  when execution finds a regression a static linter would have passed.
  This is the verification gap as a guardrail, the most natural developer
  adoption path.
* **GitHub Action + PR comment** (M, developer). On a pull request, run
  QALLM on the diff and post a comment: bugs found by execution, with the
  minimal failing input and suggested fix. SonarQube's AI CodeFix posts
  static suggestions; QALLM would post execution-verified ones, the direct
  contrast.
* **LSP / editor surfacing** (L, developer). Surface execution-found issues
  inline in the editor, not just in a separate UI. Heavier, but it is where
  developers actually live.
* **Deepen the Jupyter magic** (S, researcher). Build on the existing
  `%%qallm` magic: a `%qallm_watch` that re-runs on cell change, and
  rendering the minimal failing input inline. Notebooks are where research
  software is written; this is high-leverage for the thesis audience.

## 4. Serve the researcher's actual job

Researchers need to produce defensible claims, reproduce results, and
write them up.

* **The quality loop** (L, researcher). Already designed in
  `docs/quality-loop-design.md`: regression-catching plus prompt/strategy
  search over a fixed benchmark. This is the single most valuable research
  feature, because it turns QALLM's own improvement into measured,
  defensible evidence and produces the thesis's trajectory data.
* **Experiment reproducibility bundle** (M, researcher). One click to
  export a run as a self-contained bundle: the exact config, seeds, model
  versions, dataset slice, the per-problem results, and the environment
  (a lock file). A reviewer can re-run it. This is what makes an
  experiment citable rather than anecdotal.
* **Cross-run comparison view** (M, researcher). Pick two runs (or two
  QALLM versions) and see the metric deltas with the pairwise significance
  test already used in the report. This is the manual companion to the
  automated regression mode.
* **Notebook-corpus benchmark** (L, researcher). Beyond HumanEvalFix, run
  against Li's notebook corpus (the research-software distribution the
  thesis targets) so the numbers reflect the real population, not only
  curated single-function bugs. Already noted as QLOOP-04.
* **LaTeX / figure export** (S, researcher). Export the aggregate tables
  and the bug-detection comparison as LaTeX tables and publication-quality
  figures, straight into the thesis. Small effort, disproportionate
  goodwill from the one user who matters most right now.

## 5. Make it trustworthy and safe to run

Adoption depends on people trusting the tool with their code and their
budget.

* **Cost preflight and hard caps** (S, both). Before a run, estimate the
  token/USD cost from the unit count and rounds, and show it. The budget
  caps exist; surfacing the estimate up front prevents surprise bills and
  builds trust.
* **Sandbox hardening transparency** (M, both). Document and surface that
  generated code runs in an isolated subprocess, what it can and cannot
  reach (network, filesystem), and let the user tighten it. Researchers
  running untrusted-ish generated code need to know the blast radius.
* **Deterministic replay** (M, researcher). Persist enough (prompts,
  responses, seeds) to replay a session without calling the LLM again, for
  debugging the pipeline and for cheap re-analysis. The transcript capture
  already exists; this builds on it.
* **Offline-first mode** (M, both). A configuration that runs entirely on
  local models (Ollama) and local analysers, no hosted API, for users who
  cannot send code to a third party. Important for institutional and
  privacy-sensitive users.

## 6. Lower the floor for new users

* **One-command quickstart with a worked example** (S, both). `qallm demo`
  runs the bundled buggy sample end to end and opens the result, so a new
  user sees the verification gap in 60 seconds without configuring
  anything.
* **Guided interpretation** (S, both). On the results view, a short
  plain-language reading of what happened ("3 bugs were found by execution
  that static analysis missed; 2 were repaired; 1 remains"), so a
  non-expert understands the output without learning the vocabulary.
* **Profile chooser guidance** (S, both). When picking a quality profile,
  explain in one line what each measures and when to use it (EVERSE for
  research software, ISO 25010 for general software, FAIR4RS for a
  publication check), so the choice is informed.

## 7. Longer-horizon, higher-risk bets

* **Multi-language support** (L, developer). The pipeline is Python-shaped
  (AST extraction, pytest). A second language (JavaScript/TypeScript with
  its own test runner) would widen the audience substantially, but it is a
  large, structural undertaking.
* **Repair-strategy library** (L, researcher). A catalogue of repair
  prompting strategies (chain-of-thought, test-first, minimal-diff) that
  the research mode of the quality loop can search over, turning QALLM into
  a platform for studying LLM repair, not just a tool that does it one way.
* **Human-in-the-loop repair review** (M, both). Let a user accept,
  reject, or edit a proposed repair before it becomes the next round's
  baseline, with their decision recorded. This makes QALLM a collaborator
  rather than a black box, and the decisions are themselves research data.

---

## Suggested first moves (if I had to choose)

If the goal is maximum usefulness per unit effort, weighted toward the
near-term thesis and a real user base forming around it:

1. **Static-vs-execution diff view + gap-front-and-centre dashboard**
   (section 1). Makes the core claim visible; mostly UI over data QALLM
   already has.
2. **Minimised failing input** (section 2). The single most useful
   per-bug improvement for both audiences, and a strong thesis artefact.
3. **The quality loop** (section 4 / QLOOP issues). The highest-value
   research feature, already designed.
4. **CI / PR-comment integration** (section 3). The most natural developer
   adoption path, and the cleanest head-to-head with SonarQube AI CodeFix.
5. **Reproducibility bundle + LaTeX export** (section 4). Cheap, and aimed
   squarely at the person whose opinion matters most this year.

Everything here keeps faith with the one idea that makes QALLM worth using:
execution is evidence that reading the code is not. The best additions are
the ones that make that evidence richer, more visible, and more trusted.
