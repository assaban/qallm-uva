import { useState, useEffect, useMemo, useRef } from "react";
import { FlaskConical, Play, Lock, CheckSquare, Square, FileCode2, Activity, Layers, Coins, Clock, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import type { SessionState } from "../hooks/useSession";
import type { FunctionEntry } from "../types";
import * as api from "../api";
import type { JobProgress } from "../api";

const ORACLES: Record<string, { title: string; desc: string }> = {
  crash: { title: "Crash oracle", desc: "Feeds edge cases (empty inputs, None, overflow) and asserts the function fails cleanly rather than crashing." },
  correctness: { title: "Correctness oracle", desc: "Reasons from the spec (signature and docstring, never the body) to find functions that do not crash but return wrong values. This is the reliability oracle behind the verification gap." },
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

// One row in the live progress timeline: a distinct (round, stage,
// function) state the orchestrator passed through, with the counters as
// they stood at that moment.
interface ProgressRow {
  key: string;
  roundLabel: string;
  stage: string;
  fn: string | null;
  unit: string | null;
  fnIndex: number;
  fnTotal: number;
  accepted: number;
  abandoned: number;
  elapsed: number;
  tokens: number;
}

// Per-round test outcome summary, derived from the improvement data once a
// round has completed.
interface RoundTestSummary {
  round: number;
  functions: {
    name: string;
    total: number;
    passed: number;
    bugs: number;
    errors: number;
    discarded: number;
  }[];
}

export default function TestGenScreen({ state, patch, autoMode }: { state: SessionState; patch: (p: Partial<SessionState>) => void; autoMode?: boolean }) {
  const [fns, setFns] = useState<FunctionEntry[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [sessionConfig, setSessionConfig] = useState<SessionConfig>({});
  // Live progress, updated on every poll while the verification job runs.
  // null when nothing is running or when the job has just started and we
  // have not received the first poll yet.
  const [progress, setProgress] = useState<JobProgress | null>(null);
  // Accumulated timeline of distinct progress states, so the right panel
  // shows the *progression* across rounds and stages instead of a single
  // overwritten status line. Each distinct (round, stage, function) snapshot
  // becomes one row.
  const [timeline, setTimeline] = useState<ProgressRow[]>([]);
  // Per-round test summaries, fetched from the improvement data as each
  // round completes (the live snapshot carries no test detail; tests land
  // on disk when a round finishes).
  const [roundTests, setRoundTests] = useState<RoundTestSummary[]>([]);
  const lastRoundFetched = useRef<number>(-1);

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

  // Accumulate the live snapshot into a timeline. Append a new row only
  // when the (round, stage, function) tuple changes, so the table grows by
  // meaningful steps rather than on every poll.
  useEffect(() => {
    if (!liveProgress) return;
    const roundLabel = liveProgress.phase === "baseline"
      ? "Round 0 (baseline)"
      : liveProgress.phase === "rounds"
        ? `Round ${liveProgress.current_round} of ${liveProgress.total_rounds}`
        : liveProgress.phase;
    const stage = liveProgress.current_stage || liveProgress.phase;
    const fn = liveProgress.current_function;
    // current_unit_id looks like "path/to/file.py::cellindex"; show just the
    // file name so analyse/repair/judge rows (which are unit-level, not
    // per-function) still say which file they acted on instead of a bare dash.
    const rawUnit = liveProgress.current_unit_id as string | null | undefined;
    const unit = rawUnit ? rawUnit.split("::")[0].split("/").pop() || rawUnit : null;
    const key = `${roundLabel}|${stage}|${fn ?? ""}|${liveProgress.function_index}`;
    setTimeline(prev => {
      if (prev.length && prev[prev.length - 1].key === key) return prev;
      return [...prev, {
        key,
        roundLabel,
        stage,
        fn,
        unit,
        fnIndex: liveProgress.function_index,
        fnTotal: liveProgress.function_total,
        accepted: liveProgress.rounds_accepted,
        abandoned: liveProgress.rounds_abandoned,
        elapsed: liveProgress.elapsed_seconds,
        tokens: liveProgress.tokens_used,
      }];
    });
  }, [liveProgress]);

  // When a round completes (current_round advances, or the job finishes),
  // fetch the improvement data and summarise each function's tests for the
  // rounds we have not summarised yet. The live snapshot has no test detail,
  // so this is how completed-round tests become visible during the run.
  useEffect(() => {
    if (!state.sessionId || !liveProgress) return;
    const justFinished = liveProgress.phase === "done"
      ? liveProgress.total_rounds
      : liveProgress.current_round - 1;
    if (justFinished <= lastRoundFetched.current) return;
    lastRoundFetched.current = justFinished;
    api.getImprovement(state.sessionId)
      .then(imp => {
        if (!imp || !imp.rounds) return;
        const summaries: RoundTestSummary[] = imp.rounds.map(r => {
          const fns: RoundTestSummary["functions"] = [];
          for (const unit of r.units || []) {
            for (const fn of unit.bug_detail || []) {
              fns.push({
                name: fn.function,
                total: fn.total,
                passed: fn.passed,
                bugs: fn.failed,
                errors: fn.errors,
                discarded: (fn.discarded || []).length,
              });
            }
          }
          return { round: r.round, functions: fns };
        });
        setRoundTests(summaries);
      })
      .catch(() => {});
  }, [state.sessionId, liveProgress]);

  // Reset the timeline and round tests when a fresh run starts.
  useEffect(() => {
    if (state.loading && timeline.length && !liveProgress) {
      setTimeline([]);
      setRoundTests([]);
      lastRoundFetched.current = -1;
    }
  }, [state.loading, liveProgress, timeline.length]);

  const oracle = sessionConfig.oracle || "crash";

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold">Improvement Rounds</h2>
          <p className="mt-1 text-sm text-slate-500">Baseline, then repair, verify, and judge across budget-capped rounds. Generate tests, execute in the sandbox, score with the reward, improve each round.</p>

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

          {/* Active oracle reference. Lives on the left, below the function
              list, since it is read once to understand what the oracle
              does; the right column is reserved for live stream status. */}
          <div className="mt-6 border-t border-slate-100 pt-4">
            <h3 className="text-sm font-semibold text-slate-700">Active oracle: <span className="capitalize">{oracle}</span></h3>
            <div className="mt-3 space-y-2">
              {Object.entries(ORACLES).map(([k, v]) => (
                <div key={k} className={`rounded-xl border p-3 transition ${oracle === k ? "border-slate-900 bg-slate-50" : "border-slate-200 opacity-60"}`}>
                  <div className="text-sm font-medium">{v.title}</div>
                  <div className="mt-1 text-xs text-slate-500">{oracle === k ? v.desc : `${v.desc.slice(0, 80)}...`}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          {/* Live verification timeline: accumulates each distinct stage
              state into a table so the progression across rounds is visible,
              instead of a single status line that gets overwritten. */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Live verification</h3>
              {liveProgress && (
                <span className="flex items-center gap-1.5 text-xs text-slate-500">
                  <Clock className="h-3.5 w-3.5" /> {liveProgress.elapsed_seconds.toFixed(0)}s
                  <Coins className="ml-2 h-3.5 w-3.5 text-amber-600" /> ${liveProgress.cost_usd.toFixed(4)}
                </span>
              )}
            </div>

            {timeline.length === 0 ? (
              <p className="mt-3 text-sm text-slate-400">
                The run timeline appears here: each round and stage as the pipeline works through baseline, repair, verify, and judge.
              </p>
            ) : (
              <div className="mt-3 max-h-72 overflow-auto rounded-xl border border-slate-100">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-left text-slate-500">
                    <tr>
                      <th className="px-2 py-1.5">Round</th>
                      <th className="px-2 py-1.5">Stage</th>
                      <th className="px-2 py-1.5">Function</th>
                      <th className="px-2 py-1.5 text-right">Acc/Aband</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.map((row, i) => {
                      const isLast = i === timeline.length - 1;
                      return (
                        <tr key={row.key} className={`border-t border-slate-100 ${isLast && state.loading ? "bg-indigo-50" : ""}`}>
                          <td className="px-2 py-1.5 whitespace-nowrap">{row.roundLabel}</td>
                          <td className="px-2 py-1.5">
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium capitalize text-slate-600">{row.stage}</span>
                          </td>
                          <td className="px-2 py-1.5 font-mono text-slate-700">
                            {row.fn ? (
                              <span>{row.fn}{row.fnTotal > 0 && <span className="text-slate-400"> ({row.fnIndex}/{row.fnTotal})</span>}</span>
                            ) : row.unit ? (
                              <span className="font-mono text-xs text-slate-500">{row.unit}</span>
                            ) : <span className="text-slate-300">—</span>}
                          </td>
                          <td className="px-2 py-1.5 text-right whitespace-nowrap">
                            <span className="text-emerald-700">{row.accepted}</span>
                            <span className="text-slate-300"> / </span>
                            <span className="text-rose-700">{row.abandoned}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {liveProgress && liveProgress.tokens_used > 0 && (
              <div className="mt-2 text-xs text-slate-500">
                {liveProgress.tokens_used.toLocaleString()} tokens
                {liveProgress.units_total > 0 && <> · {liveProgress.units_completed} of {liveProgress.units_total} units completed</>}
              </div>
            )}
          </div>

          {/* Per-round tests, accumulated. Shows how the FROZEN+GROW suite
              grows: each completed round's functions with pass/bug/error
              counts. Latest round first. */}
          {roundTests.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="font-semibold">Tests by round</h3>
              <p className="mt-1 text-xs text-slate-500">Accumulated test outcomes per round. The suite grows each round (FROZEN+GROW): later rounds re-run earlier tests plus new ones.</p>
              <div className="mt-3 space-y-3">
                {[...roundTests].reverse().map(rt => (
                  <div key={rt.round} className="rounded-xl border border-slate-100 p-3">
                    <div className="text-xs font-semibold text-slate-700">
                      {rt.round === 0 ? "Round 0 (baseline)" : `Round ${rt.round}`}
                    </div>
                    <div className="mt-2 space-y-1.5">
                      {rt.functions.map((fn, i) => (
                        <div key={i} className="flex items-center justify-between text-xs">
                          <span className="font-mono text-slate-700">{fn.name}</span>
                          <span className="flex items-center gap-2">
                            <span className="flex items-center gap-0.5 text-emerald-600"><CheckCircle2 className="h-3 w-3" />{fn.passed}</span>
                            <span className="flex items-center gap-0.5 text-rose-600"><XCircle className="h-3 w-3" />{fn.bugs}</span>
                            {fn.errors > 0 && <span className="flex items-center gap-0.5 text-amber-600"><AlertCircle className="h-3 w-3" />{fn.errors}</span>}
                            {fn.discarded > 0 && <span className="flex items-center gap-0.5 text-slate-400" title="Tests dropped before running: requested undefined fixtures">⊘{fn.discarded}</span>}
                            <span className="text-slate-400">/ {fn.total}</span>
                          </span>
                        </div>
                      ))}
                      {rt.functions.length === 0 && <div className="text-xs text-slate-400">No test detail recorded.</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

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