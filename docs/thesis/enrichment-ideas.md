# Enrichment ideas for QALLM

Candidate features and experiments that would strengthen QALLM, each with a
value / effort / risk read, and a clear split between what is worth pulling into
the thesis scope and what belongs in future work. The guiding principle: the
thesis is close to done, so anything thesis-scope must sharpen an existing
contribution, not open a new front.

## Principle for deciding

Pull an idea into thesis scope only if it (a) strengthens an existing
contribution (the gap, the judge, the confidence), (b) is low-risk, and (c) fits
before the write-up closes. Everything else is future work, and a strong
future-work section is itself a thesis asset.

## Tier A: thesis-scope candidates (sharpen what exists)

### A1. Confidence-stratified gap rate as a first-class result
Report the verification gap rate not just twice (all vs high-confidence) but as
a small distribution: gap rate within each confidence band. This turns the
mutation-confidence contribution into a headline figure rather than a footnote.
Value: high (directly strengthens RQ1 and the confidence contribution). Effort:
low (the data already exists in the aggregate; it is a reporting/plotting
choice). Risk: none. **Recommended for the thesis.**

### A2. Per-EVERSE-dimension gap breakdown
Report the gap rate per quality dimension (Reliability vs Security vs ...), since
findings are already dimension-tagged. "The gap is concentrated in Reliability"
is a sharper, more defensible claim than a single blended rate and showcases the
judge/EVERSE contribution. Value: high. Effort: low-medium (group existing
findings by their tag in the aggregate). Risk: low. **Recommended.**

### A3. Ablation: crash oracle vs correctness oracle
A small controlled experiment on the lab set (and a slice of ENVRI) showing the
gap the crash oracle finds vs the correctness oracle. This quantifies why the
correctness oracle matters and makes the methodology chapter's oracle discussion
empirical rather than asserted. Value: high (a clean, citable ablation). Effort:
low (re-run with `--oracle crash` vs `correctness`). Risk: low. **Recommended.**

### A4. Sensitivity of the gap to rounds
Run the headline at rounds in {1, 3, 5} on a slice and show how the gap and the
verified-fix rate move with the repair budget. Cheap insight into how much of the
gap is reachable, and a natural robustness paragraph. Value: medium. Effort: low.
Risk: low. **Optional, nice if time allows.**

## Tier B: strong future-work (named in the thesis, built later)

### B1. Fixed-input voting for consensus
The real fix for consensus: propose inputs once, then have K samples vote on the
expected output per input. This is the way to make voting actually bind (current
union consensus never triggers) and would push precision on ambiguous specs.
Value: high. Effort: medium (a new generation shape). Risk: medium
(re-calibration). Designed already in oracle-variance-and-consensus.md.

### B2. Broader oracle types (property and metamorphic)
The oracle interface already names `property` and `metamorphic`; implementing
them would extend the defect classes QALLM can catch beyond crash and
wrong-value, especially for numeric/scientific code where invariants and
relations are natural. Value: high for the research-code domain. Effort: medium.
Risk: medium (oracle soundness, the same calibration discipline applies).

### B3. Safe, observable security confirmation
The narrow eval/shell exploit-confirmation work scoped in
security-confirmation-scope.md. Turns inconclusive security findings into
confirmed ones. Value: medium. Effort: medium. Risk: high (touches sandbox
isolation). Explicitly future work, with the risk called out.

### B4. Cross-model comparison
Run the headline across models (the pilot used gpt-4o-mini, gpt-5-mini,
gemma3:4b) and report how the gap rate and confidence distribution vary by model.
Speaks to generality: is the verification gap a property of AI-generated code, or
of one model? Value: high for external validity. Effort: medium (more runs,
provenance already captures the model). Risk: low. A strong candidate if the
timeline allows; otherwise future work.

### B5. Confidence-guided repair prioritisation
Use the mutation confidence to order repair effort: fix high-confidence defects
first, since they are the most certainly real. Value: medium (a product feature
more than a thesis result). Effort: medium. Risk: low. Future work.

### B6. Incremental / cached runs
Skip re-verifying functions whose source is unchanged across runs (hash-keyed
cache), so re-running a large corpus after a code change is cheap. Value: medium
(operational). Effort: medium. Risk: low. Future work / engineering.

## Tier C: dissemination (Tier 3 of the roadmap)

### C1. In-app architecture page
A live architecture view in the web UI (the pipeline diagram, clickable to the
relevant docs). Value: high for the demo and the defence. Effort: low-medium.
Risk: none.

### C2. Live metrics page
Once E1 is in, a page that reads the run aggregate and shows the headline gap
rate, the confidence distribution, and the per-dimension breakdown. Value: high
for the demo. Effort: low (the aggregate endpoint exists). Risk: none.

### C3. One-click reproduce
A button that surfaces a run's provenance (commit, model, dataset fingerprint)
and the exact command to reproduce it. Value: medium (reinforces the
reproducibility story to a committee). Effort: low. Risk: none.

## Recommendation

For the thesis, do A1, A2, and A3: they are cheap, low-risk, and each directly
strengthens one of the three contributions (confidence, judge, oracle). A4 if
time allows. For the demo, C1 and C2. Everything in Tier B is genuine future
work; naming it well (especially B1, B2, B4) makes the future-work section
credible and shows the work has a clear forward path. Do not open a Tier B front
before the headline and the write-up are done.
