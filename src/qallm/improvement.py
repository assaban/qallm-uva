"""Improvement log: the per-round, per-indicator audit of quality change.

The judge decides accept or abandon, but to *defend* the claim that the
loop improves quality we need to see exactly which indicators moved, in
which direction, and how the status transitioned (e.g. FAIL -> PASS). This
module turns a parent verdict and a variant verdict into a structured,
human-readable delta.

It is pure: no I/O, no LLM. The reporter persists the output as
``improvement.json`` per round, and the API serves it to the UI so a
reviewer can answer "did this round actually help, and where?".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Direction of a single indicator's change between parent and variant.
IMPROVED = "improved"
REGRESSED = "regressed"
UNCHANGED = "unchanged"
APPEARED = "appeared"      # indicator present in variant but not parent
DISAPPEARED = "disappeared"


@dataclass
class IndicatorDelta:
    name: str
    dimension: str
    comparator: str            # GE | LE | etc., to read the direction
    threshold: float
    parent_measured: Optional[float]
    variant_measured: Optional[float]
    parent_status: Optional[str]
    variant_status: Optional[str]
    measured_delta: Optional[float]
    status_transition: str     # e.g. "FAIL->PASS", "PASS->PASS"
    direction: str             # IMPROVED | REGRESSED | UNCHANGED | ...

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DimensionDelta:
    dimension: str
    parent_status: Optional[str]
    variant_status: Optional[str]
    indicators: list[IndicatorDelta] = field(default_factory=list)

    @property
    def net(self) -> str:
        """Net direction for the dimension from its indicator transitions."""
        dirs = [i.direction for i in self.indicators]
        improved = sum(1 for d in dirs if d in (IMPROVED, APPEARED))
        regressed = sum(1 for d in dirs if d in (REGRESSED, DISAPPEARED))
        if improved and not regressed:
            return IMPROVED
        if regressed and not improved:
            return REGRESSED
        if improved and regressed:
            return "mixed"
        return UNCHANGED

    def to_dict(self) -> dict[str, Any]:
        d = {
            "dimension": self.dimension,
            "parent_status": self.parent_status,
            "variant_status": self.variant_status,
            "net": self.net,
            "indicators": [i.to_dict() for i in self.indicators],
        }
        return d


@dataclass
class ImprovementReport:
    round_number: int
    unit_id: str
    accepted: bool
    parent_round: Optional[int]
    overall_parent_status: Optional[str]
    overall_variant_status: Optional[str]
    dimensions: list[DimensionDelta] = field(default_factory=list)
    judge_outcome: Optional[str] = None
    judge_rationale: Optional[str] = None

    def counts(self) -> dict[str, int]:
        """Tally indicator directions across all dimensions."""
        tally = {IMPROVED: 0, REGRESSED: 0, UNCHANGED: 0,
                 APPEARED: 0, DISAPPEARED: 0}
        for dim in self.dimensions:
            for ind in dim.indicators:
                tally[ind.direction] = tally.get(ind.direction, 0) + 1
        return tally

    def headline(self) -> str:
        """One-line human summary of what this round did."""
        c = self.counts()
        improved = c[IMPROVED] + c[APPEARED]
        regressed = c[REGRESSED] + c[DISAPPEARED]
        verb = "ACCEPTED" if self.accepted else "ABANDONED"
        return (
            f"Round {self.round_number} {verb}: "
            f"{improved} indicator(s) improved, {regressed} regressed, "
            f"{c[UNCHANGED]} unchanged."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_number": self.round_number,
            "unit_id": self.unit_id,
            "accepted": self.accepted,
            "parent_round": self.parent_round,
            "overall_parent_status": self.overall_parent_status,
            "overall_variant_status": self.overall_variant_status,
            "judge_outcome": self.judge_outcome,
            "judge_rationale": self.judge_rationale,
            "counts": self.counts(),
            "headline": self.headline(),
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


def _classify(
    comparator: str,
    parent_val: Optional[float],
    variant_val: Optional[float],
    parent_status: Optional[str],
    variant_status: Optional[str],
) -> str:
    """Decide whether an indicator improved, regressed, or held steady.

    Status transition dominates: moving FAIL -> PASS is an improvement
    regardless of the raw number, and PASS -> FAIL a regression. When the
    status is unchanged, the measured value decides, read in the direction
    the comparator implies (GE: higher is better; LE: lower is better).
    """
    if parent_val is None and variant_val is None:
        return UNCHANGED
    if parent_val is None and variant_val is not None:
        return APPEARED
    if parent_val is not None and variant_val is None:
        return DISAPPEARED

    # Status transition first.
    if parent_status != variant_status:
        good = {"PASS"}
        if variant_status in good and parent_status not in good:
            return IMPROVED
        if parent_status in good and variant_status not in good:
            return REGRESSED

    # Same status (or both non-terminal): use the measured delta.
    if parent_val == variant_val:
        return UNCHANGED
    higher_is_better = comparator.upper() in ("GE", "GT")
    increased = variant_val > parent_val
    if increased:
        return IMPROVED if higher_is_better else REGRESSED
    return REGRESSED if higher_is_better else IMPROVED


def _index_indicators(verdict_dict: dict[str, Any]) -> dict[tuple[str, str], dict]:
    """Map (dimension, indicator_name) -> indicator dict for a verdict."""
    out: dict[tuple[str, str], dict] = {}
    for dim in verdict_dict.get("dimensions", []):
        dname = dim.get("dimension", "")
        for ind in dim.get("indicators", []):
            out[(dname, ind.get("name", ""))] = ind
    return out


def build_improvement_report(
    *,
    round_number: int,
    unit_id: str,
    accepted: bool,
    parent_verdict: Optional[dict[str, Any]],
    variant_verdict: dict[str, Any],
    parent_round: Optional[int] = None,
    judge_verdict: Optional[dict[str, Any]] = None,
) -> ImprovementReport:
    """Compute the per-indicator improvement report for one variant.

    Args take dicts (the ``to_dict()`` form of ProfileVerdict and the
    judge verdict) so this module stays decoupled from the evaluation
    types and is trivially testable.
    """
    report = ImprovementReport(
        round_number=round_number,
        unit_id=unit_id,
        accepted=accepted,
        parent_round=parent_round,
        overall_parent_status=(parent_verdict or {}).get("status"),
        overall_variant_status=variant_verdict.get("status"),
        judge_outcome=(judge_verdict or {}).get("outcome"),
        judge_rationale=(judge_verdict or {}).get("rationale")
        or (judge_verdict or {}).get("reason"),
    )

    parent_idx = _index_indicators(parent_verdict or {})

    for dim in variant_verdict.get("dimensions", []):
        dname = dim.get("dimension", "")
        parent_dim_status = None
        for pdim in (parent_verdict or {}).get("dimensions", []):
            if pdim.get("dimension") == dname:
                parent_dim_status = pdim.get("status")
                break
        dim_delta = DimensionDelta(
            dimension=dname,
            parent_status=parent_dim_status,
            variant_status=dim.get("status"),
        )
        for ind in dim.get("indicators", []):
            name = ind.get("name", "")
            pind = parent_idx.get((dname, name))
            p_val = (pind or {}).get("measured")
            v_val = ind.get("measured")
            p_status = (pind or {}).get("status")
            v_status = ind.get("status")
            comparator = ind.get("comparator", "")
            delta = None
            if isinstance(p_val, (int, float)) and isinstance(v_val, (int, float)):
                delta = v_val - p_val
            direction = _classify(comparator, p_val, v_val, p_status, v_status)
            dim_delta.indicators.append(IndicatorDelta(
                name=name,
                dimension=dname,
                comparator=comparator,
                threshold=ind.get("threshold", 0.0),
                parent_measured=p_val,
                variant_measured=v_val,
                parent_status=p_status,
                variant_status=v_status,
                measured_delta=delta,
                status_transition=f"{p_status}->{v_status}"
                if p_status or v_status else "n/a",
                direction=direction,
            ))
        report.dimensions.append(dim_delta)

    return report
