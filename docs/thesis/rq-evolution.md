# Research-question evolution: from proposal to thesis

A short, defensible account of how the research questions changed between the
proposal and the thesis, and why. This is the kind of change an examiner and the
thesis coordinator will ask about, so it is written to be stated plainly in the
defence and, in condensed form, in the thesis introduction.

## The change

The proposal framed the work around building and evaluating an execution-based
quality-assessment pipeline for AI-generated notebook code, with the empirical
emphasis on whether iterative, feedback-guided test generation outperforms
simpler baselines. The thesis keeps the same artifact and the same core idea
(execution adjudicates static findings) but sharpens the empirical questions into
three precise, measurable ones:

- **RQ1**: To what extent does execution-based assessment reveal defects that
  static analysis of AI-generated notebook code misses? (the verification gap)
- **RQ2**: How reliably can individual static findings be confirmed or refuted
  by automatically generated, executed tests? (confirmation)
- **RQ3**: When a repair is applied, can the fix be verified by execution, and
  how often does a repair that satisfies static analysis fail to fix the
  underlying defect? (verified fixes)

## Why the change is legitimate, not scope drift

Refining research questions during a project is normal and expected; what matters
is that the refinement is principled and that the artifact did not change
underneath it. Here both hold.

1. **The object of study is unchanged.** The proposal and the thesis study the
   same thing: using execution to assess the quality of AI-generated notebook
   code. The RQs were made measurable, not redirected. RQ1 to RQ3 are the
   quantitative form of the proposal's central claim.

2. **The refinement was driven by what turned out to be measurable.** During
   implementation and calibration it became clear that the strongest, most
   defensible result was the size of the verification gap and the soundness of
   the verdicts, not a head-to-head "RL beats baseline" comparison. The three
   RQs name exactly the quantities the pipeline can measure on real artefacts
   (gap rate, confirmation rate, verified-fix rate), each with a clear
   definition and a confidence interval. A measurable question is a better
   question.

3. **It directly addresses the earlier scope concern.** The coordinator's
   concern was about AI-heavy framing and scope. Reframing around the
   verification gap, with the generation loop precisely described as iterative
   prompting with quantitative feedback over an external LLM API (not model
   training), narrows and grounds the scope rather than expanding it. The thesis
   claims are about a measurable property of AI-generated code, not about a novel
   learning method.

4. **The contribution is sharper.** The three-RQ framing yields three concrete
   contributions (the verification-gap method, the EVERSE-aligned judge, and the
   mutation-based oracle confidence) that are each independently defensible,
   which is stronger than a single comparative result.

## How to state it (for the introduction and the defence)

One or two sentences suffice in the introduction:

> The research questions refine those of the proposal. The object of study,
> execution-based assessment of AI-generated notebook code, is unchanged; the
> questions are stated in the measurable form the implementation made possible,
> namely the size of the verification gap (RQ1), the reliability of confirming
> or refuting individual findings (RQ2), and the verifiability of repairs (RQ3).

For the defence, the three points above (same object, made measurable, narrows
scope, sharper contribution) are the answer. The key line: the artifact did not
change; the questions were made precise.

## Recommended action

Add the one-to-two-sentence note above to the thesis introduction (right after
the RQs), and keep this document as the longer justification to draw on if the
coordinator or an examiner presses. If the proposal's exact RQ wording is to
hand, include a one-line before/after mapping in an appendix; it pre-empts the
question entirely.
