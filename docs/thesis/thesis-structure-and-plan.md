# QALLM thesis structure and writing plan

A companion to `thesis-draft-scaffold.md`. The scaffold holds the chapter
skeleton; this document adds the contribution framing, the sections that matured
since the scaffold was written, a per-chapter content checklist, and a writing
status tracker, so the write-up is a fill-in exercise, not a blank page.

## Contribution framing (decide and hold this)

The single most important framing decision: one contribution or three. The
recommendation, given where the work landed, is **three explicit
contributions**, because each is independently defensible and together they tell
a complete story:

1. **The verification-gap method**: treating static findings as hypotheses and
   using execution as the adjudicator, with a formal gap rate. This is the
   conceptual core.
2. **The EVERSE-aligned judge**: a lexicographic accept/reject over
   research-software quality dimensions, which turns "is this repair better?"
   into a principled, dimension-ordered decision.
3. **Mutation-based oracle confidence**: a positive soundness check that gives
   each gap finding a confidence grounded in the oracle's demonstrated power to
   detect injected faults. This is the answer to "how do you know the bugs are
   real?", and it is novel in the LLM-as-oracle setting.

The RL-style loop (iterative prompting with quantitative feedback over an
external LLM API, not model training) is the mechanism that runs through all
three, not a separate contribution. State this precisely and early; it pre-empts
the scope concern.

## Chapters and what each must contain

### 1. Introduction
- The problem: AI-generated research code, static analysis gives false
  confidence. Motivate with the headline (a large fraction of clean-looking
  functions carry runtime defects).
- The three contributions, stated explicitly.
- The RL-as-iterative-prompting clarification.
- Thesis outline.

### 2. Background and related work
- Static analysis and its blind spot to runtime behaviour.
- LLM-based test generation and repair; where prior work stops (no execution
  adjudication, no confidence on the verdict).
- EVERSE / research-software quality models; the EOSC lifecycle.
- Mutation testing as suite-adequacy measurement (the basis for contribution 3).
- Position QALLM against the proposal's literature (Li, Volentir et al.,
  Islam and Zhao's agentic workflow line, Schvarcbacher's TAR structure).

### 3. Method  (extend the scaffold with the two sections below)
The scaffold covers 3.1 to 3.7. Add:

- **3.8 The judge and EVERSE quality model.** The lexicographic ordering
  (Security, Reliability, Maintainability, Reproducibility, FAIRness), why that
  order, and how a finding's dimension routes both the gate and the repair. This
  is contribution 2 and is currently underrepresented in the scaffold.
- **3.9 Oracle confidence via mutation testing.** The mutant operators
  (AOR/ROR/COI/CRP/RVR, including %, //, ** for numeric code), the kill / survive
  / not-viable classification, the mutation score, and the confidence label. The
  strong-vs-weak worked example (exact-value oracle 1.0 high vs isinstance-only
  0.25 low). This is contribution 3. Source:
  `docs/concepts/oracle-confidence-mutation-testing.md`.

### 4. Implementation
- Architecture (the staged pipeline diagram from the status update).
- The analyser registry and normalisation to a common finding model.
- The sandboxed executor and the FROZEN+GROW accumulation policy.
- The resumable, parallel runner; provenance manifest; retention modes.
- The web UI as the inspection surface (see the UI section below).

### 5. Evaluation  (align to the experiment plan)
- 5.1 Setup: datasets (lab + ENVRI + Li), models, the calibration-first
  protocol, provenance.
- 5.2 Instrument validation (E0): the calibration table; 5/5 reliability recall;
  the documented residual false positives. This earns trust before any headline.
- 5.3 RQ1 (E1): the gap rate with 95% CI, reported twice (all vs
  high-confidence), with the confidence distribution.
- 5.4 RQ2 (E2): confirmation vs refutation; interpret a high refute rate.
- 5.5 RQ3 (E3): verified-fix rate, per dimension where the sample allows.
- 5.6 Scale (E4): the Li corpus, stability of the gap.
- 5.7 Threats to validity: oracle variance / single-sample choice; generated-
  test quality (incoherent-oracle count); confirmation as corroboration not
  proof; the ambiguous-spec false positives; LLM nondeterminism (mitigated by
  provenance and the confidence check).

### 6. Discussion
- What the gap size means for trusting AI-generated research code.
- Where execution adjudication helps most (reliability) and least (style).
- The confidence check as a template for trusting LLM-as-judge systems.

### 7. Conclusion and future work
- Restate the three contributions and the evidence for each.
- Future: fixed-input voting for consensus; broader oracle types; the demo and
  dissemination surface; larger corpora.

### Appendix
- Authoritative metric definitions (gap rate, confirmation rate, verified-fix
  rate, mutation score, confidence label).
- The lab answer key.
- Reproduction: commands (the experiment plan), and how to read a manifest.

## Writing status tracker

Legend: [ ] not started, [~] drafted, [x] solid.

| Section | Status | Blocking input |
| --- | --- | --- |
| 1 Introduction | [~] | headline number from E1 |
| 2 Background/related | [~] | none (can write now) |
| 3.1 to 3.7 Method | [~] | none (scaffold exists) |
| 3.8 Judge/EVERSE | [~] | drafted into the scaffold |
| 3.9 Oracle confidence | [~] | drafted into the scaffold |
| 4 Implementation | [~] | none |
| 5.1 Setup | [ ] | none |
| 5.2 Calibration (E0) | [ ] | E0 run |
| 5.3 RQ1 (E1) | [ ] | E1 run |
| 5.4 RQ2 (E2) | [ ] | E2 run (confirm path verified) |
| 5.5 RQ3 (E3) | [ ] | E3 run |
| 5.6 Scale (E4) | [ ] | Li dataset |
| 5.7 Threats | [~] | none (mostly writable now) |
| 6 Discussion | [ ] | results |
| 7 Conclusion | [ ] | results |
| Appendix | [~] | none |

## What can be written now, before the runs

Most of the thesis does not depend on the headline numbers and should be drafted
in parallel with the experiments: all of Chapter 2, Method 3.1 to 3.9 (the code
and concept docs are the source), Chapter 4, the Setup and Threats sections, and
the Appendix definitions. Only the results subsections (5.2 to 5.6) and the
discussion need the runs. Drafting the method and implementation now de-risks the
schedule: when E1 lands, only the numbers go in.
