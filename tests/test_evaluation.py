"""Tests for qallm.evaluation.

Coverage targets:

  * Registry: known/unknown lookups, error message includes registered ids.
  * Built-in evaluators on real sample sources (skipped cleanly if the
    underlying tool is missing).
  * ``evaluate_profile`` walking the default profile end-to-end with a
    real source and a stubbed registry.
  * Indicator outcomes: PASS, FAIL, SKIPPED, ERROR.
  * Dimension and verdict roll-up rules (worst-of, all-skipped, any-error).
  * JSON serialisation.

Tests use a fresh in-memory registry per case where they need isolation,
restoring the original registrations after the test runs.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from qallm import evaluation
from qallm.evaluation import (
    DimensionResult,
    IndicatorResult,
    IndicatorStatus,
    ProfileVerdict,
    evaluate_profile,
    register,
    registered_evaluators,
    resolve,
)
from qallm.profiles import (
    IMPLEMENTATION_DEFAULT,
    Comparator,
    DimensionSpec,
    QualityDimension,
    QualityIndicator,
    QualityProfile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def preserve_registry():
    """Snapshot the evaluator registry and restore it after the test."""
    snapshot = dict(evaluation._REGISTRY)
    yield
    evaluation._REGISTRY.clear()
    evaluation._REGISTRY.update(snapshot)


@pytest.fixture
def simple_clean_source() -> str:
    return (
        "def add(a, b):\n"
        "    \"\"\"Return the sum of two numbers.\"\"\"\n"
        "    return a + b\n"
    )


@pytest.fixture
def temp_project_with_manifest():
    """A scratch directory containing a requirements.txt."""
    root = Path(tempfile.mkdtemp(prefix="qallm-eval-"))
    (root / "requirements.txt").write_text("radon\nbandit\n")
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def temp_project_without_manifest():
    root = Path(tempfile.mkdtemp(prefix="qallm-eval-"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_builtins_are_registered():
    ids = registered_evaluators()
    assert "radon.mi" in ids
    assert "radon.cc" in ids
    assert "bandit.high" in ids
    assert "qallm.repro.manifest" in ids


def test_resolve_returns_callable_for_known_id():
    fn = resolve("radon.mi")
    assert callable(fn)


def test_resolve_raises_with_helpful_message_for_unknown_id():
    with pytest.raises(KeyError) as info:
        resolve("does.not.exist")
    msg = str(info.value)
    assert "does.not.exist" in msg
    assert "radon.mi" in msg


def test_register_overwrites_previous(preserve_registry):
    register("test.dummy", lambda src, ctx: 1.0)
    assert resolve("test.dummy")("", {}) == 1.0
    register("test.dummy", lambda src, ctx: 2.0)
    assert resolve("test.dummy")("", {}) == 2.0


# ---------------------------------------------------------------------------
# Built-in evaluators
# ---------------------------------------------------------------------------


def _radon_available() -> bool:
    return shutil.which("radon") is not None


def _bandit_available() -> bool:
    return shutil.which("bandit") is not None


@pytest.mark.skipif(not _radon_available(), reason="radon not installed")
def test_radon_mi_returns_float_on_real_source(simple_clean_source):
    fn = resolve("radon.mi")
    value = fn(simple_clean_source, {})
    assert value is not None
    assert 0.0 <= float(value) <= 100.0


@pytest.mark.skipif(not _radon_available(), reason="radon not installed")
def test_radon_cc_returns_float_on_real_source(simple_clean_source):
    fn = resolve("radon.cc")
    value = fn(simple_clean_source, {})
    assert value is not None
    assert float(value) >= 0.0


def test_radon_mi_returns_none_on_empty_source():
    assert resolve("radon.mi")("", {}) is None
    assert resolve("radon.mi")("   \n  ", {}) is None


@pytest.mark.skipif(not _bandit_available(), reason="bandit not installed")
def test_bandit_high_returns_count_for_safe_source(simple_clean_source):
    value = resolve("bandit.high")(simple_clean_source, {})
    # Clean source should have zero HIGH findings.
    assert value == 0.0


def test_repro_manifest_finds_requirements_txt(temp_project_with_manifest):
    fn = resolve("qallm.repro.manifest")
    value = fn("", {"project_root": str(temp_project_with_manifest)})
    assert value == 1.0


def test_repro_manifest_returns_zero_when_no_manifest_present(
    temp_project_without_manifest,
):
    fn = resolve("qallm.repro.manifest")
    value = fn("", {"project_root": str(temp_project_without_manifest)})
    assert value == 0.0


def test_repro_manifest_returns_none_without_project_root():
    fn = resolve("qallm.repro.manifest")
    assert fn("anything", {}) is None


def test_verification_evaluators_skip_without_sessions():
    # Reliability indicators are registered. They require a list of
    # verification sessions in the context; without it, they decline to
    # produce a value (SKIPPED), which is what we want.
    assert resolve("qallm.verification.pass_rate")("source", {}) is None
    assert resolve("qallm.verification.bugs")("source", {}) is None


# ---------------------------------------------------------------------------
# Verification-backed evaluators: pass_rate and bugs
# ---------------------------------------------------------------------------


def _make_session(
    *,
    function_name: str = "f",
    passed: int = 0,
    failed: int = 0,
    errors: int = 0,
    final_bugs: int = 0,
):
    """Build a TestGenerationSession with one round whose execution result has
    the given counts. final_bugs sets the cumulative_bugs on that round.
    """
    from qallm.verification.models import (
        ExecutionResult,
        GeneratedTest,
        RewardBreakdown,
        RoundResult,
        TestGenerationSession,
    )

    execution = ExecutionResult(
        passed=passed,
        failed=failed,
        errors=errors,
        total=passed + failed + errors,
    )
    generated = GeneratedTest(
        function_name=function_name,
        oracle="crash",
        test_code="def test_x(): pass",
        is_valid=True,
        generation_error=None,
        model="stub",
        provider="stub",
        input_tokens=0,
        output_tokens=0,
    )
    reward = RewardBreakdown(total=0.0)
    round_result = RoundResult(
        round_number=1,
        generated_test=generated,
        execution=execution,
        reward=reward,
        cumulative_coverage=100.0,
        cumulative_bugs=final_bugs,
    )
    session = TestGenerationSession(
        function_name=function_name,
        source_code="def f(): pass",
        oracle="crash",
        model="stub",
        total_rounds=1,
    )
    session.rounds.append(round_result)
    return session


class TestVerificationPassRate:
    """Behaviour of the qallm.verification.pass_rate evaluator."""

    def test_returns_none_without_sessions_key(self):
        fn = resolve("qallm.verification.pass_rate")
        assert fn("src", {}) is None

    def test_returns_none_for_empty_sessions_list(self):
        fn = resolve("qallm.verification.pass_rate")
        assert fn("src", {"verification_sessions": []}) is None

    def test_single_session_all_passing(self):
        fn = resolve("qallm.verification.pass_rate")
        sessions = [_make_session(passed=10, failed=0)]
        assert fn("src", {"verification_sessions": sessions}) == 1.0

    def test_single_session_half_passing(self):
        fn = resolve("qallm.verification.pass_rate")
        sessions = [_make_session(passed=5, failed=5)]
        assert fn("src", {"verification_sessions": sessions}) == 0.5

    def test_errors_excluded_from_denominator(self):
        # Five passed, zero failed, two errored => pass rate is 5/5 = 1.0.
        # Errors are infrastructure failures, not test results, and shouldn't
        # be punished as 'not passing'.
        fn = resolve("qallm.verification.pass_rate")
        sessions = [_make_session(passed=5, failed=0, errors=2)]
        assert fn("src", {"verification_sessions": sessions}) == 1.0

    def test_multi_session_averages(self):
        # Two functions, one perfect, one 50%. Mean is 0.75.
        fn = resolve("qallm.verification.pass_rate")
        sessions = [
            _make_session(function_name="f", passed=10, failed=0),
            _make_session(function_name="g", passed=5, failed=5),
        ]
        assert fn("src", {"verification_sessions": sessions}) == 0.75

    def test_skips_undefined_sessions(self):
        # If one session has 0 passed + 0 failed (only errors), its rate is
        # undefined and should be excluded from the average rather than
        # counted as zero.
        fn = resolve("qallm.verification.pass_rate")
        sessions = [
            _make_session(function_name="f", passed=10, failed=0),
            _make_session(function_name="g", passed=0, failed=0, errors=3),
        ]
        # Only the first session contributes: rate is 1.0.
        assert fn("src", {"verification_sessions": sessions}) == 1.0


class TestVerificationBugs:
    """Behaviour of the qallm.verification.bugs evaluator."""

    def test_returns_none_without_sessions_key(self):
        fn = resolve("qallm.verification.bugs")
        assert fn("src", {}) is None

    def test_empty_list_is_zero(self):
        # An empty list means 'we ran verification on nothing' which is a
        # meaningful 0, not a SKIP.
        fn = resolve("qallm.verification.bugs")
        assert fn("src", {"verification_sessions": []}) == 0.0

    def test_sums_across_sessions(self):
        fn = resolve("qallm.verification.bugs")
        sessions = [
            _make_session(function_name="f", final_bugs=2),
            _make_session(function_name="g", final_bugs=3),
        ]
        assert fn("src", {"verification_sessions": sessions}) == 5.0


class TestFinalPassRateProperty:
    """The TestGenerationSession.final_pass_rate property added for NEW-03."""

    def test_no_rounds_returns_none(self):
        from qallm.verification.models import TestGenerationSession

        session = TestGenerationSession(
            function_name="f",
            source_code="def f(): pass",
            oracle="crash",
            model="stub",
            total_rounds=1,
        )
        assert session.final_pass_rate is None

    def test_zero_denominator_returns_none(self):
        # Latest round had only errors, no pass/fail outcomes.
        session = _make_session(passed=0, failed=0, errors=3)
        assert session.final_pass_rate is None

    def test_uses_latest_round_only(self):
        # Two rounds: first one bad, second one perfect. Should reflect the
        # current variant, which is the latest round.
        from qallm.verification.models import (
            ExecutionResult,
            GeneratedTest,
            RewardBreakdown,
            RoundResult,
            TestGenerationSession,
        )

        def _make_round(round_num, passed, failed):
            return RoundResult(
                round_number=round_num,
                generated_test=GeneratedTest(
                    function_name="f",
                    oracle="crash",
                    test_code="x",
                    is_valid=True,
                    generation_error=None,
                    model="stub",
                    provider="stub",
                    input_tokens=0,
                    output_tokens=0,
                ),
                execution=ExecutionResult(
                    passed=passed, failed=failed, total=passed + failed
                ),
                reward=RewardBreakdown(total=0.0),
                cumulative_coverage=100.0,
                cumulative_bugs=0,
            )

        session = TestGenerationSession(
            function_name="f",
            source_code="def f(): pass",
            oracle="crash",
            model="stub",
            total_rounds=2,
        )
        session.rounds.append(_make_round(1, passed=2, failed=8))  # 0.2
        session.rounds.append(_make_round(2, passed=10, failed=0))  # 1.0

        assert session.final_pass_rate == 1.0  # latest, not historical


# ---------------------------------------------------------------------------
# evaluate_profile end-to-end with stubs
# ---------------------------------------------------------------------------


def _stub_profile() -> QualityProfile:
    return QualityProfile(
        profile_id="stub_profile",
        lifecycle_stage=IMPLEMENTATION_DEFAULT.lifecycle_stage,
        dimensions=(
            DimensionSpec(
                dimension=QualityDimension.MAINTAINABILITY,
                repair_prompt_id="stub_repair",
                indicators=(
                    QualityIndicator(
                        name="stub_passing",
                        evaluator="stub.passing",
                        threshold=10.0,
                        comparator=Comparator.GE,
                    ),
                ),
            ),
            DimensionSpec(
                dimension=QualityDimension.SECURITY,
                repair_prompt_id="stub_repair",
                indicators=(
                    QualityIndicator(
                        name="stub_failing",
                        evaluator="stub.failing",
                        threshold=0.0,
                        comparator=Comparator.LE,
                    ),
                ),
            ),
        ),
    )


def test_evaluate_profile_with_stub_evaluators_produces_typed_results(
    preserve_registry,
):
    register("stub.passing", lambda src, ctx: 42.0)
    register("stub.failing", lambda src, ctx: 5.0)

    verdict = evaluate_profile(_stub_profile(), "irrelevant source")

    assert verdict.profile_id == "stub_profile"
    maint = verdict.get_dimension(QualityDimension.MAINTAINABILITY)
    sec = verdict.get_dimension(QualityDimension.SECURITY)
    assert maint is not None and sec is not None

    [m_ind] = maint.indicators
    [s_ind] = sec.indicators
    assert m_ind.status is IndicatorStatus.PASS
    assert m_ind.measured == 42.0
    assert s_ind.status is IndicatorStatus.FAIL
    assert s_ind.measured == 5.0


def test_evaluate_profile_skips_indicator_when_evaluator_returns_none(
    preserve_registry,
):
    register("stub.passing", lambda src, ctx: None)
    register("stub.failing", lambda src, ctx: 0.0)

    verdict = evaluate_profile(_stub_profile(), "src")

    maint = verdict.get_dimension(QualityDimension.MAINTAINABILITY)
    [m_ind] = maint.indicators
    assert m_ind.status is IndicatorStatus.SKIPPED
    assert m_ind.measured is None


def test_evaluate_profile_marks_indicator_as_error_when_evaluator_raises(
    preserve_registry,
):
    def boom(src, ctx):
        raise RuntimeError("boom")

    register("stub.passing", boom)
    register("stub.failing", lambda src, ctx: 0.0)

    verdict = evaluate_profile(_stub_profile(), "src")
    maint = verdict.get_dimension(QualityDimension.MAINTAINABILITY)
    [m_ind] = maint.indicators
    assert m_ind.status is IndicatorStatus.ERROR
    assert "RuntimeError" in m_ind.detail
    assert "boom" in m_ind.detail


def test_evaluate_profile_marks_indicator_as_error_when_evaluator_unknown(
    preserve_registry,
):
    # Build a profile pointing to an unregistered evaluator id.
    profile = QualityProfile(
        profile_id="bad",
        lifecycle_stage=IMPLEMENTATION_DEFAULT.lifecycle_stage,
        dimensions=(
            DimensionSpec(
                dimension=QualityDimension.MAINTAINABILITY,
                repair_prompt_id="x",
                indicators=(
                    QualityIndicator(
                        name="ghost",
                        evaluator="not.registered",
                        threshold=0.0,
                        comparator=Comparator.GE,
                    ),
                ),
            ),
        ),
    )
    verdict = evaluate_profile(profile, "src")
    [dim] = verdict.dimensions
    [ind] = dim.indicators
    assert ind.status is IndicatorStatus.ERROR
    assert "not.registered" in ind.detail


# ---------------------------------------------------------------------------
# Roll-up rules
# ---------------------------------------------------------------------------


def _indicator(status: IndicatorStatus) -> IndicatorResult:
    return IndicatorResult(
        name="x",
        evaluator="x",
        threshold=0.0,
        comparator="ge",
        measured=0.0,
        status=status,
    )


def test_dimension_status_is_skipped_when_all_indicators_skipped():
    d = DimensionResult(
        dimension=QualityDimension.MAINTAINABILITY,
        indicators=[_indicator(IndicatorStatus.SKIPPED) for _ in range(3)],
    )
    assert d.status is IndicatorStatus.SKIPPED


def test_dimension_status_is_error_if_any_indicator_errored():
    d = DimensionResult(
        dimension=QualityDimension.MAINTAINABILITY,
        indicators=[
            _indicator(IndicatorStatus.PASS),
            _indicator(IndicatorStatus.ERROR),
            _indicator(IndicatorStatus.PASS),
        ],
    )
    assert d.status is IndicatorStatus.ERROR


def test_dimension_status_is_fail_if_any_indicator_failed_and_no_errors():
    d = DimensionResult(
        dimension=QualityDimension.MAINTAINABILITY,
        indicators=[
            _indicator(IndicatorStatus.PASS),
            _indicator(IndicatorStatus.FAIL),
        ],
    )
    assert d.status is IndicatorStatus.FAIL


def test_dimension_status_is_pass_when_only_pass_or_skipped():
    d = DimensionResult(
        dimension=QualityDimension.MAINTAINABILITY,
        indicators=[
            _indicator(IndicatorStatus.PASS),
            _indicator(IndicatorStatus.SKIPPED),
        ],
    )
    assert d.status is IndicatorStatus.PASS


def test_verdict_status_aggregates_across_dimensions():
    verdict = ProfileVerdict(
        profile_id="p",
        dimensions=[
            DimensionResult(
                dimension=QualityDimension.MAINTAINABILITY,
                indicators=[_indicator(IndicatorStatus.PASS)],
            ),
            DimensionResult(
                dimension=QualityDimension.SECURITY,
                indicators=[_indicator(IndicatorStatus.FAIL)],
            ),
        ],
    )
    assert verdict.status is IndicatorStatus.FAIL


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_verdict_roundtrips_through_json(preserve_registry):
    register("stub.passing", lambda src, ctx: 1.0)
    register("stub.failing", lambda src, ctx: 0.0)
    verdict = evaluate_profile(_stub_profile(), "src")

    payload = verdict.to_dict()
    text = json.dumps(payload)
    loaded = json.loads(text)

    assert loaded["profile_id"] == "stub_profile"
    assert loaded["status"] in {"pass", "fail", "skipped", "error"}
    assert {d["dimension"] for d in loaded["dimensions"]} == {
        "Maintainability",
        "Security",
    }


# ---------------------------------------------------------------------------
# Full default profile run
# ---------------------------------------------------------------------------


def test_evaluate_default_profile_on_real_source_does_not_crash(
    simple_clean_source, temp_project_with_manifest
):
    """Smoke test: run the real default profile against a real snippet.

    Indicators backed by missing tools (e.g. radon if not installed) will
    be SKIPPED rather than ERRORed because the built-in evaluators catch
    FileNotFoundError. This test exercises the full code path.
    """
    verdict = evaluate_profile(
        IMPLEMENTATION_DEFAULT,
        simple_clean_source,
        context={"project_root": str(temp_project_with_manifest)},
    )
    # All five EVERSE dimensions appear in the verdict.
    dims = {d.dimension for d in verdict.dimensions}
    assert dims == {
        QualityDimension.MAINTAINABILITY,
        QualityDimension.SECURITY,
        QualityDimension.RELIABILITY,
        QualityDimension.REPRODUCIBILITY,
        QualityDimension.FAIRNESS,
    }
    # Reliability is fully deferred in v1, so its dimension status is SKIPPED.
    rel = verdict.get_dimension(QualityDimension.RELIABILITY)
    assert rel.status is IndicatorStatus.SKIPPED
    # Reproducibility has one passing indicator (manifest exists) and one
    # skipped (determinism). Worst non-skipped is PASS.
    repro = verdict.get_dimension(QualityDimension.REPRODUCIBILITY)
    assert repro.status is IndicatorStatus.PASS
