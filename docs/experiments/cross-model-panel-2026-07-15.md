# Cross-model panel: four generators, one defect set (2026-07-15)

Extends the two-model record (`cross-model-2026-07-14.md`) to a four-model
panel on the byte-identical 40-notebook forest sample (all manifests pin
paths_sha256 9377906801fb...2d92; zero errored sessions in any arm; arms
span three behaviourally inert commits: dead-code sweep, detection-variable
rename, docs).

## Panel

| generator | fv | gaps | rate | verified fixes |
|---|---|---|---|---|
| fedllm gpt-oss-120b (headline) | 73 | 12 | 16.4% | 10/13 |
| openai gpt-5-mini | 76 | 12 | 15.8% | 12/13 |
| openai gpt-5.4-mini | 64 | 12 | 18.8% | 4/13 |
| openai gpt-5.6-luna | 67 | 10 | 14.9% | 4/10 |

## Agreement structure

Three generators flag the identical twelve functions (pairwise function
Jaccard 1.0). Luna flags ten of the twelve and nothing else: a strict
subset. Across the whole panel no generator produced any finding outside
the twelve; disagreement is monotone, never contradictory. Panel
intersection 10, union 12.

## Reading

Which defects exist is, on this sample, a property of the code under test:
four independently generated test suites, verifying different function
sets (64 to 76), converge on one defect set. What the model governs is
downstream: verified-fix outcomes range from 4/13 to 12/13 on the same
defects, so generator choice decides evidence strength and repair quality,
not existence. Scope: one seeded sample of 40; the consistency may partly
reflect that these twelve are robustly discoverable failures. Feeds the
thesis Model paragraph (sec:generality), the external-validity threat, and
the paper.
