import { useState, useEffect } from "react";
import { RotateCw, TrendingUp, AlertTriangle, Layers } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { StatCard } from "../components/Shared";
import type { SessionState } from "../hooks/useSession";
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
