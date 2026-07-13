"""Discovery exclude globs: sampling-frame hygiene for the form comparison.

The .py arm of the notebook-vs-python comparison (playbook run 4) must not
sample test files, __init__.py, or packaging boilerplate: they have no
notebook counterpart, so their inclusion confounds the form variable
(MD-010). Excludes match the dataset-relative path and the bare filename,
and are recorded in the run manifest because they change the sampling frame.
"""

from pathlib import Path

from qallm.experiments.gap_runner import _discover_inputs


def _touch(root: Path, rel: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x = 1\n")


def _build(tmp_path: Path) -> Path:
    for rel in [
        "proj/analysis.py",
        "proj/scripts/model.py",
        "proj/tests/test_model.py",
        "proj/test_utils.py",
        "proj/__init__.py",
        "proj/setup.py",
        "other/pipeline.py",
    ]:
        _touch(tmp_path, rel)
    return tmp_path


EXCLUDES = ("*/tests/*", "test_*.py", "*_test.py",
            "__init__.py", "setup.py", "conftest.py")


def test_excludes_prune_tests_and_boilerplate(tmp_path):
    root = _build(tmp_path)
    kept = {p.relative_to(root).as_posix()
            for p in _discover_inputs(root, "*.py", EXCLUDES)}
    assert kept == {"proj/analysis.py", "proj/scripts/model.py",
                    "other/pipeline.py"}


def test_no_excludes_keeps_everything(tmp_path):
    root = _build(tmp_path)
    assert len(_discover_inputs(root, "*.py")) == 7


def test_exclude_matches_relative_path_not_absolute(tmp_path):
    # A glob like "*/tests/*" must match the dataset-relative path even when
    # the absolute prefix contains no separator-friendly text.
    root = _build(tmp_path)
    kept = _discover_inputs(root, "*.py", ("*/tests/*",))
    assert all("tests" not in p.parts for p in kept)


def test_excludes_recorded_in_manifest_dict():
    from qallm.experiments.gap_runner import GapExperimentConfig
    cfg = GapExperimentConfig(dataset_dir=Path("d"), output_dir=Path("o"),
                              excludes=("__init__.py",))
    assert cfg.to_manifest()["excludes"] == ["__init__.py"]
