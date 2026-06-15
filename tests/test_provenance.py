"""Tests for experiment provenance capture."""

from pathlib import Path
from qallm.experiments.provenance import capture, dataset_fingerprint


def test_capture_has_core_fields():
    prov = capture()
    for key in ("captured_at", "git", "python", "platform", "executable"):
        assert key in prov
    # git block always present, fields may be None outside a repo
    assert set(prov["git"]) == {"commit", "branch", "dirty"}


def test_dataset_fingerprint_is_stable_and_order_independent():
    a = dataset_fingerprint([Path("b.py"), Path("a.py")])
    b = dataset_fingerprint([Path("a.py"), Path("b.py")])
    assert a == b               # sorted before hashing
    assert a["n_inputs"] == 2


def test_dataset_fingerprint_changes_with_inputs():
    a = dataset_fingerprint([Path("a.py")])
    b = dataset_fingerprint([Path("a.py"), Path("b.py")])
    assert a["paths_sha256"] != b["paths_sha256"]


def test_extra_fields_merged():
    prov = capture({"dataset": {"n_inputs": 5}})
    assert prov["dataset"]["n_inputs"] == 5


def test_capture_never_raises(monkeypatch):
    # even if git is missing, capture returns a dict
    import qallm.experiments.provenance as p
    monkeypatch.setattr(p, "_git", lambda *a: None)
    prov = capture()
    assert prov["git"]["commit"] is None
