# Experiment catalog for QALLM

Beyond the core E0 to E4 in the experiment plan, this catalogs additional
experiments worth running, each with what it answers, the command or method, and
whether it is thesis-scope or future work. Ordered roughly by value-per-effort.

The core experiments (recap, see experiment-plan.md): E0 lab calibration,
E1 RQ1 headline (ENVRI), E2/E3 RQ2/RQ3 (--confirm), E4 scale (Li corpus).

## Now-cheap, thesis-scope

### EX1. Notebook (.ipynb) vs script (.py) gap
Run the same pipeline over the .py files in the corpus and compare the gap rate
to the .ipynb result. Answers whether the verification gap is a property of
notebook code specifically or of AI-generated Python generally. Notebooks are the
thesis's framing, so showing the gap also exists (or differs) in scripts is a
clean external-validity point.
```
python scripts/run_gap_experiment.py \
    --dataset datasets/envri_forest --output runs/ex1_py \
    --pattern "*.py" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 \
    --workers 4 --mutation-confidence
```
Effort: low (one run, change --pattern). Value: high.

### EX2. Crash oracle vs correctness oracle (ablation)
The same dataset run twice, once with --oracle crash, once with correctness.
Quantifies how much of the gap the correctness oracle adds over crash-only, which
makes the methodology's oracle choice empirical instead of asserted.
```
python scripts/run_gap_experiment.py --dataset datasets/lab \
    --output runs/ex2_crash --pattern "*.py" --oracle crash \
    --llm fedllm --rounds 5 --samples 1 --workers 4
# correctness arm = the E0 calibration run
```
Effort: low. Value: high (a citable ablation).

### EX3. Sensitivity to repair rounds
Run a sampled slice at rounds in {1, 3, 5} and plot gap and verified-fix rate
against the round budget. Shows how much of the gap is reachable and where the
repair loop plateaus.
```
for R in 1 3 5; do
  python scripts/run_gap_experiment.py --dataset datasets/envri_forest \
    --output runs/ex3_rounds_$R --pattern "*.ipynb" --rounds $R \
    --oracle correctness --samples 1 --workers 4 \
    --sample 80 --sample-seed 42 --sample-stratify
done
```
Effort: low-medium (three sampled runs). Value: medium.

### EX4. Confidence-stratified gap (A1) and per-dimension gap (A2)
Not separate runs, these are reporting cuts over E1's output: the gap rate within
each confidence band, and the gap rate per EVERSE dimension. Both strengthen the
headline and showcase contributions 2 and 3. Produced by analysing the E1
aggregate and per-session rows.
Effort: low (analysis). Value: high.

## Useful with the new sampling support

### EX5. Fast representative pilot while the full run continues
Use --sample to get a stable signal in a fraction of the time, then compare the
sampled gap rate to the full run's once it finishes (a check that the sample is
representative).
```
python scripts/run_gap_experiment.py --dataset datasets/envri_forest \
    --output runs/ex5_pilot --pattern "*.ipynb" \
    --llm fedllm --rounds 5 --oracle correctness --samples 1 --workers 4 \
    --mutation-confidence --sample 150 --sample-seed 42 --sample-stratify
```
Effort: low. Value: high (de-risks the timeline; gives a number now).

### EX6. Gap by notebook size / domain
Using the stratified sample's size bands (and, if available, project/domain
labels), report whether the gap concentrates in larger or smaller notebooks, or
in particular research domains. Answers "where does AI-generated code go wrong
most". Effort: low-medium (analysis over E1 plus size metadata). Value: medium.

## Future work (named in the thesis, not run now)

### EX7. Cross-model comparison
Repeat E1 across models (gpt-4o-mini, gpt-5-mini, gemma3:4b, FedLLM) and compare
gap rate and confidence distribution. Answers whether the gap is a property of
AI-generated code in general or of one model. Effort: medium (more runs;
provenance already records the model). Value: high for generality. A strong
candidate if time allows; otherwise future work.

### EX8. Property and metamorphic oracles
Implement the property and metamorphic oracle types (already named in the oracle
interface) and measure the additional defect classes they catch on numeric and
scientific code. Effort: medium. Value: high for the research-code domain.

### EX9. Fixed-input voting (real consensus)
Propose inputs once, vote on expected output per input across K samples, and
measure precision against single-sample on ambiguous specs. The real fix for
consensus. Effort: medium. Value: high.

### EX10. Safe security confirmation
The narrow eval/shell exploit-confirmation work (see
security-confirmation-scope.md). Turns inconclusive security findings into
confirmed ones. Effort: medium, risk high (sandbox isolation). Future work.

## Recommendation

For the thesis: EX1 (.py vs .ipynb), EX2 (oracle ablation), and EX4 (the
reporting cuts) are cheap and each strengthens the story; EX5 gives a number now
while E1 runs. EX3 and EX6 if time allows. EX7 to EX10 are future work and the
cross-model one (EX7) is the most compelling of those to mention. Do not start a
future-work experiment before the core E1 to E3 and the write-up are done.
