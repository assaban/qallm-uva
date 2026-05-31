import { useState, useEffect } from "react";
import { ShieldCheck, ShieldAlert, ShieldQuestion, Zap, Microscope, Loader2, BadgeCheck } from "lucide-react";
import * as api from "../api";
import type { GapRound, FindingStatus, FindingVerdictRow, FindingVerdict, FixResultRow, FixVerdict } from "../api";

// The static-vs-execution gap, per round: how many static findings
// execution confirmed, could not reproduce, or could not test, and the
// execution-found bugs no static tool flagged (the verification gap).
export default function GapPanel({ sessionId }: { sessionId: string }) {
  const [rounds, setRounds] = useState<GapRound[]>([]);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  // Confirm/refute: an explicit action (it makes LLM calls), so it runs on
  // demand rather than on load.
  const [confirming, setConfirming] = useState(false);
  const [verdicts, setVerdicts] = useState<FindingVerdictRow[] | null>(null);
  const [confirmSummary, setConfirmSummary] = useState<api.ConfirmFindingsResponse["summary"] | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const runConfirm = () => {
    setConfirming(true);
    setConfirmError(null);
    api.confirmFindings(sessionId)
      .then(res => {
        if (res.available) {
          setVerdicts(res.verdicts);
          setConfirmSummary(res.summary ?? null);
        } else {
          setConfirmError(res.reason ?? "Not available.");
        }
      })
      .catch(() => setConfirmError("Confirm/refute failed."))
      .finally(() => setConfirming(false));
  };

  // Verified-fix loop: re-run confirmed findings' reproducing tests against
  // the repaired code to prove the defect is gone. Pure execution, no LLM.
  const [verifying, setVerifying] = useState(false);
  const [fixResults, setFixResults] = useState<FixResultRow[] | null>(null);
  const [fixSummary, setFixSummary] = useState<api.VerifyFixesResponse["summary"] | null>(null);
  const [fixError, setFixError] = useState<string | null>(null);

  const confirmedFindings = (verdicts ?? []).filter(v => v.verdict === "confirmed");

  const runVerifyFixes = () => {
    setVerifying(true);
    setFixError(null);
    api.verifyFixes(sessionId, confirmedFindings)
      .then(res => {
        if (res.available) {
          setFixResults(res.results);
          setFixSummary(res.summary ?? null);
        } else {
          setFixError(res.reason ?? "Not available.");
        }
      })
      .catch(() => setFixError("Verify-fixes failed."))
      .finally(() => setVerifying(false));
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getGap(sessionId)
      .then(res => {
        if (!alive) return;
        if (res.available) setRounds(res.rounds);
        else setReason(res.reason ?? "Not available yet.");
      })
      .catch(() => alive && setReason("Could not load the gap analysis."))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [sessionId]);

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white/70 p-6 text-sm text-slate-400">Loading gap analysis...</div>;
  }
  if (reason) {
    return <div className="rounded-2xl border border-slate-200 bg-white/70 p-6 text-sm text-slate-400">{reason}</div>;
  }
  if (rounds.length === 0) return null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 p-6 shadow-sm">
      <div className="flex items-center gap-2">
        <Zap className="h-5 w-5 text-indigo-600" />
        <h2 className="text-xl font-semibold text-slate-800">Static analysis vs execution</h2>
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Static findings are hypotheses; execution is the judge. For each round: which static findings execution confirmed, which it could not reproduce (candidate false positives), which it could not test, and the bugs execution found that no static tool flagged, the verification gap.
      </p>

      <div className="mt-4 space-y-4">
        {rounds.map(r => <GapRoundCard key={r.round} round={r} />)}
      </div>

      {/* Per-finding confirm/refute: sharpens the function-level gap above to
          individual findings by generating a targeted test for each. */}
      <div className="mt-6 border-t border-slate-100 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <Microscope className="h-4 w-4 text-indigo-600" /> Confirm or refute each finding
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Generates a targeted test per finding to reproduce its defect. Reliability findings are confirmed when a correctness test fails; security findings when an exploit test passes. Complexity and maintainability findings are not execution-testable.
            </p>
          </div>
          <button
            onClick={runConfirm}
            disabled={confirming}
            className="flex shrink-0 items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {confirming ? <><Loader2 className="h-4 w-4 animate-spin" /> Running...</> : <>Run confirm/refute</>}
          </button>
        </div>

        {confirmError && <div className="mt-3 text-xs text-rose-600">{confirmError}</div>}

        {confirmSummary && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <Stat icon={<ShieldCheck className="h-3.5 w-3.5" />} label="confirmed" value={confirmSummary.confirmed} tone="emerald" />
            <Stat icon={<ShieldQuestion className="h-3.5 w-3.5" />} label="refuted" value={confirmSummary.refuted} tone="amber" />
            <Stat icon={<ShieldAlert className="h-3.5 w-3.5" />} label="inconclusive" value={confirmSummary.inconclusive} tone="slate" />
            <Stat icon={<ShieldAlert className="h-3.5 w-3.5" />} label="not testable" value={confirmSummary.not_execution_testable} tone="slate" />
            {confirmSummary.confirmation_rate !== null && (
              <span className="text-slate-500">rate: <span className="font-semibold text-slate-700">{(confirmSummary.confirmation_rate * 100).toFixed(0)}%</span></span>
            )}
          </div>
        )}

        {verdicts && verdicts.length > 0 && (
          <div className="mt-3 space-y-2">
            {verdicts.map((v, i) => <VerdictCard key={i} v={v} />)}
          </div>
        )}

        {/* Verified-fix loop: once findings are confirmed, prove the repair
            actually fixed them by re-running the reproducing tests against
            the repaired code. */}
        {confirmedFindings.length > 0 && (
          <div className="mt-5 border-t border-slate-100 pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <BadgeCheck className="h-4 w-4 text-emerald-600" /> Prove the fixes
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  Re-runs each confirmed finding's reproducing test against the repaired code. A fix is verified when the test that demonstrated the defect now shows it is gone. Pure execution, no model calls.
                </p>
              </div>
              <button
                onClick={runVerifyFixes}
                disabled={verifying}
                className="flex shrink-0 items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-50"
              >
                {verifying ? <><Loader2 className="h-4 w-4 animate-spin" /> Verifying...</> : <>Verify fixes ({confirmedFindings.length})</>}
              </button>
            </div>

            {fixError && <div className="mt-3 text-xs text-rose-600">{fixError}</div>}

            {fixSummary && (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <Stat icon={<BadgeCheck className="h-3.5 w-3.5" />} label="verified fixed" value={fixSummary.verified_fixed} tone="emerald" />
                <Stat icon={<ShieldAlert className="h-3.5 w-3.5" />} label="not fixed" value={fixSummary.not_fixed} tone="amber" />
                <Stat icon={<ShieldAlert className="h-3.5 w-3.5" />} label="inconclusive" value={fixSummary.inconclusive} tone="slate" />
                {fixSummary.verified_fix_rate !== null && (
                  <span className="text-slate-500">verified-fix rate: <span className="font-semibold text-slate-700">{(fixSummary.verified_fix_rate * 100).toFixed(0)}%</span></span>
                )}
              </div>
            )}

            {fixResults && fixResults.length > 0 && (
              <div className="mt-3 space-y-2">
                {fixResults.map((r, i) => <FixCard key={i} r={r} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FixCard({ r }: { r: FixResultRow }) {
  return (
    <div className="rounded-lg border border-slate-100 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <FixBadge verdict={r.fix_verdict} />
        <span className="text-slate-600">{r.tool}</span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">{r.type}</span>
        <span className="text-slate-400">·</span>
        <span className="font-mono text-slate-500">L{r.line}</span>
        {r.function && <><span className="text-slate-400">·</span><span className="font-mono text-slate-700">{r.function}</span></>}
      </div>
      <div className="mt-1 text-slate-600">{r.message}</div>
      <div className="mt-1 italic text-slate-500">{r.reason}</div>
    </div>
  );
}

function FixBadge({ verdict }: { verdict: FixVerdict }) {
  const map: Record<FixVerdict, { label: string; cls: string }> = {
    verified_fixed: { label: "verified fixed", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
    not_fixed: { label: "not fixed", cls: "text-amber-700 bg-amber-50 border-amber-200" },
    inconclusive: { label: "inconclusive", cls: "text-slate-600 bg-slate-50 border-slate-200" },
  };
  const m = map[verdict];
  return <span className={`rounded border px-1.5 py-0.5 font-medium ${m.cls}`}>{m.label}</span>;
}

function VerdictCard({ v }: { v: FindingVerdictRow }) {
  const [showTest, setShowTest] = useState(false);
  return (
    <div className="rounded-lg border border-slate-100 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={v.verdict} />
        <span className="text-slate-600">{v.tool}</span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">{v.type}</span>
        <span className="text-slate-400">·</span>
        <span className="font-mono text-slate-500">L{v.line}</span>
        {v.function && <><span className="text-slate-400">·</span><span className="font-mono text-slate-700">{v.function}</span></>}
      </div>
      <div className="mt-1 text-slate-600">{v.message}</div>
      <div className="mt-1 text-slate-500 italic">{v.reason}</div>
      {v.reproducing_test && (
        <div className="mt-2">
          <button onClick={() => setShowTest(s => !s)} className="text-indigo-600 hover:underline">
            {showTest ? "Hide" : "Show"} reproducing test
          </button>
          {showTest && (
            <pre className="mt-1 overflow-auto rounded bg-slate-900 p-2 text-[11px] text-slate-100">{v.reproducing_test}</pre>
          )}
        </div>
      )}
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: FindingVerdict }) {
  const map: Record<FindingVerdict, { label: string; cls: string }> = {
    confirmed: { label: "confirmed", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
    refuted: { label: "refuted", cls: "text-amber-700 bg-amber-50 border-amber-200" },
    inconclusive: { label: "inconclusive", cls: "text-slate-600 bg-slate-50 border-slate-200" },
    not_execution_testable: { label: "not testable", cls: "text-slate-500 bg-slate-50 border-slate-200" },
  };
  const m = map[verdict];
  return <span className={`rounded border px-1.5 py-0.5 font-medium ${m.cls}`}>{m.label}</span>;
}

function GapRoundCard({ round }: { round: GapRound }) {
  const s = round.summary;
  const rate = s.confirmation_rate;
  return (
    <div className="rounded-xl border border-slate-100 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-700">
          {round.round === 0 ? "Round 0 (baseline)" : `Round ${round.round}`}
        </span>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Stat icon={<ShieldCheck className="h-3.5 w-3.5" />} label="confirmed" value={s.confirmed} tone="emerald" />
          <Stat icon={<ShieldQuestion className="h-3.5 w-3.5" />} label="unconfirmed" value={s.unconfirmed} tone="amber" />
          <Stat icon={<ShieldAlert className="h-3.5 w-3.5" />} label="untested" value={s.untested} tone="slate" />
          <Stat icon={<Zap className="h-3.5 w-3.5" />} label="execution-only" value={s.execution_only} tone="indigo" />
        </div>
      </div>

      {rate !== null && (
        <div className="mt-2 text-xs text-slate-500">
          Confirmation rate: <span className="font-semibold text-slate-700">{(rate * 100).toFixed(0)}%</span>
          <span className="text-slate-400"> (of findings execution could test)</span>
        </div>
      )}

      {/* The gap, called out: execution-found bugs with no static finding. */}
      {round.execution_only_functions.length > 0 && (
        <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-800">
            <Zap className="h-3.5 w-3.5" /> Verification gap: bugs static analysis missed
          </div>
          <div className="mt-1 text-xs text-indigo-700">
            Execution found bugs in {round.execution_only_functions.map(f => <code key={f} className="mx-0.5 rounded bg-white/70 px-1 font-mono">{f}</code>)} that no static tool flagged.
          </div>
        </div>
      )}

      {round.findings.length > 0 && (
        <div className="mt-3 max-h-64 overflow-auto rounded-lg border border-slate-100">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5">Tool</th>
                <th className="px-2 py-1.5">Severity</th>
                <th className="px-2 py-1.5">Line</th>
                <th className="px-2 py-1.5">Function</th>
                <th className="px-2 py-1.5">Finding</th>
              </tr>
            </thead>
            <tbody>
              {round.findings.map((f, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="px-2 py-1.5"><StatusBadge status={f.status} /></td>
                  <td className="px-2 py-1.5 text-slate-600">{f.tool}</td>
                  <td className="px-2 py-1.5 text-slate-600">{f.severity}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-500">{f.line}</td>
                  <td className="px-2 py-1.5 font-mono text-slate-700">{f.function ?? "—"}</td>
                  <td className="px-2 py-1.5 text-slate-600">{f.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: number; tone: string }) {
  const tones: Record<string, string> = {
    emerald: "text-emerald-700 bg-emerald-50",
    amber: "text-amber-700 bg-amber-50",
    slate: "text-slate-600 bg-slate-100",
    indigo: "text-indigo-700 bg-indigo-50",
  };
  return (
    <span className={`flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium ${tones[tone]}`}>
      {icon}{value} {label}
    </span>
  );
}

function StatusBadge({ status }: { status: FindingStatus }) {
  const map: Record<FindingStatus, { label: string; cls: string }> = {
    confirmed: { label: "confirmed", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
    unconfirmed: { label: "unconfirmed", cls: "text-amber-700 bg-amber-50 border-amber-200" },
    untested: { label: "untested", cls: "text-slate-600 bg-slate-50 border-slate-200" },
  };
  const m = map[status];
  return <span className={`rounded border px-1.5 py-0.5 font-medium ${m.cls}`}>{m.label}</span>;
}
