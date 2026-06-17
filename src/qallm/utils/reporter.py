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
import uuid
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

    def __init__(
        self,
        base_dir: str = "outputs/reports",
        run_id: Optional[str] = None,
        artefact_retention: str = "full",
        origin: str = "experiment",
    ) -> None:
        # origin distinguishes how this session was created, so the web Sessions
        # library can show only interactive runs and not be swamped by the
        # thousands of per-unit directories a large dataset experiment produces.
        #   "interactive" : started from the web UI (upload/analyse/run).
        #   "experiment"  : produced by the batch runner (scripts/run_gap_*).
        # The web layer passes origin="interactive"; the runner uses the default.
        self.origin = origin
        # Allow run_id override for deterministic test directories. The default
        # is "{timestamp}_{short-uuid}", the same shape the web upload/analyse
        # paths use, so every session directory has a consistent name and two
        # sessions started in the same second never collide (a plain timestamp
        # collided when several runs launched together).
        self.run_id = run_id or (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        )
        self.report_dir = Path(base_dir) / self.run_id
        # Artefact retention controls how much per-round provenance is written.
        #   "full"         : write every variant's source/static/verification/
        #                    tests under lineage/ and abandoned/ (default; best
        #                    for interactive single runs and deep inspection).
        #   "metrics_only" : skip those per-unit round directories (the bulk of
        #                    the disk footprint on large batch runs) but still
        #                    accumulate the gap data in memory so the gap rate
        #                    remains computable from summary.json. Use for big
        #                    dataset experiments where per-file provenance for
        #                    thousands of units is neither needed nor wanted.
        if artefact_retention not in ("full", "metrics_only"):
            raise ValueError(
                f"artefact_retention must be 'full' or 'metrics_only', "
                f"got {artefact_retention!r}"
            )
        self.artefact_retention = artefact_retention
        # Gap rounds accumulated in memory when retention skips disk artefacts.
        self.gap_rounds: list[dict] = []
        # The directory is created lazily, on the first artefact write, NOT
        # here. Constructing a reporter (which the orchestrator does in its
        # own constructor) must not leave an empty session directory on disk
        # if the run never produces anything, e.g. an ingest-only probe or a
        # run that fails before the baseline. Every write path calls
        # _ensure_dir() first.

    def _ensure_dir(self) -> None:
        """Create the session directory on first use. Idempotent."""
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def _accumulate_gap_round(self, round_dict: dict) -> None:
        """Merge one unit's gap report into the in-memory per-round totals.

        Used in metrics_only retention, where per-unit round directories are
        not written. Multiple units can contribute to the same round, so
        findings and execution-only functions are merged by round number,
        matching how compute_gap_rounds_from_dir merges across unit
        subdirectories on disk.
        """
        rno = round_dict.get("round")
        existing = next((r for r in self.gap_rounds if r.get("round") == rno), None)
        if existing is None:
            self.gap_rounds.append(round_dict)
            return
        existing.setdefault("findings", []).extend(round_dict.get("findings", []))
        eo = existing.setdefault("execution_only_functions", [])
        eo.extend(round_dict.get("execution_only_functions", []))
        existing["execution_only_functions"] = sorted(set(eo))
        # Refresh the summary counts to match the merged lists.
        summary = existing.setdefault("summary", {})
        summary["execution_only"] = len(existing["execution_only_functions"])

    # ----- baseline -----

    def save_baseline(self, analysed: AnalysedCodeUnit) -> Path:
        """Save round-0 baseline: static analysis only, no verification.

        Returns the directory the artefacts were written to.
        """
        self._ensure_dir()
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
        improvement_dict: Optional[dict] = None,
        transcript_records: Optional[list] = None,
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
        self._ensure_dir()
        bucket = "lineage" if accepted else "abandoned"

        if self.artefact_retention == "metrics_only":
            # Skip the per-unit round directory (the bulk of the disk
            # footprint), but still compute the gap data this round would
            # have contributed, so the gap rate stays computable from
            # summary.json without re-reading any files. Mirrors exactly what
            # compute_gap_rounds_from_dir would derive from the on-disk
            # source.py/static.json/verification.json for this unit.
            from qallm.analysis.gap_analysis import build_gap_report
            verification = [_session_dict(s) for s in tested.sessions]
            unit_report = build_gap_report(
                round_number, code_unit.source_code, analysed.findings, verification
            )
            self._accumulate_gap_round(unit_report.to_dict())
            return self.report_dir
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

        # 5b. improvement.json: per-indicator parent-vs-variant deltas, the
        # audit trail for "did quality improve this round". Optional so
        # older callers/tests that don't compute it still work.
        if improvement_dict is not None:
            (round_dir / "improvement.json").write_text(
                json.dumps(improvement_dict, indent=2, default=_json_serialise),
                encoding="utf-8",
            )

        # 5c. transcript.json: every LLM prompt/response made for this unit
        # this round (repair + test generation). The provenance that lets a
        # reviewer see exactly what was asked and what came back.
        if transcript_records is not None:
            (round_dir / "transcript.json").write_text(
                json.dumps(transcript_records, indent=2, default=_json_serialise),
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
    """Render a unit identifier as a clean, short directory segment.

    A unit id has the shape ``"<path>::<cell_index>"`` (the orchestrator's
    ``_unit_id`` helper constructs it). The previous version of this
    function escaped every path separator and produced verbose names like
    ``__var__folders__7z__yc4nm0ls6rg1gxbpqyg7frkmzzshkp__T__heval_Python_16_8o3xor8a__count_distinct_characters.py__0``
    when the source lived under a system temp directory.

    The path's full hierarchy adds nothing useful to the artefact tree:
    the source is already saved as ``source.py`` inside the round dir.
    What identifies a unit uniquely within a session is ``<basename>::<cell_index>``,
    which is much shorter and human-readable.

    Examples::

        "/var/folders/7z/.../count_distinct_characters.py::0"  ->  "count_distinct_characters.py__0"
        "demo.py::3"                                            ->  "demo.py__3"
        "C:\\Users\\foo\\bar.ipynb::2"                          ->  "bar.ipynb__2"

    Collisions are theoretically possible if two units share the same
    basename and cell_index (e.g. two notebooks named ``test.ipynb`` with
    a cell_index 0). In practice this doesn't happen within one session
    because the ingestion manager normalises notebook cells with unique
    indices. We document the constraint rather than work around it.
    """
    # Split on the conventional "::" separator; tolerant of inputs that
    # don't follow the convention (returns the whole thing as the path).
    if "::" in unit_id:
        path_part, _, cell_part = unit_id.rpartition("::")
    else:
        path_part, cell_part = unit_id, "0"

    # Take just the basename, agnostic to OS path separator.
    basename = path_part.replace("\\", "/").rsplit("/", 1)[-1]
    if not basename:
        basename = "unit"

    # Sanitise the cell_part: it's normally a number but be defensive.
    cell_part = (
        cell_part.replace("/", "_").replace("\\", "_")
        .replace(":", "_").replace(" ", "_")
    )
    return f"{basename}__{cell_part}"


def _session_dict(session: TestGenerationSession) -> dict:
    """Snapshot a verification session including its computed properties."""
    d = asdict(session)
    d["final_coverage"] = session.final_coverage
    d["final_bugs"] = session.final_bugs
    d["final_pass_rate"] = session.final_pass_rate
    d["learning_curve"] = session.learning_curve
    return d
