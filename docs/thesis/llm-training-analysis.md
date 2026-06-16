# Training an LLM for QALLM: what it would take, value, and how

An honest analysis of moving from "iterative prompting with quantitative
feedback over an external LLM API" to actually training a model. Written so the
decision is informed, and with a clear recommendation up front.

## Recommendation up front

Do not train a model for the thesis. The current framing (iterative prompting
with feedback, no training) is a deliberate scope decision that addresses the
coordinator's earlier concern, and the thesis's contributions do not depend on
training. Training is a strong, well-defined future-work direction, and naming it
precisely (as below) strengthens the future-work section. The rest of this
document is the basis for that recommendation and the plan if it is ever pursued.

## What "training" could mean here (three rungs, increasing cost)

It is important to separate three different things often lumped as "training",
because they differ by an order of magnitude in cost and risk.

### Rung 1: supervised fine-tuning (SFT) on QALLM's own traces
Collect the (prompt, accepted output) pairs QALLM already produces, the test
suites that scored high confidence, the repairs the judge accepted, and
fine-tune a smaller open model to imitate them. This is the cheapest rung and
the most realistic.

### Rung 2: preference optimisation (DPO/ORPO) on judged pairs
QALLM's judge already produces accept/reject decisions and the mutation scorer
produces high/low confidence. Those are preference labels. A method like DPO or
ORPO learns from (preferred, rejected) pairs without a reward model. This is the
natural fit because QALLM is already a preference-generating machine.

### Rung 3: reinforcement learning with QALLM as the reward (RLAIF/RLVR)
Use QALLM's execution-based verdict as a programmatic reward signal and optimise
the model with PPO or GRPO. This is "reinforcement learning with verifiable
rewards": the reward is not a learned approximation, it is the actual mutation
score / verified-fix outcome. Conceptually elegant and the most powerful, also
the most expensive and least stable.

Note the terminology trap: the thesis is careful to say the current loop is NOT
RL. Rung 3 is the only one that would make "RL" literally true. If training is
ever pursued, the framing must be updated precisely, because conflating the two
is exactly the scope concern the project worked to avoid.

## What has to happen (prerequisites, common to all rungs)

1. **A training dataset from QALLM's own runs.** This is the asset QALLM
   uniquely has: execution-grounded labels. Each example is a function plus a
   generated artefact (test or repair) plus a verdict (high-confidence /
   accepted / verified-fixed). The mutation confidence and the verified-fix
   outcome make the labels trustworthy, which is the whole point: most code-LLM
   training data has noisy labels; QALLM's are execution-checked. Need on the
   order of thousands to tens of thousands of clean examples, which is why the
   full-scale corpus (Li's ~2,800 notebooks, expanded) matters.
2. **A base model and compute.** An open model in the 1B to 8B range for SFT/DPO
   (trainable on a single high-memory GPU or a small node); Rung 3 needs more
   (a rollout loop calling the model many times per step, plus the QALLM reward,
   so it is GPU-hours-heavy and engineering-heavy).
3. **A held-out evaluation.** The lab set and a held-out notebook slice, scored
   with the existing metrics, so "the trained model is better" is itself an
   execution-based, falsifiable claim, not a vibe.
4. **A training stack.** TRL or Axolotl for SFT/DPO; TRL or a GRPO implementation
   for Rung 3. QALLM would need to expose its reward as a callable for Rung 3.

## Anticipated added value

- **Cost and latency.** A small fine-tuned model that matches the API model on
  QALLM's narrow task (generate a correctness oracle; propose a repair) would
  cut per-run cost and latency dramatically, making large corpora and frequent
  re-runs cheap. This is the most concrete, most likely-to-materialise benefit.
- **Specialisation.** The task is narrow (sound, sensitive oracles; minimal
  behaviour-preserving repairs). A specialised small model can match or beat a
  general large model on a narrow task, which is a clean, publishable result if
  it holds.
- **A virtuous loop (Rung 3).** If the execution-based reward genuinely improves
  the model, QALLM becomes a system that both measures and improves
  AI-generated-code quality, a stronger story. But this is the least certain
  benefit and the most expensive to establish.
- **It would make "RL" literally true**, turning a framing the thesis currently
  avoids into a genuine contribution, if (and only if) Rung 3 is done properly.

Honest counterweight: the thesis's value is the verification gap and the
confidence check; none of it needs a trained model. Training risks trading a
finished, defensible contribution for an open-ended research project.

## How to implement (a staged, low-regret plan)

If pursued (post-thesis), do it in the order of the rungs, stopping when the
value plateaus:

1. **Harvest labels (no training yet).** Add a small exporter that turns
   persisted run artefacts into a training set: (function, generated artefact,
   verdict, confidence). This is useful on its own (a dataset of
   execution-labelled code-LLM examples is a contribution) and is the
   prerequisite for everything else. Low risk, high reuse.
2. **SFT a small model (Rung 1)** on the high-confidence subset; evaluate on the
   held-out set with QALLM's metrics. If it matches the API model at a fraction
   of the cost, that alone is a result.
3. **DPO on judged pairs (Rung 2)** using accept/reject and high/low confidence
   as preferences. Compare to SFT on the same held-out set.
4. **Only if 2 and 3 show headroom, attempt RLVR (Rung 3)** with QALLM's reward,
   treating sandbox/reward-hacking and training stability as the gating risks.

Each step is independently evaluable with the metrics QALLM already has, so the
programme is de-risked: it produces a usable result at every rung and can stop
early.

## Risks

- **Scope and timeline.** Training is a separate research project; pulling it
  into the thesis would jeopardise the finished contributions. (Dominant risk
  now.)
- **Reward hacking (Rung 3).** A model optimised against QALLM's reward may learn
  to produce artefacts that game the metric (e.g. tests that trivially pass)
  rather than genuinely better ones. The mutation-confidence check is a partial
  guard, but this needs careful held-out evaluation.
- **Label bias.** Training on QALLM's own accepted outputs risks amplifying
  QALLM's current preferences, including its blind spots. A held-out,
  independently-labelled evaluation is essential.
- **Compute and reproducibility.** Rung 3 especially is compute-heavy and harder
  to reproduce; provenance discipline would have to extend to training runs.

## One-line summary

Training is a credible, valuable future direction, best entered through label
harvesting and SFT/DPO before any RL, but it is out of scope for the thesis,
whose contributions are complete without it; name it precisely as future work and
keep the current loop framed as iterative prompting with feedback.
