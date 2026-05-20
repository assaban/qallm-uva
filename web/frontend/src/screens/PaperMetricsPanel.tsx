import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

interface PaperMetrics {
  cs: number;
  mi: number;
  codu: number;
  code: number;
  loc: number;
  cc: number;
  round?: number;
  label?: string;
}

interface Comparison {
  round: number;
  vs_baseline?: Record<string, number>;
  vs_previous?: Record<string, number>;
}

function DeltaBadge({ value, inverted }: { value: number; inverted?: boolean }) {
  const improved = inverted ? value > 0 : value < 0;
  const cls = improved
    ? "bg-emerald-100 text-emerald-800"
    : value === 0
      ? "bg-slate-100 text-slate-600"
      : "bg-red-100 text-red-800";
  const prefix = value > 0 ? "+" : "";
  return <span className={`inline-block rounded-md px-1.5 py-0.5 text-xs font-medium ${cls}`}>{prefix}{value}</span>;
}

export default function PaperMetricsPanel({
  rounds,
  comparisons,
}: {
  rounds: PaperMetrics[];
  comparisons: Comparison[];
}) {
  if (!rounds.length) {
    return <div className="text-sm text-slate-500">No metrics data yet. Run analysis first.</div>;
  }

  // Chart data for metrics across rounds
  const chartData = rounds.map((r) => ({
    name: r.label || (r.round === 0 ? "Baseline" : `Round ${r.round}`),
    CS: r.cs,
    MI: r.mi,
    CoDu: r.codu,
    CC: r.cc,
  }));

  const latestComparison = comparisons[comparisons.length - 1];

  return (
    <div className="space-y-6">
      {/* Metrics table (paper Table 6 format) */}
      <div className="overflow-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="border-b bg-slate-50">
            <tr>
              <th className="px-3 py-2">Step</th>
              <th className="px-3 py-2">CS ↓</th>
              <th className="px-3 py-2">MI ↑</th>
              <th className="px-3 py-2">CoDu ↓</th>
              <th className="px-3 py-2">CoDe ↑</th>
              <th className="px-3 py-2">LoC</th>
              <th className="px-3 py-2">CC ↑</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((r, i) => (
              <tr key={i} className={`border-b border-slate-100 ${i === 0 ? "bg-slate-50 font-medium" : "hover:bg-slate-50"}`}>
                <td className="px-3 py-2">{r.label || (r.round === 0 ? "Baseline" : `Round ${r.round}`)}</td>
                <td className="px-3 py-2">{r.cs}</td>
                <td className="px-3 py-2">{r.mi}</td>
                <td className="px-3 py-2">{r.codu}</td>
                <td className="px-3 py-2">{r.code}</td>
                <td className="px-3 py-2">{r.loc}</td>
                <td className="px-3 py-2">{r.cc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Improvement deltas */}
      {latestComparison?.vs_baseline && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 className="mb-3 font-semibold">Improvement vs baseline</h4>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
            <div className="text-center">
              <div className="text-xs text-slate-500">CS</div>
              <DeltaBadge value={latestComparison.vs_baseline.cs_delta || 0} />
            </div>
            <div className="text-center">
              <div className="text-xs text-slate-500">MI</div>
              <DeltaBadge value={latestComparison.vs_baseline.mi_delta || 0} inverted />
            </div>
            <div className="text-center">
              <div className="text-xs text-slate-500">CoDu</div>
              <DeltaBadge value={latestComparison.vs_baseline.codu_delta || 0} />
            </div>
            <div className="text-center">
              <div className="text-xs text-slate-500">CoDe</div>
              <DeltaBadge value={latestComparison.vs_baseline.code_delta || 0} inverted />
            </div>
            <div className="text-center">
              <div className="text-xs text-slate-500">LoC</div>
              <DeltaBadge value={latestComparison.vs_baseline.loc_delta || 0} />
            </div>
            <div className="text-center">
              <div className="text-xs text-slate-500">CC</div>
              <DeltaBadge value={latestComparison.vs_baseline.cc_delta || 0} inverted />
            </div>
          </div>
        </div>
      )}

      {/* Chart: metrics across rounds */}
      {chartData.length > 1 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 className="mb-3 font-semibold">Metrics across rounds</h4>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="CS" fill="#ef4444" radius={[4, 4, 0, 0]} />
                <Bar dataKey="MI" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="CoDu" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                <Bar dataKey="CC" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
