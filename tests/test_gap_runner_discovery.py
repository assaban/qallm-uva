"""Sampling selects a reproducible, size-spanning subset of inputs."""

from qallm.experiments.gap_runner import _sample_inputs


def _make(tmp_path, n):
    paths = []
    for i in range(n):
        p = tmp_path / f"f{i:03d}.py"
        p.write_text("x" * (i * 10 + 1))  # increasing sizes
        paths.append(p)
    return sorted(paths)


def test_sample_is_reproducible(tmp_path):
    inputs = _make(tmp_path, 30)
    a = _sample_inputs(inputs, 8, seed=1, stratify=False)
    b = _sample_inputs(inputs, 8, seed=1, stratify=False)
    assert a == b
    assert len(a) == 8


def test_sample_zero_or_oversize_returns_all(tmp_path):
    inputs = _make(tmp_path, 10)
    assert _sample_inputs(inputs, 0, 1, False) == inputs
    assert _sample_inputs(inputs, 99, 1, False) == inputs


def test_stratified_spans_size_range(tmp_path):
    inputs = _make(tmp_path, 30)
    picked = _sample_inputs(inputs, 9, seed=1, stratify=True)
    sizes = sorted(p.stat().st_size for p in picked)
    # spans from a small file to a large one
    assert sizes[0] < sizes[-1]
    assert len(picked) == 9
