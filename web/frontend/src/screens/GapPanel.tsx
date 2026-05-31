import { useState, useEffect } from "react";
import { ShieldCheck, ShieldAlert, ShieldQuestion, Zap } from "lucide-react";
import * as api from "../api";
import type { GapRound, FindingStatus } from "../api";

// The static-vs-execution gap, per round: how many static findings
// execution confirmed, could not reproduce, or could not test, and the
// execution-found bugs no static tool flagged (the verification gap).
export default function GapPanel({ sessionId }: { sessionId: string }) {
  const [rounds, setRounds] = useState<GapRound[]>([]);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

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
    </div>
  );
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
