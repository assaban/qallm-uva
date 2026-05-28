import { useState, useEffect, useMemo } from "react";
import { FlaskConical, Play, Lock, CheckSquare, Square, FileCode2, Activity, Layers, Coins, Clock } from "lucide-react";
import type { SessionState } from "../hooks/useSession";
import type { FunctionEntry } from "../types";
import * as api from "../api";
import type { JobProgress } from "../api";

const ORACLES: Record<string, { title: string; desc: string }> = {
  crash: { title: "Crash oracle", desc: "Feeds edge cases (empty inputs, None, overflow) and asserts the function fails cleanly rather than crashing." },
  property: { title: "Property oracle", desc: "Checks output invariants: correct return types, size relationships, value range constraints." },
  metamorphic: { title: "Metamorphic oracle", desc: "Tests input/output relationships: permutations, negation, composition. Catches logic bugs without expected outputs." },
};

interface SessionConfig {
  model_label?: string;
  model_name?: string;
  oracle?: string;
  rounds?: number;
  strategy?: string;
}

export default function TestGenScreen({ state, patch, autoMode }: { state: SessionState; patch: (p: Partial<SessionState>) => void; autoMode?: boolean }) {
  const [fns, setFns] = useState<FunctionEntry[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [sessionConfig, setSessionConfig] = useState<SessionConfig>({});
  // Live progress, updated on every poll while the verification job runs.
  // null when nothing is running or when the job has just started and we
  // have not received the first poll yet.
  const [progress, setProgress] = useState<JobProgress | null>(null);

  useEffect(() => {
    if (!state.sessionId) return;
    fetch(`/api/session/${state.sessionId}/config`)
      .then(r => r.json())
      .then(d => setSessionConfig(d.config || {}))
      .catch(() => {});
    api.getFunctions(state.sessionId)
      .then(f => { setFns(f); setSel(new Set(f.map(x => `${x.file}::${x.name}`))); })
      .catch(() => {});
  }, [state.sessionId]);

  // Group functions by file
  const grouped = useMemo(() => {
    const map: Record<string, FunctionEntry[]> = {};
    for (const f of fns) {
      (map[f.file] ||= []).push(f);
    }
    return map;
  }, [fns]);

  const allSelected = sel.size === fns.length;
  const noneSelected = sel.size === 0;

  function toggleAll() {
    if (allSelected) {
      setSel(new Set());
    } else {
      setSel(new Set(fns.map(f => `${f.file}::${f.name}`)));
    }
  }

  function toggleFile(file: string) {
    const fileFns = grouped[file] || [];
    const fileKeys = fileFns.map(f => `${f.file}::${f.name}`);
    const allIn = fileKeys.every(k => sel.has(k));
    const next = new Set(sel);
    if (allIn) {
      fileKeys.forEach(k => next.delete(k));
    } else {
      fileKeys.forEach(k => next.add(k));
    }
    setSel(next);
  }

  function toggle(f: FunctionEntry) {
    const key = `${f.file}::${f.name}`;
    setSel(prev => { const n = new Set(prev); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  }

  async function run() {
    if (!state.sessionId) return;
    setProgress(null);
    patch({ loading: true, error: null, progress: null });
    try {
      const r = await api.runTestGen(
        state.sessionId, "", "", 0,
        view => {
          if (view.progress) {
            setProgress(view.progress);
            patch({ progress: view.progress });
          }
        },
      );
      patch({ testGenResult: r, loading: false });
    } catch (e: unknown) {
      patch({ loading: false, error: (e as Error).message });
    }
  }

  // Use the live local progress when present (manual mode); otherwise
  // fall back to global state.progress (set by useAutoRunner during
  // auto mode runs).
  const liveProgress = progress ?? state.progress;

  const oracle = sessionConfig.oracle || "crash";

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold">RL-Guided Test Generation</h2>
          <p className="mt-1 text-sm text-slate-500">Generate tests, execute in sandbox, score with reward function, improve across rounds.</p>

          {/* Locked session config */}
          <div className="mt-4 grid grid-cols-3 gap-3">
            <div className="rounded-xl border bg-slate-50 p-3">
              <div className="flex items-center gap-1.5 text-xs text-slate-500"><Lock className="h-3 w-3" /> Model</div>
              <div className="mt-1 text-sm font-medium truncate">{sessionConfig.model_label || sessionConfig.model_name || "..."}</div>
            </div>
            <div className="rounded-xl border bg-slate-50 p-3">
              <div className="flex items-center gap-1.5 text-xs text-slate-500"><Lock className="h-3 w-3" /> Oracle</div>
              <div className="mt-1 text-sm font-medium capitalize">{oracle}</div>
            </div>
            <div className="rounded-xl border bg-slate-50 p-3">
              <div className="flex items-center gap-1.5 text-xs text-slate-500"><Lock className="h-3 w-3" /> Rounds</div>
              <div className="mt-1 text-sm font-medium">{sessionConfig.rounds || 5}</div>
            </div>
          </div>

          {/* Function selection grouped by file */}
          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium">Functions ({fns.length})</span>
              <button onClick={toggleAll} className="text-xs text-indigo-600 hover:underline">
                {allSelected ? "Deselect all" : "Select all"}
              </button>
            </div>
            <div className="max-h-[220px] space-y-1 overflow-auto rounded-xl border p-2">
              {Object.entries(grouped).map(([file, fileFns]) => {
                const fileKeys = fileFns.map(f => `${f.file}::${f.name}`);
                const allFileSelected = fileKeys.every(k => sel.has(k));
                const someFileSelected = fileKeys.some(k => sel.has(k));

                return (
                  <div key={file}>
                    {/* File header */}
                    <button
                      onClick={() => toggleFile(file)}
                      className="flex w-full items-center gap-2 rounded-lg bg-slate-50 px-2 py-1.5 text-left hover:bg-slate-100"
                    >
                      {allFileSelected ? (
                        <CheckSquare className="h-3.5 w-3.5 text-slate-900 flex-shrink-0" />
                      ) : (
                        <Square className={`h-3.5 w-3.5 flex-shrink-0 ${someFileSelected ? "text-slate-500" : "text-slate-300"}`} />
                      )}
                      <FileCode2 className="h-3.5 w-3.5 text-slate-500 flex-shrink-0" />
                      <span className="font-mono text-xs font-semibold text-slate-700">{file}</span>
                      <span className="ml-auto text-xs text-slate-400">{fileFns.length} fn{fileFns.length !== 1 ? "s" : ""}</span>
                    </button>
                    {/* Functions under this file */}
                    {fileFns.map(f => {
                      const key = `${f.file}::${f.name}`;
                      return (
                        <label key={key} className="flex cursor-pointer items-center gap-2 rounded-lg pl-7 pr-2 py-1 text-sm hover:bg-slate-50">
                          <input type="checkbox" checked={sel.has(key)} onChange={() => toggle(f)} className="rounded" />
                          <span className="font-mono text-xs text-slate-800">{f.name}</span>
                          <span className="text-xs text-slate-400">L{f.lineno}</span>
                          {f.docstring && <span className="ml-auto max-w-[120px] truncate text-xs text-slate-400 italic">{f.docstring}</span>}
                        </label>
                      );
                    })}
                  </div>
                );
              })}
              {fns.length === 0 && <div className="p-3 text-center text-xs text-slate-400">No extractable functions found.</div>}
            </div>
          </div>

          {!autoMode ? (
            <button onClick={run} disabled={state.loading || noneSelected}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">
              <Play className="h-4 w-4" />{state.loading ? "Generating..." : `Generate tests for ${sel.size} function${sel.size !== 1 ? "s" : ""}`}
            </button>
          ) : state.loading ? (
            <div className="mt-5 flex items-center justify-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-5 py-3 text-sm text-indigo-700">
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" /> Generating tests automatically...
            </div>
          ) : null}

          {/* Live progress: surfaces what the orchestrator is doing right
              now. Renders only while the job runs and progress has been
              received. Designed as a status line plus counters, not a
              progress bar; LLM call durations and judge-driven early-halt
              make percentage estimates misleading. */}
          {state.loading && liveProgress && (
            <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-indigo-600 animate-pulse" />
                <span className="text-sm font-semibold capitalize text-slate-800">
                  {liveProgress.phase === "rounds"
                    ? `Round ${liveProgress.current_round} of ${liveProgress.total_rounds}`
                    : liveProgress.phase === "baseline"
                      ? "Round 0 (baseline)"
                      : liveProgress.phase}
                </span>
                {liveProgress.current_stage && (
                  <span className="rounded-md bg-indigo-100 px-2 py-0.5 text-xs font-medium capitalize text-indigo-700">
                    {liveProgress.current_stage}
                  </span>
                )}
              </div>

              {liveProgress.current_unit_id && (
                <div className="flex items-start gap-2 text-xs text-slate-600">
                  <FileCode2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                  <span className="font-mono break-all">{liveProgress.current_unit_id}</span>
                </div>
              )}

              {/* Function-level visibility inside the verify stage. On
                  slow local LLMs the verify stage can run for tens of
                  minutes per unit; showing "function 3 of 8: predict"
                  is the difference between "stuck" and "working". */}
              {liveProgress.current_function && liveProgress.function_total > 0 && (
                <div className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="rounded-md bg-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-700">
                    {liveProgress.function_index}/{liveProgress.function_total}
                  </span>
                  <span>Verifying function: <span className="font-mono font-semibold text-slate-800">{liveProgress.current_function}</span></span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <div className="flex items-center gap-1.5">
                  <Layers className="h-3.5 w-3.5 text-emerald-600" />
                  <span className="text-slate-500">Accepted:</span>
                  <span className="font-semibold text-emerald-700">{liveProgress.rounds_accepted}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Layers className="h-3.5 w-3.5 text-rose-600" />
                  <span className="text-slate-500">Abandoned:</span>
                  <span className="font-semibold text-rose-700">{liveProgress.rounds_abandoned}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5 text-slate-400" />
                  <span className="text-slate-500">Elapsed:</span>
                  <span className="font-semibold text-slate-700">{liveProgress.elapsed_seconds.toFixed(1)}s</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Coins className="h-3.5 w-3.5 text-amber-600" />
                  <span className="text-slate-500">Cost:</span>
                  <span className="font-semibold text-slate-700">${liveProgress.cost_usd.toFixed(4)}</span>
                </div>
              </div>

              {liveProgress.tokens_used > 0 && (
                <div className="text-xs text-slate-500">
                  {liveProgress.tokens_used.toLocaleString()} tokens used
                  {liveProgress.units_total > 0 && (
                    <> · {liveProgress.units_completed} of {liveProgress.units_total} units completed</>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="font-semibold">Active oracle: <span className="capitalize">{oracle}</span></h3>
            <p className="mt-2 text-sm text-slate-600">{ORACLES[oracle]?.desc}</p>
            <div className="mt-4 space-y-3">
              {Object.entries(ORACLES).map(([k, v]) => (
                <div key={k} className={`rounded-xl border p-3 transition ${oracle === k ? "border-slate-900 bg-slate-50" : "border-slate-200 opacity-60"}`}>
                  <div className="text-sm font-medium">{v.title}</div>
                  {oracle !== k && <div className="mt-1 text-xs text-slate-500">{v.desc.slice(0, 80)}...</div>}
                </div>
              ))}
            </div>
          </div>
          {state.testGenResult && (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6">
              <div className="flex items-center gap-2"><FlaskConical className="h-5 w-5 text-emerald-600" /><h3 className="font-semibold text-emerald-900">Tests completed</h3></div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-emerald-700">Functions:</span> {state.testGenResult.total_functions}</div>
                <div><span className="text-emerald-700">Bugs found:</span> <span className="font-bold">{state.testGenResult.total_bugs}</span></div>
                <div><span className="text-emerald-700">Model:</span> {state.testGenResult.model}</div>
                <div><span className="text-emerald-700">Oracle:</span> {state.testGenResult.oracle}</div>
              </div>
              <p className="mt-3 text-xs text-emerald-700">Proceed to Step 6 for learning curves and detailed results.</p>
            </div>
          )}
        </div>
      </div>
      {state.error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{state.error}</div>}
    </div>
  );
}