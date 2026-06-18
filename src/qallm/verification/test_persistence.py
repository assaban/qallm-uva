"""Test suite persistence across QALLM rounds.

Implements workflow design v3 section 4.5: how generated test suites behave
when the orchestrator visits the same code unit across multiple QALLM rounds
(each round produces a repaired variant of the same code unit).

Two orthogonal configuration axes:

1. **Test stability** (do we carry tests across variants of the same code unit?)
   * `FROZEN`: yes; once a code unit has tests, they apply to every subsequent
     variant of that code unit in the same session.
   * `PER_ROUND`: no; every QALLM round generates fresh tests, independent of
     prior rounds.

2. **Generation policy** (is the LLM allowed to produce new tests for a variant?)
   * `REPLAY_ONLY`: no; only existing persisted tests are run against new
     variants. The LLM is not called again for the same code unit.
   * `GROW`: yes; the LLM may add new tests for each new variant. Existing
     tests are preserved.

Three combinations are meaningful; one is rejected:

| Stability   | Policy        | Behaviour                                            |
|-------------|---------------|------------------------------------------------------|
| FROZEN      | REPLAY_ONLY   | Identical tests for every variant; cleanest compare. |
| FROZEN      | GROW          | Tests grow over the lineage; never replaced. (v3.)   |
| PER_ROUND   | GROW          | Each round generates fresh tests. (Current default.) |
| PER_ROUND   | REPLAY_ONLY   | Degenerate, rejected at construction.                |

The v3 default is `FROZEN` + `GROW`. This module supports all three meaningful
modes; the orchestrator chooses one at session start and it remains constant
for the session.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from qallm.verification.models import (
    GeneratedTest,
    TestGenerationSession,
)

logger = logging.getLogger(__name__)


# ---------- enums ----------


class TestStability(str, Enum):
    """Whether the test suite carries across variants of the same code unit."""
    __test__ = False  # pytest: not a test class
    FROZEN = "frozen"
    PER_ROUND = "per_round"


class GenerationPolicy(str, Enum):
    """Whether the LLM may produce new tests for a new variant."""
    REPLAY_ONLY = "replay_only"
    GROW = "grow"


@dataclass(frozen=True)
class TestStabilityConfig:
    """The two-axis configuration. Constructed once per session."""
    __test__ = False  # pytest: not a test class
    stability: TestStability = TestStability.FROZEN
    policy: GenerationPolicy = GenerationPolicy.GROW

    def __post_init__(self) -> None:
        if self.stability is TestStability.PER_ROUND and self.policy is GenerationPolicy.REPLAY_ONLY:
            raise ValueError(
                "PER_ROUND with REPLAY_ONLY is degenerate: nothing carries between "
                "rounds, so there is nothing to replay. Use FROZEN with REPLAY_ONLY "
                "if you want strict apples-to-apples comparison."
            )

    def to_dict(self) -> dict:
        return {
            "test_stability": self.stability.value,
            "generation_policy": self.policy.value,
        }

    @classmethod
    def from_strings(cls, stability: str, policy: str) -> "TestStabilityConfig":
        return cls(
            stability=TestStability(stability),
            policy=GenerationPolicy(policy),
        )


# ---------- the store ----------


# A code-unit key is (absolute_path_string, cell_index_or_minus_one, function_name).
# The minus-one default matches the convention used by `cell_index` for scripts.
CodeUnitKey = Tuple[str, int, str]


@dataclass
class StoredTest:
    """One persisted test, with provenance."""
    test_code: str
    generated_in_round: int
    is_valid: bool
    model: str
    # Keep a reference to the original GeneratedTest for serialisation; the
    # store does not modify it.
    original: GeneratedTest

    @property
    def content_hash(self) -> str:
        """Short, stable hash of the test source.

        Two regenerations with identical code share a hash (so they can be
        deduplicated); the same test name with different logic across rounds
        gets distinct hashes (so neither is silently lost). Whitespace is
        normalised so cosmetic reformatting does not change the hash.
        """
        normalised = re.sub(r"\s+", " ", self.test_code).strip()
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:8]

    @property
    def test_id(self) -> str:
        """Unique identity for this stored test within a function record.

        Round-stamped and content-hashed, so a test carried unchanged from an
        earlier round, a test regenerated with new logic under the same name,
        and a genuinely new test are all distinguishable. This is the key the
        report and the executor should use instead of (filename, test_name),
        which collapses same-named tests from different rounds.
        """
        return f"r{self.generated_in_round}_{self.content_hash}"

    def as_dict(self) -> dict:
        d = {
            "test_id": self.test_id,
            "content_hash": self.content_hash,
            "test_code": self.test_code,
            "generated_in_round": self.generated_in_round,
            "is_valid": self.is_valid,
            "model": self.model,
        }
        return d


@dataclass
class FunctionRecord:
    """All persisted state for one (code_unit, function) pair across the session."""
    function_name: str
    tests: List[StoredTest] = field(default_factory=list)
    session: Optional[TestGenerationSession] = None

    def append_test(self, generated: GeneratedTest, round_number: int) -> None:
        candidate = StoredTest(
            test_code=generated.test_code,
            generated_in_round=round_number,
            is_valid=generated.is_valid,
            model=generated.model or "unknown",
            original=generated,
        )
        # Deduplicate: if an identical test (same normalised source) was already
        # stored in an earlier round, keep the earlier one rather than adding a
        # byte-for-byte copy. This keeps the suite from inflating when a round
        # regenerates the same test verbatim. A same-named test with *different*
        # logic has a different content hash and is kept as a distinct entry.
        existing_hashes = {t.content_hash for t in self.tests}
        if candidate.content_hash in existing_hashes:
            logger.debug(
                "skip duplicate test (hash %s) regenerated in round %d",
                candidate.content_hash, round_number,
            )
            return
        self.tests.append(candidate)

    def valid_tests(self) -> List[StoredTest]:
        return [t for t in self.tests if t.is_valid]


class TestSuiteStore:
    """Per-session persistence of generated test suites.

    Keys are `(absolute_path, cell_index, function_name)`. Within a session,
    multiple QALLM rounds may visit the same key with different *variants* of
    the code (because repair changed the source). The store decides what
    happens depending on `TestStabilityConfig`.

    The store is intentionally agnostic about *how* tests are generated; the
    `VerificationManager` calls `should_generate()` to ask whether to call the
    LLM, then either calls `record_generated()` (after generating new tests)
    or uses `replay_tests()` (to get existing tests for execution against a
    new variant).
    """
    __test__ = False  # pytest: not a test class

    def __init__(self, config: TestStabilityConfig) -> None:
        self.config = config
        self._records: Dict[CodeUnitKey, FunctionRecord] = {}

    # ----- key helpers -----

    @staticmethod
    def make_key(path: Path, cell_index: int, function_name: str) -> CodeUnitKey:
        return (str(path.absolute()), cell_index, function_name)

    # ----- public API -----

    def has_record(self, key: CodeUnitKey) -> bool:
        return key in self._records

    def get_or_create_record(
        self,
        key: CodeUnitKey,
        function_name: str,
    ) -> FunctionRecord:
        if key not in self._records:
            self._records[key] = FunctionRecord(function_name=function_name)
        return self._records[key]

    def should_generate(self, key: CodeUnitKey) -> bool:
        """Whether the verifier should call the LLM for this code unit now.

        Decision matrix:
          FROZEN + REPLAY_ONLY: generate iff no existing tests (only round 0).
          FROZEN + GROW:        always generate (and accumulate).
          PER_ROUND + GROW:     always generate (fresh tests each round).
          PER_ROUND + REPLAY_ONLY: rejected at config time.
        """
        cfg = self.config
        if cfg.stability is TestStability.FROZEN and cfg.policy is GenerationPolicy.REPLAY_ONLY:
            record = self._records.get(key)
            return record is None or not record.valid_tests()
        # GROW always generates
        return True

    def carries_tests(self) -> bool:
        """Whether tests from prior rounds apply to new variants."""
        return self.config.stability is TestStability.FROZEN

    def replay_tests(self, key: CodeUnitKey) -> List[StoredTest]:
        """All previously-stored valid tests for this code unit.

        Returns an empty list if there are no stored tests yet. Callers should
        only invoke this when `carries_tests()` is true; under PER_ROUND, the
        store is reset every round (see `clear_for_round`).
        """
        record = self._records.get(key)
        if record is None:
            return []
        return record.valid_tests()

    def record_generated(
        self,
        key: CodeUnitKey,
        function_name: str,
        generated: GeneratedTest,
        round_number: int,
    ) -> None:
        record = self.get_or_create_record(key, function_name)
        record.append_test(generated, round_number)

    def attach_session(self, key: CodeUnitKey, session: TestGenerationSession) -> None:
        record = self._records.get(key)
        if record is None:
            raise KeyError(f"No record for {key}; record_generated must be called first")
        record.session = session

    def get_session(self, key: CodeUnitKey) -> Optional[TestGenerationSession]:
        record = self._records.get(key)
        return record.session if record else None

    def all_sessions(self) -> List[TestGenerationSession]:
        return [r.session for r in self._records.values() if r.session is not None]

    def clear_for_round(self) -> None:
        """Drop all stored tests. Called between QALLM rounds under PER_ROUND.

        Sessions are *not* dropped (they remain part of the historical log);
        only the tests-to-replay are cleared.
        """
        if self.config.stability is not TestStability.PER_ROUND:
            logger.debug("clear_for_round called under non-PER_ROUND mode; no-op")
            return
        for record in self._records.values():
            record.tests = []

    # ----- persistence -----

    def save(self, output_dir: Path) -> Path:
        """Write a JSON snapshot of the store to disk.

        The on-disk format is keyed by `str(path)::cell::function` so it can be
        re-read by tooling that does not have access to the original Python
        tuples.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        out: Dict[str, dict] = {}
        for (path, cell, func), record in self._records.items():
            disk_key = f"{path}::{cell}::{func}"
            out[disk_key] = {
                "function_name": record.function_name,
                "tests": [t.as_dict() for t in record.tests],
                "session": (
                    {
                        **asdict(record.session),
                        "final_coverage": record.session.final_coverage,
                        "final_bugs": record.session.final_bugs,
                        "learning_curve": record.session.learning_curve,
                    }
                    if record.session is not None
                    else None
                ),
            }
        path = output_dir / "test_suite_store.json"
        path.write_text(
            json.dumps(
                {
                    "config": self.config.to_dict(),
                    "records": out,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return path

    def summary(self) -> dict:
        """A small summary suitable for inclusion in the session-level summary.json."""
        return {
            **self.config.to_dict(),
            "code_units_with_tests": sum(
                1 for r in self._records.values() if r.valid_tests()
            ),
            "total_tests_stored": sum(
                len(r.valid_tests()) for r in self._records.values()
            ),
        }
