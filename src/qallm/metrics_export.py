"""Export QALLM's execution-based metrics in a citable, reproducible form.

The three headline metrics (verification gap, confirmation rate, verified-fix
rate) live in the UI, computed on demand. For the thesis they need to exist
as durable, machine-readable records: one per session, and aggregated across
many sessions. This module produces both, as plain dicts that the API
serialises to JSON and flattens to CSV.

A per-session export carries:
* run metadata (model, oracle, rounds, cost, profile), from summary.json.
* the verification-gap figures, derived from the per-round gap reports
  (always available, computed from persisted artefacts).
* the confirmation and verified-fix figures, IF those on-demand actions were
  run and recorded; otherwise null, never a misleading zero.

Honesty rules, carried over from the UI:
* rates are null when their denominator is zero (nothing was testable), not
  0.0, so an absent measurement is never read as a measured absence.
* the verification-gap rate counts only execution-found defects; errored and
  discarded tests are already excluded upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionMetrics:
    session_id: str
    model: str = ""
    testgen_model: str = ""
    oracle: str = ""
    rounds: int = 0
    units_analyzed: int = 0
    functions_verified: int = 0
    incoherent_oracles_dropped: int = 0  # generated-test quality (MD-002)
    cost_usd: float = 0.0
    tokens: int = 0
    # Verification gap (from gap reports, always available post-run).
    static_findings: int = 0
    confirmed_findings: int = 0  # findings execution corroborated (function-level)
    execution_only_bugs: int = 0
    verification_gap_rate: float | None = None
    # Confirmation (only if confirm/refute was run and recorded).
    confirmed: int | None = None
    # The confirmed total splits into two sources kept distinct for RQ2:
    # static-finding confirmations (security findings execution corroborated)
    # and reliability-gap confirmations (execution-only defects, confirmed by
    # construction because their test failed on the original code). Reporting a
    # single blended confirmed count hides that the reliability confirmations
    # dominate and that a raw confirmation rate is degenerate.
    confirmed_static: int | None = None
    confirmed_reliability_gap: int | None = None
    refuted: int | None = None
    confirmation_rate: float | None = None
    # Confirm/refute outcomes that are neither confirmed nor refuted, surfaced
    # so RQ2 is legible: an "inconclusive" (the targeted test errored or was
    # invalid) or "not_execution_testable" (a non-runtime finding type, e.g.
    # complexity) is not the same as "no findings". Without these, a run where
    # every finding came back inconclusive looks identical to a run with nothing
    # to confirm, which is misleading.
    inconclusive: int | None = None
    not_execution_testable: int | None = None
    # Verified-fix (only if verify-fixes was run and recorded).
    verified_fixed: int | None = None
    not_fixed: int | None = None
    verified_fix_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "model": self.model,
            "testgen_model": self.testgen_model,
            "oracle": self.oracle,
            "rounds": self.rounds,
            "units_analyzed": self.units_analyzed,
            "functions_verified": self.functions_verified,
            "incoherent_oracles_dropped": self.incoherent_oracles_dropped,
            "cost_usd": round(self.cost_usd, 6),
            "tokens": self.tokens,
            "static_findings": self.static_findings,
            "execution_only_bugs": self.execution_only_bugs,
            "verification_gap_rate": self.verification_gap_rate,
            "confirmed": self.confirmed,
            "confirmed_static": self.confirmed_static,
            "confirmed_reliability_gap": self.confirmed_reliability_gap,
            "refuted": self.refuted,
            "confirmation_rate": self.confirmation_rate,
            "inconclusive": self.inconclusive,
            "not_execution_testable": self.not_execution_testable,
            "verified_fixed": self.verified_fixed,
            "not_fixed": self.not_fixed,
            "verified_fix_rate": self.verified_fix_rate,
        }


# Stable column order for CSV; mirrors to_dict so the two never drift.
CSV_COLUMNS: list[str] = [
    "session_id", "model", "testgen_model", "oracle", "rounds",
    "units_analyzed", "functions_verified", "cost_usd", "tokens",
    "incoherent_oracles_dropped",
    "static_findings", "execution_only_bugs", "verification_gap_rate",
    "confirmed", "confirmed_static", "confirmed_reliability_gap",
    "refuted", "confirmation_rate",
    "inconclusive", "not_execution_testable",
    "verified_fixed", "not_fixed", "verified_fix_rate",
]


def _rate(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator > 0 else None


def build_session_metrics(
    session_id: str,
    summary: dict | None,
    gap_rounds: list[dict],
    confirm_summary: dict | None = None,
    verify_summary: dict | None = None,
) -> SessionMetrics:
    """Assemble one session's metrics from its summary and gap data.

    ``gap_rounds`` is the list of per-round gap dicts (each with a "summary").
    ``confirm_summary`` / ``verify_summary`` are the summary dicts from the
    confirm-findings / verify-fixes endpoints, when those were run.
    """
    summary = summary or {}
    cost = summary.get("cost") or {}

    m = SessionMetrics(
        session_id=session_id,
        model=summary.get("model", ""),
        testgen_model=summary.get("testgen_model", ""),
        oracle=summary.get("oracle", ""),
        rounds=int(summary.get("rounds_per_function", 0) or 0),
        units_analyzed=int(summary.get("units_analyzed", 0) or 0),
        functions_verified=int(summary.get("functions_verified", 0) or 0),
        incoherent_oracles_dropped=int(
            summary.get("incoherent_oracles_dropped", 0) or 0
        ),
        cost_usd=float(cost.get("total_cost_usd", 0.0) or 0.0),
        tokens=int(cost.get("total_tokens", 0) or 0),
    )

    # Verification gap: a property of the ORIGINAL code (round 0). Use the
    # round-0 gap report only, not a sum across rounds. Summing double-counted
    # the same functions and folded in repair-round test noise, which on clean
    # code produced false-positive "bugs" (the lab clean_control case). Round 0
    # is the baseline pass over the original code, exactly what the gap asks
    # about; repair rounds inform RQ3 (verified fixes), not the gap count.
    def _round_no(r: dict) -> int:
        return int(r.get("round", r.get("round_number", 0)) or 0)

    baseline_round = None
    if gap_rounds:
        baseline_round = min(gap_rounds, key=_round_no)
    if baseline_round is not None:
        exec_only = int(baseline_round.get("summary", {}).get("execution_only", 0) or 0)
        confirmed_findings = int(
            baseline_round.get("summary", {}).get("confirmed", 0) or 0
        )
        findings = len(baseline_round.get("findings", []) or [])
    else:
        exec_only = 0
        confirmed_findings = 0
        findings = 0
    m.static_findings = findings
    m.confirmed_findings = confirmed_findings
    m.execution_only_bugs = exec_only
    m.verification_gap_rate = _rate(exec_only, confirmed_findings + exec_only)

    if confirm_summary:
        m.confirmed = int(confirm_summary.get("confirmed", 0) or 0)
        m.confirmed_static = int(confirm_summary.get("confirmed_static", 0) or 0)
        m.confirmed_reliability_gap = int(
            confirm_summary.get("confirmed_reliability_gap", 0) or 0)
        m.refuted = int(confirm_summary.get("refuted", 0) or 0)
        m.confirmation_rate = confirm_summary.get("confirmation_rate")
        m.inconclusive = int(confirm_summary.get("inconclusive", 0) or 0)
        m.not_execution_testable = int(
            confirm_summary.get("not_execution_testable", 0) or 0
        )

    if verify_summary:
        m.verified_fixed = int(verify_summary.get("verified_fixed", 0) or 0)
        m.not_fixed = int(verify_summary.get("not_fixed", 0) or 0)
        m.verified_fix_rate = verify_summary.get("verified_fix_rate")

    return m


@dataclass
class AggregateMetrics:
    """Cross-session roll-up. Rates are recomputed from summed counts, not
    averaged, so a session with one finding does not weigh the same as a
    session with fifty (count-weighted, the correct aggregation for rates)."""
    n_sessions: int = 0
    total_static_findings: int = 0
    total_confirmed_findings: int = 0
    total_execution_only_bugs: int = 0
    total_confirmed: int = 0
    total_confirmed_static: int = 0
    total_confirmed_reliability_gap: int = 0
    total_refuted: int = 0
    total_inconclusive: int = 0
    total_not_execution_testable: int = 0
    total_verified_fixed: int = 0
    total_not_fixed: int = 0
    total_cost_usd: float = 0.0
    per_session: list[dict] = field(default_factory=list)
    # Per-session (numerator, denominator) pairs for each rate, captured from
    # the typed SessionMetrics so the bootstrap CI does not depend on the
    # lossy per-session dict (which omits some counts).
    _gap_pairs: list[tuple[int, int]] = field(default_factory=list)
    _conf_pairs: list[tuple[int, int]] = field(default_factory=list)
    _fix_pairs: list[tuple[int, int]] = field(default_factory=list)

    @property
    def verification_gap_rate(self) -> float | None:
        # execution-only over all execution-found defects at the function
        # level (confirmed findings + execution-only).
        return _rate(self.total_execution_only_bugs,
                     self.total_confirmed_findings + self.total_execution_only_bugs)

    @property
    def confirmation_rate(self) -> float | None:
        return _rate(self.total_confirmed,
                     self.total_confirmed + self.total_refuted)

    @property
    def verified_fix_rate(self) -> float | None:
        return _rate(self.total_verified_fixed,
                     self.total_verified_fixed + self.total_not_fixed)

    def confidence_intervals(self) -> dict[str, Any]:
        """Bootstrap 95% CIs for the three rates, resampling by session.

        Sessions are the independent unit (findings cluster within them), so
        the CI is computed by resampling sessions with replacement and
        recomputing each pooled rate. Gives the headline figures an interval
        rather than a bare point estimate.
        """
        from qallm.stats import bootstrap_rate_ci

        gap_num = [p[0] for p in self._gap_pairs]
        gap_den = [p[1] for p in self._gap_pairs]
        conf_num = [p[0] for p in self._conf_pairs]
        conf_den = [p[1] for p in self._conf_pairs]
        fix_num = [p[0] for p in self._fix_pairs]
        fix_den = [p[1] for p in self._fix_pairs]

        return {
            "verification_gap_rate": bootstrap_rate_ci(gap_num, gap_den),
            "confirmation_rate": bootstrap_rate_ci(conf_num, conf_den),
            "verified_fix_rate": bootstrap_rate_ci(fix_num, fix_den),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_sessions": self.n_sessions,
            "total_static_findings": self.total_static_findings,
            "total_execution_only_bugs": self.total_execution_only_bugs,
            "verification_gap_rate": self.verification_gap_rate,
            "total_confirmed": self.total_confirmed,
            "total_confirmed_static": self.total_confirmed_static,
            "total_confirmed_reliability_gap": self.total_confirmed_reliability_gap,
            "total_refuted": self.total_refuted,
            "total_inconclusive": self.total_inconclusive,
            "total_not_execution_testable": self.total_not_execution_testable,
            "confirmation_rate": self.confirmation_rate,
            "total_verified_fixed": self.total_verified_fixed,
            "total_not_fixed": self.total_not_fixed,
            "verified_fix_rate": self.verified_fix_rate,
            "confidence_intervals": self.confidence_intervals(),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "per_session": self.per_session,
        }


def aggregate_sessions(sessions: list[SessionMetrics]) -> AggregateMetrics:
    """Roll up many sessions, recomputing rates from summed counts."""
    agg = AggregateMetrics(n_sessions=len(sessions))
    for s in sessions:
        agg.total_static_findings += s.static_findings
        agg.total_confirmed_findings += s.confirmed_findings
        agg.total_execution_only_bugs += s.execution_only_bugs
        agg.total_confirmed += (s.confirmed or 0)
        agg.total_confirmed_static += (s.confirmed_static or 0)
        agg.total_confirmed_reliability_gap += (s.confirmed_reliability_gap or 0)
        agg.total_refuted += (s.refuted or 0)
        agg.total_inconclusive += (s.inconclusive or 0)
        agg.total_not_execution_testable += (s.not_execution_testable or 0)
        agg.total_verified_fixed += (s.verified_fixed or 0)
        agg.total_not_fixed += (s.not_fixed or 0)
        agg.total_cost_usd += s.cost_usd
        agg.per_session.append(s.to_dict())
        # Capture per-session (numerator, denominator) for the bootstrap CIs.
        eo, cf = s.execution_only_bugs, s.confirmed_findings
        agg._gap_pairs.append((eo, eo + cf))
        c, r = (s.confirmed or 0), (s.refuted or 0)
        agg._conf_pairs.append((c, c + r))
        vf, nf = (s.verified_fixed or 0), (s.not_fixed or 0)
        agg._fix_pairs.append((vf, vf + nf))
    return agg


def to_csv(sessions: list[SessionMetrics]) -> str:
    """Flatten per-session metrics to CSV text with a stable header."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for s in sessions:
        writer.writerow(s.to_dict())
    return buf.getvalue()
