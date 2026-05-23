"""Quality reporter: persists session artefacts per workflow design v3 section 10.

Directory layout for one session::

    session_dir/
    ├── summary.json              # canonical, written by orchestrator
    ├── report.md                 # human view (NEW-07; via qallm.utils.views)
    ├── report.html               # human view (NEW-07; via qallm.utils.views)
    ├── round_00_baseline/        # original code static analysis only
    │   └── <file>_static.json
    ├── lineage/
    │   ├── round_01/
    │   │   ├── source.py
    │   │   ├── static.json
    │   │   ├── verification.json
    │   │   ├── profile.json
    │   │   ├── judge.json        # null on round 1 (no parent)
    │   │   └── tests/
    │   │       ├── test_<func1>.py
    │   │       └── test_<func2>.py
    │   └── round_02/...
    └── abandoned/
        └── round_02/...          # same shape as lineage/round_N/

A round directory holds EXACTLY one variant's full provenance. The
choice of `lineage/` vs `abandoned/` is the judge's decision (round 1
always goes to lineage). Both directories have the same shape, so
downstream tooling can iterate uniformly.

API
---

The reporter has two write entry points used by the orchestrator:

* :meth:`save_baseline` once per session, before round 1, with the
  original code's static analysis.
* :meth:`save_round_artefacts` once per code unit per round, with
  everything for that variant. Takes ``accepted: bool`` to route into
  ``lineage/`` or ``abandoned/``.

The old `save_static_report`, `save_static_repair_artifacts`, and
`save_verification_artifacts` methods are gone (the orchestrator's
only caller is updated). If a future caller needs the legacy layout,
build it on top of the new API.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from qallm.analysis.analysis_model import AnalysedCodeUnit
from qallm.common.model import CodeUnit
from qallm.evaluation import ProfileVerdict
from qallm.verification.models import TestedCodeUnit, TestGenerationSession


def _json_serialise(obj: Any) -> Any:
    """Best-effort JSON serialiser for dataclasses, paths, sets, enums."""
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (set, Path)):
        return str(obj)
    # str fallback covers enums by .value via their __str__; safer than failing.
    return str(obj)


class QualityReporter:
    """Persists session artefacts to disk in the v3 layout.

    Each :class:`QualityReporter` instance owns one session directory.
    The orchestrator constructs one per run.
    """

    def __init__(self, base_dir: str = "outputs/reports", run_id: Optional[str] = None) -> None:
        # Allow run_id override for deterministic test directories; default
        # to a timestamp so concurrent sessions don't collide.
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.report_dir = Path(base_dir) / self.run_id
        self.report_dir.mkdir(parents=True, exist_ok=True)

    # ----- baseline -----

    def save_baseline(self, analysed: AnalysedCodeUnit) -> Path:
        """Save round-0 baseline: static analysis only, no verification.

        Returns the directory the artefacts were written to.
        """
        baseline_dir = self.report_dir / "round_00_baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        stem = analysed.code_unit.original_path.stem
        target = baseline_dir / f"{stem}_static.json"
        target.write_text(
            json.dumps(analysed.findings, indent=2, default=_json_serialise),
            encoding="utf-8",
        )
        return baseline_dir

    # ----- per-round, per-unit -----

    def save_round_artefacts(
        self,
        *,
        round_number: int,
        unit_id: str,
        code_unit: CodeUnit,
        analysed: AnalysedCodeUnit,
        tested: TestedCodeUnit,
        profile_verdict: ProfileVerdict,
        judge_verdict_dict: Optional[dict],
        accepted: bool,
    ) -> Path:
        """Write the full provenance bundle for one variant.

        Args:
            round_number: 1-indexed QALLM round.
            unit_id: stable identifier (e.g. ``{path}::{cell_index}``).
            code_unit: the variant whose source is saved as ``source.py``.
            analysed: static analysis findings to save as ``static.json``.
            tested: verification output (sessions) saved as ``verification.json``
                plus per-function test files under ``tests/``.
            profile_verdict: the EVERSE profile verdict saved as ``profile.json``.
            judge_verdict_dict: the judge's structured verdict; None on round 1
                where no judgement was made.
            accepted: True routes into ``lineage/``, False into ``abandoned/``.

        Returns the directory written to.
        """
        bucket = "lineage" if accepted else "abandoned"
        # Per-unit subdirectories let multi-unit sessions co-exist within
        # lineage/round_N/ without filename collisions.
        round_dir = (
            self.report_dir / bucket
            / f"round_{round_number:02d}"
            / _safe_unit_segment(unit_id)
        )
        round_dir.mkdir(parents=True, exist_ok=True)

        # 1. source.py
        (round_dir / "source.py").write_text(code_unit.source_code, encoding="utf-8")

        # 2. static.json
        (round_dir / "static.json").write_text(
            json.dumps(analysed.findings, indent=2, default=_json_serialise),
            encoding="utf-8",
        )

        # 3. verification.json
        sessions_data = [
            _session_dict(s) for s in tested.sessions
        ]
        (round_dir / "verification.json").write_text(
            json.dumps(sessions_data, indent=2, default=_json_serialise),
            encoding="utf-8",
        )

        # 4. profile.json
        (round_dir / "profile.json").write_text(
            json.dumps(profile_verdict.to_dict(), indent=2, default=_json_serialise),
            encoding="utf-8",
        )

        # 5. judge.json (null payload on round 1)
        (round_dir / "judge.json").write_text(
            json.dumps(judge_verdict_dict, indent=2, default=_json_serialise),
            encoding="utf-8",
        )

        # 6. tests/  one file per function session, latest valid test only
        tests_dir = round_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        for session in tested.sessions:
            if not session.rounds:
                continue
            last = session.rounds[-1]
            if not last.generated_test.is_valid:
                continue
            (tests_dir / f"test_{session.function_name}.py").write_text(
                last.generated_test.test_code, encoding="utf-8"
            )

        return round_dir


# ----- helpers -----


def _safe_unit_segment(unit_id: str) -> str:
    """Render a unit identifier as a single safe directory segment.

    A unit id is typically ``"<path>::<cell_index>"``; we replace the
    separators that browsers and filesystems treat specially.
    """
    return (
        unit_id
        .replace("/", "__")
        .replace("\\", "__")
        .replace(":", "_")
        .replace(" ", "_")
    )


def _session_dict(session: TestGenerationSession) -> dict:
    """Snapshot a verification session including its computed properties."""
    d = asdict(session)
    d["final_coverage"] = session.final_coverage
    d["final_bugs"] = session.final_bugs
    d["final_pass_rate"] = session.final_pass_rate
    d["learning_curve"] = session.learning_curve
    return d
