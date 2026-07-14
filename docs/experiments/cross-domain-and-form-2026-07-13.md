# Cross-domain and form runs: the 2x2 (2026-07-13)

Playbook runs 2 and 4, completed on commit a431510 (dirty: false), seeded
samples of 40 inputs per arm, correctness oracle, identical configuration.
The .py arms carry the eight MD-010 exclusion globs in their manifests;
samples are pinned by paths_sha256.

## The 2x2 (gap rate, session-resample bootstrap 95% CI)

| | Notebooks (.ipynb) | Plain Python (.py) |
|---|---|---|
| Forest | 12/73 = 16.4% [3.7, 42.9] | 11/73 = 15.1% [3.1, 29.6] |
| Ocean | 16/96 = 16.7% [6.9, 27.6] | 9/160 = 5.6% [0.0, 15.3] |

Full-corpus forest reference: 17.0% [14.7, 19.6]. One errored session
(x_dom_ocean, 1/40); zero elsewhere.

## Contrasts (bootstrap difference CIs)

- Domain (forest minus ocean, notebooks): -0.2pp [-17.3, +27.4]. No evidence
  of a domain effect; both point estimates within half a point of the
  full-corpus headline.
- Form, pooled (ipynb minus py): +8.0pp [-3.8, +20.6]; pooled rates 16.6%
  vs 8.6%. The gap persists in authored plain Python (not an extraction
  artefact); the notebook surcharge is a direction, not a finding, at this
  sample size. Ocean's .py arm is markedly function-dense (160 verified
  functions from 40 files) and cleaner, echoing the engineered-module
  pattern from the full corpus.
- Verified-fix rates in these arms (44% to 77% on 9 to 16 defects) straddle
  the headline 58.4% with intervals too wide for any claim.

## Where it feeds the thesis

sec:generality and tab:generality (Experiments); the external-validity
paragraph (two of three bounds now measured; cross-model remains); the
triage paragraph in Analysis.
