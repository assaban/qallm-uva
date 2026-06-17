import { useState, useEffect } from "react";
import { RotateCw, TrendingUp, AlertTriangle, Layers, CheckCircle2, PlusCircle, MinusCircle, ChevronRight } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { StatCard } from "../components/Shared";
import type { SessionState } from "../hooks/useSession";
import type { AnalysisRound, RoundFinding } from "../types";
import * as api from "../api";
import PaperMetricsPanel from "./PaperMetricsPanel";

interface PaperMetrics {
  cs: number; mi: number; codu: number; code: number; loc: number; cc: number;
  round?: number; label?: string;
}
interface Comparison {
  round: number;
  vs_baseline?: Record<string, number>;
  vs_previous?: Record<string, number>;
}
interface RoundInfo {
  round: number; label: string; files: number; has_findings?: boolean; has_tests?: boolean;
}

export default function ReanalyseScreen({ state, patch }: { state: SessionState; patch: (p: Partial<SessionState>) => void }) {
  const [metricsHistory, setMetricsHistory] = useState<PaperMetrics[]>([]);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [rounds, setRounds] = useState<RoundInfo[]>([]);
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!state.sessionId || loaded) return;
    loadData();
    setLoaded(true);
  }, [state.sessionId]);

  async function loadData() {
    if (!state.sessionId) return;
    try {
      const [mh, comp, rds] = await Promise.allSettled([
        fetch(`/api/session/${state.sessionId}/paper-metrics-history`).then(r => r.json()).then(d => d.rounds || []),
        fetch(`/api/session/${state.sessionId}/comparisons`).then(r => r.json()).then(d => d.comparisons || []),
        fetch(`/api/session/${state.sessionId}/rounds`).then(r => r.json()).then(d => d.rounds || []),
      ]);
      if (mh.status === "fulfilled") setMetricsHistory(mh.value);
      if (comp.status === "fulfilled") setComparisons(comp.value);
      if (rds.status === "fulfilled") setRounds(rds.value);
    } catch { /* ignore */ }
  }

  async function run() {
    if (!state.sessionId) return;
    patch({ loading: true, error: null });
    try {
      const r = await api.runAnalysis(state.sessionId, state.selectedFiles);
      const analysisRounds = await api.getAnalysisHistory(state.sessionId).catch(() => []);
      patch({ summary: r.summary, findings: r.findings, analysisRounds, loading: false });
      await loadData();
    } catch (e: unknown) { patch({ loading: false, error: (e as Error).message }); }
  }

  const analysisRounds = state.analysisRounds;
  const first = analysisRounds[0];
  const last = analysisRounds[analysisRounds.length - 1];
  const improved = first && last ? first.total - last.total : 0;
  const pct = first && first.total > 0 ? Math.round((improved / first.total) * 100) : 0;

  const findingsChartData = analysisRounds.map(r => ({
    name: r.round === 0 ? "Baseline" : `Round ${r.round}`,
    "Critical+High": (r.by_severity.CRITICAL || 0) + (r.by_severity.HIGH || 0),
    Medium: r.by_severity.MEDIUM || 0,
    Low: r.by_severity.LOW || 0,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-xl font-semibold">Re-analyse shows improvement</h2>
          <p className="mt-1 text-sm text-slate-500">Compare findings and paper metrics before and after repair.</p>
        </div>
        <div className="flex items-center gap-3">
          {rounds.length > 1 && (
            <select
              value={selectedRound ?? ""}
              onChange={e => setSelectedRound(e.target.value ? Number(e.target.value) : null)}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">All rounds</option>
              {rounds.map(r => (
                <option key={r.round} value={r.round}>{r.label} ({r.files} files)</option>
              ))}
            </select>
          )}
          <button onClick={run} disabled={state.loading} className="flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">
            <RotateCw className="h-4 w-4" />{state.loading ? "Analysing..." : "Re-analyse"}
          </button>
        </div>
      </div>

      {state.error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{state.error}</div>}

      {/* Stats cards */}
      {analysisRounds.length >= 2 && (
        <div className="grid gap-4 sm:grid-cols-4">
          <StatCard label="Initial findings" value={first?.total || 0} icon={AlertTriangle} />
          <StatCard label="Current findings" value={last?.total || 0} icon={AlertTriangle} />
          <StatCard label="Improvement" value={`${pct}%`} hint={`${improved} resolved`} icon={TrendingUp} />
          <StatCard label="Rounds" value={rounds.length - 1} icon={Layers} />
        </div>
      )}

      {/* Findings across rounds */}
      {findingsChartData.length >= 2 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="mb-4 font-semibold">Findings across rounds</h3>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={findingsChartData}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
                <Bar dataKey="Critical+High" stackId="a" fill="#ef4444" />
                <Bar dataKey="Medium" stackId="a" fill="#f59e0b" />
                <Bar dataKey="Low" stackId="a" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* What changed: per-finding diff between the first and latest round */}
      <FindingsDiff rounds={analysisRounds} />

      {/* Paper metrics panel (Table 6 view) */}
      {metricsHistory.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="mb-4 font-semibold">Paper metrics (Table 6)</h3>
          <PaperMetricsPanel rounds={metricsHistory} comparisons={comparisons} />
        </div>
      )}

      {/* Empty state */}
      {analysisRounds.length < 2 && !state.loading && metricsHistory.length === 0 && (
        <div className="rounded-2xl border bg-slate-50 p-8 text-center text-sm text-slate-500">
          Run analysis at least twice (before and after repair) to see comparison.
        </div>
      )}
    </div>
  );
}

function _key(f: RoundFinding): string {
  // Identity of a finding across rounds: same rule at the same place. Message
  // is excluded so a reworded message does not look like a different finding.
  return `${f.tool}|${f.rule_id || f.type}|${f.file || ""}|${f.line ?? ""}`;
}

function FindingsDiff({ rounds }: { rounds: AnalysisRound[] }) {
  // Compare the first (baseline) and latest round that carry finding lists.
  const withFindings = rounds.filter(r => Array.isArray(r.findings));
  if (withFindings.length < 2) return null;
  const before = withFindings[0].findings ?? [];
  const after = withFindings[withFindings.length - 1].findings ?? [];

  const beforeKeys = new Map(before.map(f => [_key(f), f]));
  const afterKeys = new Map(after.map(f => [_key(f), f]));

  const resolved = before.filter(f => !afterKeys.has(_key(f)));
  const introduced = after.filter(f => !beforeKeys.has(_key(f)));
  const persisting = after.filter(f => beforeKeys.has(_key(f)));

  if (!resolved.length && !introduced.length && !persisting.length) return null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-1 font-semibold">What changed</h3>
      <p className="mb-4 text-sm text-slate-500">
        Findings resolved, newly introduced, and still present, comparing the
        baseline to the latest re-analysis.
      </p>
      <div className="space-y-4">
        <DiffGroup title="Resolved" count={resolved.length} items={resolved}
          icon={<CheckCircle2 className="h-4 w-4 text-emerald-600" />}
          tone="text-emerald-700" />
        <DiffGroup title="Newly introduced" count={introduced.length} items={introduced}
          icon={<PlusCircle className="h-4 w-4 text-rose-600" />}
          tone="text-rose-700" />
        <DiffGroup title="Still present" count={persisting.length} items={persisting}
          icon={<MinusCircle className="h-4 w-4 text-slate-400" />}
          tone="text-slate-600" collapsed />
      </div>
    </div>
  );
}

const DIFF_SEV_CLS: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800",
  HIGH: "bg-orange-100 text-orange-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  LOW: "bg-blue-100 text-blue-800",
};

function DiffGroup({ title, count, items, icon, tone, collapsed }: {
  title: string; count: number; items: RoundFinding[];
  icon: React.ReactNode; tone: string; collapsed?: boolean;
}) {
  if (count === 0) return (
    <div className="flex items-center gap-2 text-sm text-slate-400">
      {icon}<span>{title}: none</span>
    </div>
  );
  return (
    <details open={!collapsed}>
      <summary className={`flex cursor-pointer items-center gap-2 text-sm font-semibold ${tone}`}>
        {icon}{title}: {count}
      </summary>
      {/* Same column layout as the baseline findings table, and rows expand to
          the same detail (type, rule, line, code snippet) that Koen asked for. */}
      <table className="mt-2 w-full text-left text-xs">
        <tbody className="divide-y divide-slate-100">
          {items.map((f, i) => <DiffFindingRow key={i} f={f} />)}
        </tbody>
      </table>
    </details>
  );
}

function DiffFindingRow({ f }: { f: RoundFinding }) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(f.code_snippet || f.rule_id || f.type);
  return (
    <>
      <tr
        onClick={hasDetail ? () => setOpen(o => !o) : undefined}
        className={`${hasDetail ? "cursor-pointer hover:bg-slate-50/80" : ""} ${open ? "bg-slate-50" : ""}`}
      >
        <td className="px-3 py-2 align-top">
          <div className="flex items-center gap-1.5">
            {hasDetail && <ChevronRight className={`h-3.5 w-3.5 text-slate-400 transition-transform ${open ? "rotate-90" : ""}`} />}
            <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${DIFF_SEV_CLS[f.severity] || "bg-slate-100 text-slate-600"}`}>
              {f.severity}
            </span>
          </div>
        </td>
        <td className="px-3 py-2 align-top font-medium text-slate-600">
          {f.tool}
          {f.rule_id && <span className="ml-1.5 font-mono text-[10px] text-slate-400">{f.rule_id}</span>}
        </td>
        <td className="px-3 py-2 align-top">
          <span className="font-mono text-[10px] text-slate-500">{f.file || "\u2014"}:{f.line ?? "\u2014"}</span>
        </td>
        <td className="px-3 py-2 align-top leading-relaxed text-slate-600">{f.message}</td>
      </tr>
      {open && (
        <tr className="bg-slate-50">
          <td colSpan={4} className="px-3 pb-3 pt-0">
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs">
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-slate-600">
                {f.type && <span><span className="font-semibold text-slate-700">Type:</span> {f.type}</span>}
                {f.rule_id && <span><span className="font-semibold text-slate-700">Rule:</span> <span className="font-mono">{f.rule_id}</span></span>}
                <span><span className="font-semibold text-slate-700">Tool:</span> {f.tool}</span>
                {f.line ? <span><span className="font-semibold text-slate-700">Line:</span> {f.line}</span> : null}
              </div>
              <p className="mt-2 text-slate-600">{f.message}</p>
              {f.code_snippet && (
                <pre className="mt-2 overflow-auto rounded-md bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100">
                  {f.code_snippet}
                </pre>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
