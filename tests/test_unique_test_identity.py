"""Tests for unique test identity across rounds.

Same-named tests generated in different rounds must not shadow one another
when concatenated into a single pytest module, and their provenance (origin
round) must be recoverable from the nodeid.
"""
from __future__ import annotations

from qallm.verification.executor import _parse_test_provenance
from qallm.verification.models import GeneratedTest
from qallm.verification.test_persistence import (
    FunctionRecord,
    StoredTest,
)
from qallm.verification.verification_manager import (
    _concatenate_test_codes,
    _suffix_test_functions,
)


def _gen(code: str, model: str = "m") -> GeneratedTest:
    return GeneratedTest(
        function_name="f", oracle="correctness", test_code=code,
        is_valid=True, model=model,
    )


def _stored(code: str, rnd: int) -> StoredTest:
    return StoredTest(
        test_code=code, generated_in_round=rnd, is_valid=True,
        model="m", original=_gen(code),
    )


class TestContentHashAndId:
    def test_identical_code_same_hash(self) -> None:
        a = _stored("def test_x(): assert True", 0)
        b = _stored("def test_x():   assert True  ", 1)  # whitespace only
        assert a.content_hash == b.content_hash

    def test_different_logic_different_hash(self) -> None:
        a = _stored("def test_x(): assert f(1, 5) == 4", 0)
        b = _stored("def test_x(): assert f(1, 5) == 5", 1)
        assert a.content_hash != b.content_hash

    def test_test_id_is_round_stamped(self) -> None:
        s = _stored("def test_x(): assert True", 3)
        assert s.test_id.startswith("r3_")


class TestDeduplication:
    def test_identical_regeneration_is_deduped(self) -> None:
        rec = FunctionRecord(function_name="f")
        rec.append_test(_gen("def test_x(): assert True"), 0)
        rec.append_test(_gen("def test_x(): assert True"), 1)
        assert len(rec.tests) == 1

    def test_different_logic_is_kept(self) -> None:
        rec = FunctionRecord(function_name="f")
        rec.append_test(_gen("def test_x(): assert f() == 1"), 0)
        rec.append_test(_gen("def test_x(): assert f() == 2"), 1)
        assert len(rec.tests) == 2


class TestSuffixing:
    def test_same_name_different_rounds_both_survive(self) -> None:
        s0 = _stored("def test_x(): assert f(1, 5) == 4", 0)
        s1 = _stored("def test_x(): assert f(1, 5) == 5", 1)
        out = _concatenate_test_codes([s0, s1])
        import re
        names = re.findall(r"def (test_\w+)\(", out)
        assert len(set(names)) == 2, "both versions must survive, not shadow"
        assert all("__r" in n for n in names)

    def test_helper_functions_not_renamed(self) -> None:
        code = "def helper(): return 1\n\ndef test_x(): assert helper() == 1"
        out = _suffix_test_functions(code, "r0_abcd1234")
        assert "def helper():" in out
        assert "def test_x__r0_abcd1234(" in out
        assert "helper() == 1" in out  # call site preserved


class TestProvenanceParsing:
    def test_round_trip(self) -> None:
        nodeid = "test_generated.py::test_start_greater_than_end__r2_ab12cd34"
        rnd, test_id, display = _parse_test_provenance(nodeid)
        assert rnd == 2
        assert test_id == "r2_ab12cd34"
        assert display == "test_start_greater_than_end"

    def test_unsuffixed_nodeid(self) -> None:
        rnd, test_id, display = _parse_test_provenance("test_generated.py::test_plain")
        assert rnd is None
        assert test_id is None
        assert display == "test_plain"
