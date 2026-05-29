/**
 * ResultsScreen: the final pipeline view, redesigned for the v3 surface.
 *
 * Replaces the old RLScreen with a richer view that surfaces:
 *   - The session's overall outcome (halt reason, totals).
 *   - Per-unit lineage and abandoned variants with judge verdicts.
 *   - The existing learning-curve and coverage charts.
 *   - The budget consumed.
 *   - Downloads (tests, JSON report).
 *
 * The component degrades gracefully: if the backend response is missing
 * v3 fields (older sessions, edge cases), only the basic charts render.
 */

import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  Download, CheckCircle2, XCircle, Minus, AlertTriangle,
  Clock, DollarSign, Layers, Scale,
} from "lucide-react";
import type { SessionState } from "../hooks/useSession";
import ImprovementView from "./ImprovementView";
import type {
  VerificationFunction, RoundResult, UnitTrackView,
  LineageEntryView, AbandonedEntryView,
} from "../types";
import * as api from "../api";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#38bdf8", "#ec4899"];

// Pretty-print the judge outcome with an icon and colour.
function OutcomeBadge({ outcome }: { outcome: string }) {
  if (outcome === "improvement") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="h-3 w-3" /> improvement
      </span>
    );
  }
  if (outcome === "regression") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700">
        <XCircle className="h-3 w-3" /> regression
      </span>
    );
  }
  if (outcome === "no_change") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
        <Minus className="h-3 w-3" /> no change
      </span>
    );
  }
  return <span className="text-xs text-slate-500">{outcome}</span>;
}

// One per-unit panel: lineage and abandoned variants, side by side.
function UnitTrackPanel({ unitId, track }: { unitId: string; track: UnitTrackView }) {
  return (
    <div className="rounded-2xl border bg-white p-5 shadow-sm">
      <div className="flex items-baseline justify-between">
        <h4 className="text-sm font-medium font-mono text-slate-700">{unitId}</h4>
        <div className="text-xs text-slate-500">
          <span className="font-medium text-emerald-700">{track.lineage.length}</span> accepted
          {" / "}
          <span className="font-medium text-rose-700">{track.abandoned.length}</span> abandoned
        </div>
      </div>

      {track.lineage.length > 0 && (
        <div className="mt-4">
          <div className="text-xs font-bold uppercase text-slate-500 mb-2">Accepted lineage</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-2">Round</th>
                <th className="py-1 pr-2">Outcome</th>
                <th className="py-1">Explanation</th>
              </tr>
            </thead>
            <tbody>
              {track.lineage.map((entry: LineageEntryView) => (
                <tr key={`l-${entry.round_number}`} className="border-t border-slate-100">
                  <td className="py-1.5 pr-2 font-medium">
                    {entry.round_number === 0 ? (
                      <span className="inline-flex items-center gap-1">
                        <span>0</span>
                        <span className="rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-700">
                          baseline
                        </span>
                      </span>
                    ) : (
                      entry.round_number
                    )}
                  </td>
                  <td className="py-1.5 pr-2">
                    {entry.judge_verdict ? (
                      <OutcomeBadge outcome={entry.judge_verdict.outcome} />
                    ) : (
                      <span className="text-xs italic text-slate-500">
                        ground truth
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 text-slate-600">
                    {entry.judge_verdict?.explanation || (
                      "Original code, verified before any repair."
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {track.abandoned.length > 0 && (
        <div className="mt-4">
          <div className="text-xs font-bold uppercase text-rose-700 mb-2">Abandoned variants</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 pr-2">Round</th>
                <th className="py-1">Reason</th>
              </tr>
            </thead>
            <tbody>
              {track.abandoned.map((entry: AbandonedEntryView) => (
                <tr key={`a-${entry.round_number}`} className="border-t border-slate-100">
                  <td className="py-1.5 pr-2 font-medium">{entry.round_number}</td>
                  <td className="py-1.5 text-slate-600">
                    {entry.judge_verdict.explanation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// Halt reason badge: green for completion, amber for budget caps.
function HaltBadge({ reason }: { reason: string | null | undefined }) {
  if (!reason) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" /> completed
      </span>
    );
  }
  if (reason === "max_rounds") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" /> completed all rounds
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700">
      <AlertTriangle className="h-3.5 w-3.5" /> halted: {reason}
    </span>
  );
}

export default function ResultsScreen({ state }: { state: SessionState }) {
  const result = state.testGenResult;
  if (!result) return (
    <div className="rounded-2xl border bg-slate-50 p-12 text-center text-sm text-slate-500">
      Run test generation in Step 5 first.
    </div>
  );

  const funcs: VerificationFunction[] = result.functions || [];
  const tracks = result.tracks || {};

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

  // Budget summary helpers.
  const budget = result.budget || {};
  const tokens = result.token_usage || {};
  const costUsd = (tokens as any).total_cost_usd ?? 0;
  const totalTokens = (tokens as any).total_tokens ?? 0;
  const elapsedSec = (budget as any).elapsed_seconds ?? 0;

  return (
    <div className="space-y-6">
      {/* Session outcome banner */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">Session outcome</h2>
            <HaltBadge reason={result.halt_reason} />
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600">
            <span className="inline-flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              <span className="font-medium text-emerald-700">{result.rounds_accepted_total ?? 0}</span> accepted
              {" / "}
              <span className="font-medium text-rose-700">{result.rounds_abandoned_total ?? 0}</span> abandoned
            </span>
            {result.judge_strategy && (
              <span className="inline-flex items-center gap-1">
                <Scale className="h-3.5 w-3.5" /> judge: <b>{result.judge_strategy}</b>
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" /> {elapsedSec.toFixed(1)}s
            </span>
            <span className="inline-flex items-center gap-1">
              <DollarSign className="h-3.5 w-3.5" /> {Number(costUsd).toFixed(4)} / {totalTokens.toLocaleString()} tok
            </span>
          </div>
        </div>
        {(result.repair_model || result.testgen_model) && (
          <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-slate-600 md:grid-cols-2">
            <div><b>Repair model:</b> <span className="font-mono">{result.repair_model || result.model}</span></div>
            <div><b>Test-gen model:</b> <span className="font-mono">{result.testgen_model || result.model}</span></div>
          </div>
        )}
        {/* Quality profile: which framework's dimensions and indicators
            the judge used to compute accept/abandon decisions. Shown so
            users can see which methodology the run was judged under and
            in what priority order. */}
        {result.profile && (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-xs font-semibold uppercase text-slate-500">
                Quality profile
              </span>
              <span className="font-mono text-sm font-semibold text-slate-800">
                {result.profile.profile_id}
              </span>
              {result.profile.lifecycle_stage && (
                <span className="rounded-md bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-indigo-700">
                  {result.profile.lifecycle_stage}
                </span>
              )}
              {result.profile.description && (
                <span className="text-xs text-slate-600">
                  {result.profile.description}
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {result.profile.dimensions.map((d, i) => (
                <span
                  key={d.dimension}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs"
                  title={`${d.indicators.length} indicator(s)`}
                >
                  <span className="font-mono text-[10px] text-slate-400">{i + 1}.</span>
                  <span className="font-medium text-slate-700">{d.dimension}</span>
                  <span className="text-[10px] text-slate-500">({d.indicators.length})</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Per-unit tracks (the v3 lineage / abandoned view) */}
      {Object.keys(tracks).length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-bold uppercase text-slate-500">Per-unit lineage</h3>
          {Object.entries(tracks).map(([unitId, track]) => (
            <UnitTrackPanel key={unitId} unitId={unitId} track={track as UnitTrackView} />
          ))}
        </div>
      )}

      {/* Learning curve + coverage */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold">Verification improves across rounds</h2>
          <p className="mt-1 text-sm text-slate-500">Cumulative reward per function. A rising line means the iterative feedback is finding more.</p>
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

      {/* Bugs callout */}
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

      {/* Conclusion + exports */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-900 bg-slate-900 p-6 text-white">
          <h3 className="font-semibold">Thesis conclusion</h3>
          <div className="mt-3 space-y-2 text-sm text-slate-300">
            <p>Static analysis finds issues quickly.</p>
            <p>LLM repair reduces them with actionable patches.</p>
            <p>Generated tests catch bugs static analysis misses.</p>
            <p>The judge accepts or abandons each round's variant per EVERSE dimensions.</p>
            <p className="font-medium text-white">The budget-capped improvement loop, with judged accept/abandon decisions against a quality model, is the core contribution.</p>
          </div>
        </div>
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="font-semibold">Export results</h3>
          <button onClick={dlTests} className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium hover:bg-slate-50"><Download className="h-4 w-4" /> Download generated tests</button>
          <button onClick={dlReport} className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium hover:bg-slate-50"><Download className="h-4 w-4" /> Download report (.json)</button>
          {result.report_dir && (
            <p className="text-xs text-slate-500">
              Full session artefacts on disk: <span className="font-mono">{result.report_dir}</span>
            </p>
          )}
        </div>
      </div>

      {state.sessionId && <ImprovementView sessionId={state.sessionId} />}
    </div>
  );
}