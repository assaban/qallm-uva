"""State and progress types for the orchestrator.

Extracted from orchestrator.py so the conductor file holds control flow,
not data definitions (per the architecture audit). These are the durable
per-unit state types (lineage, abandoned variants, per-unit track) and the
display snapshot the API reads. No loop logic lives here.

Re-exported from qallm.orchestrator for back-compat, so existing imports
like ``from qallm.orchestrator import UnitTrack`` keep working.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Literal, Optional

from qallm.common.model import CodeUnit
from qallm.evaluation import ProfileVerdict
from qallm.judge import JudgeVerdict


@dataclass
class LineageEntry:
    """One accepted variant in a code unit's lineage."""

    round_number: int
    code_unit: CodeUnit
    verdict: ProfileVerdict
    judge_verdict: Optional[JudgeVerdict] = None  # None for round 0 baseline only

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "verdict": self.verdict.to_dict(),
            "judge_verdict": (
                self.judge_verdict.to_dict() if self.judge_verdict else None
            ),
        }


@dataclass
class AbandonedEntry:
    """One rejected variant, kept for the abandoned log."""

    round_number: int
    code_unit: CodeUnit
    verdict: ProfileVerdict
    judge_verdict: JudgeVerdict

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "verdict": self.verdict.to_dict(),
            "judge_verdict": self.judge_verdict.to_dict(),
        }


@dataclass
class UnitTrack:
    """Per-unit state across QALLM rounds.

    Each code unit has its own lineage (chain of accepted variants) and
    abandoned list (rejected variants). The unit's *parent* for the next
    round is always the last entry in lineage.
    """

    unit_id: str  # stable identifier: f"{path}::{cell_index}"
    lineage: list[LineageEntry] = field(default_factory=list)
    abandoned: list[AbandonedEntry] = field(default_factory=list)

    @property
    def current_parent(self) -> Optional[LineageEntry]:
        return self.lineage[-1] if self.lineage else None

    @property
    def current_code_unit(self) -> Optional[CodeUnit]:
        parent = self.current_parent
        return parent.code_unit if parent else None

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "lineage": [e.to_dict() for e in self.lineage],
            "abandoned": [e.to_dict() for e in self.abandoned],
        }


@dataclass
class OrchestratorProgress:
    """A snapshot of orchestrator progress, safe to expose via the API.

    The orchestrator updates a handful of public attributes as it works
    (``current_phase``, ``current_stage``, ``current_unit_id``). The
    ``snapshot()`` method on the orchestrator reads those plus other
    durable state (tracks, budget, halt reason) and returns this dataclass.

    Designed for *display*, not for *control*. The fields are descriptive
    strings and counts. The UI renders them as a status line plus live
    counters; it does not infer a percentage.

    Why "snapshot": the orchestrator is running in a worker thread when
    the API endpoint reads its state. We never block on the worker, never
    take a lock. Python's GIL plus the fact that we only *read* primitive
    attributes makes a moment-in-time snapshot safe. The user does not
    care if the values are 50 milliseconds old.
    """

    # Top-level phase.
    phase: Literal["initialising", "baseline", "rounds", "summary", "done"]
    # Within the rounds phase.
    current_round: int
    total_rounds: int
    # Within one round, the stage of work for the *current* unit.
    current_stage: Optional[Literal["analyse", "repair", "verify", "judge"]]
    current_unit_id: Optional[str]
    # Within the verify stage, the function currently being verified.
    # On slow local LLMs an 8-function unit can spend 10+ minutes in
    # verify; without function-level progress the user sees no change
    # for that whole window.
    current_function: Optional[str]
    function_index: int       # 1-indexed within the current unit
    function_total: int       # number of functions in the current unit
    # Counts.
    units_total: int
    units_completed: int  # units that finished all rounds (or were abandoned)
    rounds_accepted: int  # cumulative across all units
    rounds_abandoned: int  # cumulative across all units
    # Budget consumed so far.
    elapsed_seconds: float
    tokens_used: int
    cost_usd: float
    # Termination state.
    halt_reason: Optional[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def unit_id(unit: CodeUnit) -> str:
    """Stable identifier for a code unit across rounds."""
    return f"{unit.original_path}::{unit.cell_index}"
