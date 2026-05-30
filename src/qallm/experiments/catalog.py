"""Catalog of validation experiments available in QALLM.

The Experiments tab lists these so a user can see what each experiment is,
the dataset it draws on, the citation and source URL, and what the code
looks like, then launch a run or browse historical runs. Keeping the
catalog as data (not hard-coded in the UI) means adding an experiment is a
backend change in one place.

Each entry is descriptive metadata only; the actual run is driven by
``qallm.experiments.humaneval_runner``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ExperimentSpec:
    """Descriptive metadata for one available experiment."""

    id: str
    name: str
    summary: str
    dataset_id: str          # the dataset identifier (e.g. a HF dataset)
    dataset_url: str         # where to view the dataset
    citation: str            # how to cite the dataset/benchmark
    n_problems: int          # size of the full set
    measures: list[str] = field(default_factory=list)  # what it measures
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# The HumanEvalFix benchmark: each task ships a buggy solution, the
# canonical fix, and a hidden unit-test suite, so it measures both whether
# QALLM detects the planted bug (by execution) and whether it repairs it.
HUMANEVALFIX = ExperimentSpec(
    id="humanevalfix",
    name="HumanEvalFix (Python)",
    summary=(
        "Each task carries a buggy program, its canonical fix, and a hidden "
        "unit-test suite. Measures whether QALLM detects the planted bug by "
        "execution and whether the improvement loop repairs it, across "
        "strategies and models."
    ),
    dataset_id="bigcode/humanevalpack",
    dataset_url="https://huggingface.co/datasets/bigcode/humanevalpack",
    citation=(
        "Muennighoff et al. (2023), OctoPack: Instruction Tuning Code Large "
        "Language Models. The HumanEvalPack/HumanEvalFix benchmark, Python "
        "subset."
    ),
    n_problems=164,
    measures=["bug detection rate", "repair success rate", "rounds", "cost"],
    notes=(
        "Datasets download from Hugging Face at run time, so a run needs "
        "network access and (for hosted models) LLM credentials. A full run "
        "over all 164 problems across several strategies/models takes hours; "
        "use a sample size for quick checks."
    ),
)


_CATALOG = {HUMANEVALFIX.id: HUMANEVALFIX}


def list_experiments() -> list[ExperimentSpec]:
    return list(_CATALOG.values())


def get_experiment(experiment_id: str) -> ExperimentSpec | None:
    return _CATALOG.get(experiment_id)
