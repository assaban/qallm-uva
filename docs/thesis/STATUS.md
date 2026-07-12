# Project status

The single point-in-time status document, overwritten in place as the
project moves; forward-looking planning lives in `roadmap.md`. Superseded
dated snapshots are in `archive/`.

## One-paragraph summary (2026-07-12)

The empirical phase is complete. Both headline experiments are finished on
pinned runs: E2 (full ENVRI forest corpus, `runs/e2_final`) and the
HumanEvalFix pair (crash and correctness arms, completing the oracle
ablation). The thesis carries the final numbers throughout, compiles clean
(58 pages, zero placeholders, zero undefined references), and is a
submission candidate. The defence deck and committee handout exist. The web
UI builds and smoke-tests clean for the demo. What remains is human, not
computational: the second reader's name, the Islam & Zhao citation in
Related Work, the author's own full read, and delivery to the supervisors.

## Headline numbers (authoritative, from committed analysis scripts)

- RQ1: 732/4,298 verified functions, 17.0% (95% CI [14.7%, 19.6%]);
  high-confidence-only 12.4%; excluding the dominant repository 21.6%;
  project-weighted macro 21.2%, median 11.1%, 39/112 projects at zero.
- RQ2: 747 confirmed reliability defects with reproducing tests; 265
  security findings inconclusive by design; 0 refuted; counts, never a rate.
- RQ3: 391/669 conclusive re-tests, 58.4% (95% CI [53.1%, 63.9%]); 278
  not-fixed; 78 fix-inconclusive reported separately.
- Benchmark (164 problems, both oracles): repair doubles under the
  correctness oracle within every strategy (McNemar exact p <= 0.007);
  detection unmoved (p >= 0.29); strategies indistinguishable. See
  `../experiments/heval-correctness-final-2026-07-11.md`.

## In flight

- Nothing computational. Optional pre-defence enrichment, in priority
  order if time allows after the supervisor draft goes out: seeded
  cross-domain pair (playbook run 2), seeded cross-model pair (run 1),
  naive re-prompt repair baseline.

## Remaining before submission

1. Second reader name in the thesis `main.tex` (pending Zhao confirmation).
2. Islam & Zhao citation in Related Work (author has the entry).
3. Author's full read of the compiled PDF.
4. DataNose upload and degree-certificate application (31 August deadline).
