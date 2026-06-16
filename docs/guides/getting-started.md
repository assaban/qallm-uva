# Getting started with QALLM

A short guide for anyone trying QALLM for the first time: researchers, testers,
and collaborators. No prior knowledge of the tool is needed.

## What QALLM does, in one minute

Static analysers (the tools that flag style, complexity, and security issues)
tell you whether code *looks* right. They never run the code, so they miss
defects that only show up at runtime: a function that passes every check and
still returns the wrong answer.

QALLM checks whether your code *runs* right. It takes your Python or Jupyter
notebook code and:

1. runs static analysis to get a baseline,
2. generates and executes tests to find defects that static analysis misses,
   the gap between "looks right" and "runs right" (we call it the
   **verification gap**),
3. where it finds a defect, it can propose a fix and verify the fix by running
   the tests again.

Each finding also comes with a **confidence**, an indication of how trustworthy
the test that found it is, so you know which findings to act on first.

## Your first run (5 minutes)

1. **Open the tool** and stay on the default pipeline screen.
2. **Load the sample project** (a button on the setup screen) if you just want
   to see it work, or **upload your own** `.py` or `.ipynb` files.
3. **Pick a quality model** (the default is fine to start).
4. **Choose Manual mode** (recommended for your first run, see below).
5. **Start the pipeline.** You will reach the baseline first.

## Manual vs Automatic mode

Both modes run the exact same pipeline. The difference is only how much you see
along the way.

- **Manual**: you step through each stage (analyse, then verify, then repair,
  then judge) and can inspect the output of each before continuing. Best for
  understanding what the tool is doing, and the right choice the first time.
- **Automatic**: runs everything end to end and drops you at the results. Best
  once you know the tool and just want the outcome.

If in doubt, use Manual.

## Reading the baseline

The baseline screen lists the static findings: severity, the tool that raised
each one, the location (file and line), and a message. **Click any finding row
to expand it** and see the detail: the finding type, the rule, the exact line,
and the offending code snippet.

The interesting part is what comes next: when QALLM runs its tests, it shows
which findings execution actually confirms, and the defects it found that static
analysis never flagged. That second group is the verification gap.

## What the results mean

- **Verification gap**: functions that passed static analysis but that execution
  proved are defective. This is the headline, the bugs your linter would have
  let through.
- **Confidence (high / medium / low)**: how well the test that found a defect
  detects injected faults. Act on high-confidence findings first.
- **Confirmed / refuted / inconclusive**: for the findings static analysis did
  raise, whether execution could reproduce the issue. "Inconclusive" is honest,
  it means the generated test could not settle it (common for some security
  findings).
- **Verified fix**: where QALLM repaired a defect, whether re-running the tests
  confirms the fix.

## Tips

- Start with the **sample project** to see a clean end-to-end run before using
  your own code.
- Notebooks (`.ipynb`) and scripts (`.py`) both work.
- A finding with **low or unknown confidence** is not necessarily wrong; it
  means the test that found it is weak, so treat it as a lead, not a verdict.

## Giving feedback

Found something confusing or missing? That feedback is genuinely useful. Note the
step you were on and what you expected to see, and send it along. The tool is
under active development and tester input shapes it directly.
