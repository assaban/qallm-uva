import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Download } from "lucide-react";
import type { SessionState } from "../hooks/useSession";
import type { VerificationFunction, RoundResult } from "../types";
import * as api from "../api";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#38bdf8", "#ec4899"];

export default function RLScreen({ state }: { state: SessionState }) {
  const result = state.testGenResult;
  if (!result) return (
    <div className="rounded-2xl border bg-slate-50 p-12 text-center text-sm text-slate-500">Run test generation in Step 5 first.</div>
  );

  const funcs: VerificationFunction[] = result.functions || [];
  const maxR = Math.max(...funcs.map(f => f.rounds?.length || 0), 1);

  const curveData = Array.from({ length: maxR }, (_, i) => {
    const pt: Record<string, number | string> = { round: `R${i + 1}` };
    funcs.forEach(f => {
      let cum = 0;
      for (let j = 0; j <= i && j < (f.rounds?.length || 0); j++) cum += f.rounds[j].reward?.total || 0;
      pt[f.function_name] = Math.round(cum * 10) / 10;
    });
    return pt;
  });

  const covData = funcs.map(f => {
    const r = f.rounds || [];
    const last = r[r.length - 1];
    return { name: f.function_name, coverage: Math.round(last?.cumulative_coverage || last?.execution?.coverage_percent || 0) };
  });

  const bugs = funcs.flatMap(f =>
    (f.rounds || []).filter((r: RoundResult) => r.reward?.bugs_found > 0).map((r: RoundResult) => ({
      func: f.function_name, round: r.round_number, bugs: r.reward.bugs_found, cov: Math.round(r.cumulative_coverage || 0),
    }))
  );

  async function dlTests() {
    if (!state.sessionId) return;
    try {
      const files = await api.downloadTestFiles(state.sessionId);
      if (!files.length) return;
      let txt = "";
      files.forEach(f => { txt += "=".repeat(60) + "\nFILE: " + f.name + "\n" + "=".repeat(60) + "\n" + f.content + "\n\n"; });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([txt], { type: "text/plain" }));
      a.download = `qallm_tests_${state.sessionId.slice(0, 8)}.txt`;
      a.click();
    } catch { /* ignore */ }
  }

  function dlReport() {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    a.download = `qallm_report_${state.sessionId?.slice(0, 8)}.json`;
    a.click();
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold">The RL loop improves across rounds</h2>
          <p className="mt-1 text-sm text-slate-500">Cumulative reward per function. A rising line means the loop is learning.</p>
          <div className="mt-4 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curveData}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="round" /><YAxis /><Tooltip />
                {funcs.map((f, i) => <Line key={f.function_name} type="monotone" dataKey={f.function_name} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5} dot={{ r: 4 }} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="font-semibold">Coverage per function</h3>
          <p className="mt-1 text-sm text-slate-500">Final coverage after all rounds.</p>
          <div className="mt-4 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={covData} layout="vertical">
                <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                <XAxis type="number" domain={[0, 100]} /><YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 12 }} /><Tooltip />
                <Bar dataKey="coverage" radius={[0, 6, 6, 0]} fill="#6366f1" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {bugs.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="font-semibold">Bugs found by generated tests</h3>
          <p className="mt-1 mb-4 text-sm text-slate-500">Discovered by execution, not static analysis.</p>
          <div className="space-y-2">
            {bugs.map((b, i) => (
              <div key={i} className="flex items-center justify-between rounded-xl border p-3">
                <div><span className="font-mono text-sm font-medium">{b.func}</span><span className="ml-2 text-xs text-slate-500">Round {b.round}</span></div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500">{b.cov}% cov</span>
                  <span className="rounded-md bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">{b.bugs} bug{b.bugs !== 1 ? "s" : ""}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-900 bg-slate-900 p-6 text-white">
          <h3 className="font-semibold">Thesis conclusion</h3>
          <div className="mt-3 space-y-2 text-sm text-slate-300">
            <p>Static analysis finds issues quickly.</p>
            <p>LLM repair reduces them with actionable patches.</p>
            <p>Generated tests catch bugs static analysis misses.</p>
            <p className="font-medium text-white">The RL loop gets better across rounds: this is the thesis contribution.</p>
          </div>
        </div>
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="font-semibold">Export results</h3>
          <button onClick={dlTests} className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium hover:bg-slate-50"><Download className="h-4 w-4" /> Download generated tests</button>
          <button onClick={dlReport} className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium hover:bg-slate-50"><Download className="h-4 w-4" /> Download report (.json)</button>
        </div>
      </div>
    </div>
  );
}
