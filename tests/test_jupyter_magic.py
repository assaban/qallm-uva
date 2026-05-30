"""Tests for the QALLM Jupyter magic (FEAT-10 frontend trigger).

These cover the parts that do not need a running IPython kernel or a real
LLM: argument parsing, HTML rendering, and the cell/line dispatch with a
stubbed orchestrator. The module imports IPython lazily, so it loads and
is testable even where IPython is not installed.
"""

from unittest.mock import MagicMock, patch

import qallm.jupyter as J

_SUMMARY = {
    "source": "cell.py", "strategy": "feedback", "model": "stub",
    "units_analyzed": 1, "functions_verified": 1,
    "rounds_accepted_total": 1, "rounds_abandoned_total": 0,
    "halt_reason": "completed", "cost": {"total_cost_usd": 0.0},
    "sessions": [{"function_name": "f", "final_coverage": 100.0, "final_bugs": 0}],
}


def test_module_imports_without_ipython():
    # The magic must not hard-depend on IPython at import time.
    assert hasattr(J, "load_ipython_extension")
    assert hasattr(J, "_run_from_args")


def test_arg_parser_defaults_and_overrides():
    p = J._make_arg_parser()
    a = p.parse_args([])
    assert a.strategy == "feedback" and a.rounds == 3 and a.source is None
    b = p.parse_args(["file.py", "--strategy", "oneshot", "--rounds", "5"])
    assert b.source == "file.py" and b.strategy == "oneshot" and b.rounds == 5


def test_summary_html_contains_key_fields():
    h = J._summary_html(_SUMMARY)
    assert "QALLM run complete" in h
    assert "feedback" in h          # strategy
    assert "divide" not in h        # only functions present are shown
    assert "f" in h                 # the function name
    assert "100%" in h              # coverage


def test_cell_magic_writes_temp_and_runs():
    fake = MagicMock()
    fake.run.return_value = _SUMMARY
    with patch.object(J, "_build_orchestrator", return_value=fake):
        result = J._run_from_args(["--strategy", "feedback"], cell="def f():\n    return 1\n")
    assert result["strategy"] == "feedback"
    # Ran on a temp cell.py file.
    assert fake.run.call_args[0][0].endswith("cell.py")


def test_line_magic_runs_on_given_path():
    fake = MagicMock()
    fake.run.return_value = _SUMMARY
    with patch.object(J, "_build_orchestrator", return_value=fake):
        J._run_from_args(["some_file.py", "--strategy", "oneshot"], cell=None)
    assert fake.run.call_args[0][0] == "some_file.py"


def test_empty_invocation_is_friendly():
    # No path and no cell: returns None, does not raise.
    assert J._run_from_args([], cell=None) is None


def test_load_extension_registers_magic():
    # Stub IPython's register_line_cell_magic so we can verify registration
    # without a real kernel.
    fake_ipython = MagicMock()
    fake_ipython.user_ns = {}
    captured = {}

    def fake_register(fn):
        captured["fn"] = fn
        return fn

    with patch.dict("sys.modules", {"IPython.core.magic": MagicMock(
            register_line_cell_magic=fake_register)}):
        J.load_ipython_extension(fake_ipython)
    assert "fn" in captured
    assert "_qallm_magic" in fake_ipython.user_ns
