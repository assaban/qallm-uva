# Cross-model replication (2026-07-14)

Playbook run 1, second arm: OpenAI gpt-5-mini on the byte-identical
40-notebook forest sample as the fedllm arm (`runs/x_dom_forest`); both
manifests pin paths_sha256 9377906801fb...2d92. Correctness oracle,
identical configuration; the arms span two commits whose delta is the
dead-code sweep, behaviourally inert for the gap pipeline. Zero errored
sessions in either arm.

## Result

| arm | fv | gaps | rate | verified fixes |
|---|---|---|---|---|
| fedllm gpt-oss-120b | 73 | 12 | 16.4% | 10/13 |
| openai gpt-5-mini | 76 | 12 | 15.8% | 12/13 |

Paired rate difference (per-notebook bootstrap): +0.6pp, 95% CI
[-0.7, +6.0].

The stronger result is set-level: the two generators flag the identical
six notebooks and, within them, the identical twelve functions (function
Jaccard 1.0), with zero one-sided findings. On this sample the gap is a
property of the code under test, not of the model generating the tests.
Downstream, the generators differ: mutation-confidence tiers and repair
outcomes vary, so model choice affects how well a defect is evidenced and
fixed, not which defects exist.

## Scope

One seeded sample of 40; wide intervals; the set-identity is an observed
outcome on this sample, not a theorem. Feeds sec:generality (Model
paragraph) and the external-validity threat (all three bounds, domain,
form, model, now measured); paper updated to match.
