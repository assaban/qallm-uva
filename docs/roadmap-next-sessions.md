# Agreed roadmap: the next sessions

This is the prioritised plan we agreed to carry forward. It pulls together
threads from the strategy doc (`surpassing-static-analysers.md`), the
diagnostics doc (`run-mechanics-and-diagnostics.md`), and the ideas doc
(`ideas-research-developer-kit.md`) into one sequence. Backend work is in
scope; nothing here is UI-only unless noted.

The ordering is deliberate: each step is independently valuable and ships
on its own, but each also unlocks the next.

## 1. AST-validate generated tests before running them

**Why first.** The `domain.py` run showed every `dangerous` test ERROR-ing
because the model generated tests referencing a `fixed_obj` fixture it
never defined. Those tests never executed, so they produced no verification
signal and polluted the picture. Validating generated tests for undefined
names and fixtures before running, then repairing or discarding the
offenders, directly raises verification signal, especially on smaller local
models. It is also the prerequisite for step 3: you cannot claim a static
finding is confirmed-by-execution with a test that never ran.

**Scope (backend).** An AST pass over each generated test module that flags
references to names/fixtures not defined or imported in the module; a
policy to either drop the offending test or feed the problem back to the
generator for a corrected version; and a count of discarded/invalid tests
surfaced in the round summary so the effect is measurable.

## 2. Static-vs-execution diff view / gap dashboard

**Why second.** Once tests reliably run, make the core claim visible: a
view that puts what the static tools reported next to what execution
proved, with the verification gap (defects execution found that static
analysis missed) front and centre. Mostly UI over data QALLM already has,
plus a small backend aggregation for the gap and confirmation counts.

**Scope.** Backend: per-run aggregation of static findings vs
execution-found defects, and the confirmation/gap counts. Frontend: the
side-by-side and the headline gap number.

## 3. Confirm/refute static findings

**Why third.** The capability that most directly demonstrates QALLM's
advantage and uses the SonarQube integration now working. For each static
finding, attempt a reproducing test; label it confirmed (with the
reproduction), unconfirmed (likely false positive, ranked down), and report
the confirmation rate. Depends on step 1 (tests must run) and step 2 (the
evidence model and aggregation).

**Scope (backend-heavy).** Feed static findings to the generator as test
targets; a unified evidence model where each finding carries its source
tool, execution-confirmation status, reproducing test, and repair outcome;
the confirmation-rate metric.

## Sequencing notes

- 1 is a clean, self-contained backend improvement and the right next
  session.
- 2 and 3 share the evidence-model groundwork; doing 2 first gives a
  visible win and builds the aggregation 3 needs.
- The quality loop (`docs/quality-loop-design.md`, QLOOP-01..04) remains a
  parallel track; QLOOP-01 (the harness) can be built whenever, and the
  confirmation/gap metrics from steps 2 and 3 are natural inputs to it.

## Borrowing from SonarQube and others

Throughout, we lift workflow, UI, and configuration conventions from
SonarQube (the standard for code-quality tooling) where they fit: the
findings-list and severity model, the project/quality-gate framing, the
PR-comment integration pattern. QALLM is not competing with these tools; it
sits on top of them and fills the gap they structurally cannot reach
(execution-based evidence). Adopting their proven UX is free polish toward
that end.
