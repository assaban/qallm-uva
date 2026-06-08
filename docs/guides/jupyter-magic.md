# QALLM in Jupyter: the `%%qallm` magic

QALLM ships an IPython magic so researchers can run the quality
improvement pipeline without leaving the notebook. This is FEAT-10, the
notebook frontend trigger.

## Why a magic (and not a button or a separate CLI)

Three options were considered for a notebook trigger:

1. **An IPython magic** (`%%qallm`): chosen. It runs in classic Jupyter,
   JupyterLab, and VS Code notebooks with nothing to install beyond the
   package, it wraps the same orchestrator the CLI and web UI use (so
   results are identical across entry points), and it is pure Python with
   no JavaScript extension to package or keep working across frontend
   versions.
2. **A toolbar button (nbextension/labextension)**: rejected. It needs
   per-frontend JavaScript packaging, the classic-notebook extension model
   is deprecated, and it adds maintenance cost out of proportion to the
   value over a magic.
3. **A CLI targeting `.ipynb`**: already exists. `qallm analysis.ipynb`
   works today, so this adds nothing new.

The magic is the option that adds genuinely new capability (in-notebook
invocation with inline results) at the lowest maintenance cost, which is
why it is the most valuable for the supervisor and the research community.

## Install and load

```
pip install -e ".[jupyter]"     # or just have ipython available
```

```python
%load_ext qallm.jupyter
```

## Use

Run on the code in the current cell with the **cell magic**:

```python
%%qallm --strategy feedback --rounds 3
def divide(a, b):
    return a / b
```

Run on an existing file, notebook, directory, zip, or GitHub URL with the
**line magic**:

```python
%qallm path/to/analysis.ipynb --strategy oneshot
```

Capture the full summary for further analysis in the notebook:

```python
result = %qallm mymodule.py
result["functions_verified"], result["cost"]["total_cost_usd"]
```

## Options

The magic accepts a subset of the `qallm` CLI options:

| Option | Default | Meaning |
|---|---|---|
| `--strategy` | `feedback` | `hypothesis`, `oneshot`, or `feedback` |
| `--llm` | `openai` | `openai`, `anthropic`, or `ollama` |
| `--model` | (provider default) | specific model name |
| `--rounds` | `3` | iterative feedback rounds |
| `--oracle` | `crash` | `crash`, `property`, or `metamorphic` |
| `--stage` | `implementation` | lifecycle stage for the quality profile |
| `--max-tokens` | budget default | token cap for the session |
| `--max-cost-usd` | budget default | USD cap for the session |

## What happens

```
  notebook cell                 qallm.jupyter                 pipeline
  ─────────────                 ─────────────                 ────────
  %%qallm --rounds 3
  def divide(a, b):  ─────────►  cell body written
      return a / b               to a temp .py file
                                       │
  (or)                                 ▼
  %qallm file.ipynb ─────────►  QALLMOrchestrator.run(path)  ──►  baseline,
                                       │                          repair rounds,
                                       │                          verify, judge
                                       ▼
                                 inline HTML summary
                                 (strategy, functions
                                  verified, accept/abandon,
                                  cost, per-function bugs)
                                 + returns the summary dict
```

The cell magic writes the cell body to a temporary `.py` file and runs the
pipeline on it; the line magic runs on the path you give. Either way the
orchestrator is the same one the CLI and web UI use, so a notebook run
produces the same artefacts on disk and the same numbers. Full session
artefacts are saved to the session directory and show up in the web UI's
Sessions tab.

## Notes

- The magic needs the LLM credentials the pipeline normally needs
  (e.g. `OPENAI_API_KEY`), set in the environment before launching the
  notebook.
- Results render as inline HTML in the notebook, with a plain-text
  fallback where rich display is unavailable.

## The verification gap, inline

When a run finds a runtime defect in a function that static analysis passed,
the inline summary shows a "Verification gap found" block with the actual
generated test that fails against that function. This is the point of QALLM
made tangible in the notebook: the researcher sees not just a bug count but
the concrete, runnable test that proves their code is wrong even though the
linter was happy. Clean functions produce no such block, so the gap section
only appears when there is a real gap to show.
