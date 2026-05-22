"""Numerical comparison of two ProfileVerdicts.

Given a parent verdict and a variant verdict over the same profile, produce
a :class:`VerdictComparison`: a structured side-by-side diff of every
indicator and dimension. All three judge strategies build on this.

The comparison is deterministic and never calls an LLM. It encodes only the
rules of arithmetic and status ordering, not any opinion about whether the
overall change is good.
"""

from __future__ import annotations

from qallm.evaluation import (
    DimensionResult,
    IndicatorResult,
    IndicatorStatus,
    ProfileVerdict,
)
from qallm.judge.models import (
    DimensionDelta,
    IndicatorChange,
    IndicatorDelta,
    VerdictComparison,
)


def _direction_for_comparator(comparator: str) -> int:
    """Return +1 if higher measured is better, -1 if lower is better.

    Mirrors the Comparator enum in qallm.profiles. Unknown comparators
    default to "higher is better".

    Note on semantics: the indicator's comparator encodes what the
    *profile author* meant. For example, ``bugs_caught`` uses GE because
    higher is treated as better (more thorough test suite). This may be
    counter-intuitive: a variant with fewer bugs caught is not necessarily
    a *better* variant; it may just have a weaker test suite. The judge
    here only enforces the profile's stated direction; methodological
    interpretation of any single indicator is for the thesis to discuss.
    """
    comp = comparator.lower()
    if comp in ("le", "lt", "lte"):
        return -1
    # ge, gt, eq, ne, and anything unrecognised: higher is better by default.
    return +1


def _classify_indicator(
    parent: IndicatorResult, variant: IndicatorResult
) -> tuple[IndicatorChange, float | None]:
    """Compare one indicator and return (change, numeric_delta).

    Rules:
      * If either status is ERROR or SKIPPED, status-based comparison only.
      * If both measured values exist, the comparator determines whether
        an increase is improvement or regression.
      * If only one measured value exists, classification is INCOMPARABLE.
    """
    # Status-driven cases first: ERROR or SKIPPED on either side.
    p_status = parent.status
    v_status = variant.status

    if p_status is IndicatorStatus.ERROR or v_status is IndicatorStatus.ERROR:
        # An ERROR on either side is uncomparable: we cannot say one is
        # better than the other based on a broken measurement.
        return IndicatorChange.INCOMPARABLE, None

    if (
        p_status is IndicatorStatus.SKIPPED
        and v_status is IndicatorStatus.SKIPPED
    ):
        return IndicatorChange.UNCHANGED, None

    # Status transitions when SKIPPED appears on only one side: we can't
    # meaningfully compare because the parent or variant has no signal.
    if (
        p_status is IndicatorStatus.SKIPPED
        or v_status is IndicatorStatus.SKIPPED
    ):
        return IndicatorChange.INCOMPARABLE, None

    # At this point both statuses are PASS or FAIL.
    p_meas = parent.measured
    v_meas = variant.measured

    if p_meas is None or v_meas is None:
        # No measured value on one side: fall back to status only.
        if p_status == v_status:
            return IndicatorChange.UNCHANGED, None
        # PASS -> FAIL is regression; FAIL -> PASS is improvement.
        if p_status is IndicatorStatus.PASS and v_status is IndicatorStatus.FAIL:
            return IndicatorChange.REGRESSED, None
        return IndicatorChange.IMPROVED, None

    direction = _direction_for_comparator(parent.comparator)
    delta = v_meas - p_meas
    # Direction-adjusted delta: positive means improvement.
    adjusted = delta * direction

    # Use a small epsilon to avoid floating-point noise being labelled as
    # change.
    eps = 1e-9
    if abs(adjusted) < eps:
        return IndicatorChange.UNCHANGED, delta
    if adjusted > 0:
        return IndicatorChange.IMPROVED, delta
    return IndicatorChange.REGRESSED, delta


def _compare_dimension(
    parent_dim: DimensionResult, variant_dim: DimensionResult
) -> DimensionDelta:
    """Compare two DimensionResults by walking their indicators."""
    # Match indicators by name. Profiles are stable across rounds, so the
    # name set should match exactly; if it doesn't, we record what we can.
    parent_by_name = {ind.name: ind for ind in parent_dim.indicators}
    variant_by_name = {ind.name: ind for ind in variant_dim.indicators}

    deltas: list[IndicatorDelta] = []
    all_names = sorted(set(parent_by_name) | set(variant_by_name))
    for name in all_names:
        p = parent_by_name.get(name)
        v = variant_by_name.get(name)
        if p is None or v is None:
            # Asymmetric: a new or missing indicator. Classify as
            # INCOMPARABLE rather than guessing.
            placeholder = p or v
            assert placeholder is not None  # one is guaranteed non-None
            deltas.append(
                IndicatorDelta(
                    name=name,
                    evaluator=placeholder.evaluator,
                    parent_status=p.status if p else IndicatorStatus.SKIPPED,
                    variant_status=v.status if v else IndicatorStatus.SKIPPED,
                    parent_measured=p.measured if p else None,
                    variant_measured=v.measured if v else None,
                    comparator=placeholder.comparator,
                    change=IndicatorChange.INCOMPARABLE,
                    delta=None,
                )
            )
            continue

        change, delta = _classify_indicator(p, v)
        deltas.append(
            IndicatorDelta(
                name=name,
                evaluator=p.evaluator,
                parent_status=p.status,
                variant_status=v.status,
                parent_measured=p.measured,
                variant_measured=v.measured,
                comparator=p.comparator,
                change=change,
                delta=delta,
            )
        )

    return DimensionDelta(
        dimension=parent_dim.dimension,
        parent_status=parent_dim.status,
        variant_status=variant_dim.status,
        indicator_deltas=deltas,
    )


def compare_verdicts(
    parent: ProfileVerdict, variant: ProfileVerdict
) -> VerdictComparison:
    """Compare two ProfileVerdicts indicator-by-indicator, dimension-by-dimension.

    Both verdicts should come from the same profile. If they don't (one has
    dimensions the other lacks), missing dimensions are treated as SKIPPED
    and any present indicators are marked INCOMPARABLE.
    """
    parent_by_dim = {d.dimension: d for d in parent.dimensions}
    variant_by_dim = {d.dimension: d for d in variant.dimensions}

    all_dims = sorted(
        set(parent_by_dim) | set(variant_by_dim),
        key=lambda d: d.value,
    )

    deltas: list[DimensionDelta] = []
    for dim in all_dims:
        p_dim = parent_by_dim.get(dim)
        v_dim = variant_by_dim.get(dim)
        if p_dim is None or v_dim is None:
            # An entire dimension missing on one side. Build a placeholder
            # delta with empty indicator list; consumers see status SKIPPED.
            present = p_dim or v_dim
            assert present is not None
            deltas.append(
                DimensionDelta(
                    dimension=dim,
                    parent_status=p_dim.status if p_dim else IndicatorStatus.SKIPPED,
                    variant_status=v_dim.status if v_dim else IndicatorStatus.SKIPPED,
                    indicator_deltas=[],
                )
            )
            continue
        deltas.append(_compare_dimension(p_dim, v_dim))

    return VerdictComparison(dimension_deltas=deltas)
