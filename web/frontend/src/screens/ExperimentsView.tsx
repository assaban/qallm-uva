/**
 * ExperimentsView: browse historical HumanEvalFix validation runs.
 *
 * Makes experiment results accessible and auditable in the UI. Three
 * levels: a list of runs, a selected run's per-(strategy, model)
 * aggregate comparison plus per-problem detail, and the run's markdown
 * report. Read-only; experiments are launched from the CLI (they take
 * hours and download datasets), this surfaces what they produced.
 */

import { useEffect, useState, useRef, useCallback } from "react";
import {
  FlaskConical, ChevronRight, ChevronLeft, Bug, Wrench,
  Clock, DollarSign, AlertTriangle, FileText, Play,
} from "lucide-react";
import * as api from "../api";
import type {
  ExperimentRunSummary, ExperimentAggregate, ExperimentProblemResult,
} from "../api";

function pct(x: number): string {
  return `${(x * 100).toFixed(0)}%`;
}

function RunList({ runs, onSelect }: {
  runs: ExperimentRunSummary[];
  onSelect: (id: string) => void;
}) {
  if (!runs.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
        No experiment runs found yet. Run one from the CLI (see
        <span className="font-mono"> docs/experiments/humaneval.md</span>), then it appears here.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {runs.map((r) => (
        <button
          key={r.id}
          onClick={() => onSelect(r.id)}
          className="flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-indigo-300 hover:bg-indigo-50/30"
        >
          <div className="min-w-0">
            <div className="truncate font-semibold text-slate-800">{r.id}</div>
            <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-slate-500">
              {r.strategies.map((s) => (
                <span key={s} className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">{s}</span>
              ))}
              <span className="text-slate-300">·</span>
              <span>{r.models.join(", ")}</span>
              {r.rounds != null && <><span className="text-slate-300">·</span><span>{r.rounds} rounds</span></>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-3 text-xs text-slate-400">
            <span>{r.n_results} results</span>
            <ChevronRight className="h-4 w-4" />
          </div>
        </button>
      ))}
    </div>
  );
}

function AggregateCard({ agg }: { agg: ExperimentAggregate }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="rounded-md bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white">{agg.strategy}</span>
        <span className="truncate text-xs text-slate-500">{agg.model}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-emerald-50 p-2.5">
          <div className="flex items-center gap-1 text-xs font-medium text-emerald-700"><Bug className="h-3.5 w-3.5" /> Bug detection</div>
          <div className="mt-0.5 text-xl font-semibold text-emerald-800">{pct(agg.bug_detection_rate)}</div>
          <div className="text-[11px] text-emerald-600">{agg.n_bug_detected}/{agg.n_problems - agg.n_errored}</div>
        </div>
        <div className="rounded-lg bg-indigo-50 p-2.5">
          <div className="flex items-center gap-1 text-xs font-medium text-indigo-700"><Wrench className="h-3.5 w-3.5" /> Repair success</div>
          <div className="mt-0.5 text-xl font-semibold text-indigo-800">{pct(agg.repair_success_rate)}</div>
          <div className="text-[11px] text-indigo-600">{agg.n_repair_successful}/{agg.n_problems - agg.n_errored}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {agg.mean_rounds.toFixed(1)} rounds</span>
        <span className="flex items-center gap-1"><DollarSign className="h-3 w-3" /> {agg.mean_cost_usd.toFixed(3)}/problem</span>
        <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {agg.mean_elapsed_seconds.toFixed(0)}s/problem</span>
        {agg.n_errored > 0 && <span className="flex items-center gap-1 text-amber-600"><AlertTriangle className="h-3 w-3" /> {agg.n_errored} errored</span>}
      </div>
    </div>
  );
}

function ProblemTable({ results }: { results: ExperimentProblemResult[] }) {
  if (!results.length) return <div className="text-xs text-slate-400">No per-problem results.</div>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Task</th>
            <th className="px-3 py-2 text-left font-medium">Strategy</th>
            <th className="px-3 py-2 text-center font-medium">Bug detected</th>
            <th className="px-3 py-2 text-center font-medium">Repaired</th>
            <th className="px-3 py-2 text-right font-medium">Rounds</th>
            <th className="px-3 py-2 text-right font-medium">Cov</th>
            <th className="px-3 py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {results.map((r, i) => (
            <tr key={i} className={r.error ? "bg-amber-50/50" : ""}>
              <td className="px-3 py-1.5 font-mono text-slate-700">{r.task_id}</td>
              <td className="px-3 py-1.5 text-slate-500">{r.strategy}</td>
              <td className="px-3 py-1.5 text-center">{r.error ? "—" : r.bug_detected ? <span className="text-emerald-600 font-semibold">yes</span> : <span className="text-slate-400">no</span>}</td>
              <td className="px-3 py-1.5 text-center">{r.error ? "—" : r.repair_successful ? <span className="text-indigo-600 font-semibold">yes</span> : <span className="text-slate-400">no</span>}</td>
              <td className="px-3 py-1.5 text-right text-slate-500">{r.rounds_run}</td>
              <td className="px-3 py-1.5 text-right text-slate-500">{r.final_coverage?.toFixed(0)}%</td>
              <td className="px-3 py-1.5 text-right text-slate-500">${r.cost_usd?.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [aggregates, setAggregates] = useState<ExperimentAggregate[]>([]);
  const [manifest, setManifest] = useState<Record<string, unknown>>({});
  const [results, setResults] = useState<ExperimentProblemResult[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.getExperiment(id), api.getExperimentResults(id)])
      .then(([run, res]) => {
        if (!alive) return;
        setAggregates(run.aggregates);
        setManifest(run.manifest);
        setResults(res.results);
      })
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [id]);

  function loadReport() {
    if (report !== null) { setShowReport(!showReport); return; }
    api.getExperimentReport(id).then((r) => { setReport(r.markdown); setShowReport(true); }).catch(() => setReport(""));
  }

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ChevronLeft className="h-4 w-4" /> All runs
      </button>
      <div>
        <h2 className="text-xl font-semibold text-slate-800">{id}</h2>
        <p className="mt-1 text-sm text-slate-500">
          {String(manifest.sample_size ?? "all")} problems · {(manifest.strategies as string[] || []).join(", ")} · {(manifest.models as string[] || []).join(", ")}
        </p>
      </div>

      {loading ? (
        <div className="py-8 text-center text-sm text-slate-400">Loading run…</div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {aggregates.map((a, i) => <AggregateCard key={i} agg={a} />)}
          </div>

          {aggregates.length >= 2 && (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Compare bug-detection rates across strategies above. The thesis claim is that the feedback (RL) strategy detects more bugs than one-shot or property-based generation, evidence that LLM-guided, execution-based test generation does real work over static analysis.
            </p>
          )}

          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-700">Per-problem results</h3>
            <ProblemTable results={results} />
          </div>

          <div>
            <button onClick={loadReport} className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              <FileText className="h-3.5 w-3.5" /> {showReport ? "Hide" : "View"} markdown report
            </button>
            {showReport && report !== null && (
              <pre className="mt-2 max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-4 font-mono text-[11px] leading-relaxed text-slate-100">
                {report || "(no report.md for this run)"}
              </pre>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function CatalogPanel({ onLaunched }: { onLaunched: () => void }) {
  const [specs, setSpecs] = useState<import("../api").ExperimentSpec[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [sampleSize, setSampleSize] = useState<string>("10");
  const [strategies, setStrategies] = useState<string[]>(["feedback", "oneshot"]);
  const [model, setModel] = useState("openai:gpt-4o-mini");
  const [rounds, setRounds] = useState("3");
  const [progressRunId, setProgressRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<import("../api").ExperimentProgress | null>(null);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.listExperimentCatalog().then((r) => alive && setSpecs(r.experiments)).catch(() => {});
    return () => { alive = false; };
  }, []);

  // Keep a stable ref to onLaunched so the polling effect does not restart
  // every time the parent re-renders (which created a fresh callback and,
  // via setRuns -> re-render, an unbounded loop of polling requests).
  const onLaunchedRef = useRef(onLaunched);
  useEffect(() => { onLaunchedRef.current = onLaunched; }, [onLaunched]);

  // Poll progress while a run is active. Restarts only when the run id
  // changes, never on callback identity. Reschedules a tick ONLY while the
  // run is genuinely still running; any terminal or untracked state stops
  // the loop and (once) refreshes the historical run list.
  useEffect(() => {
    if (!progressRunId) return;
    let alive = true;
    let notified = false;
    const finish = () => {
      if (notified) return;
      notified = true;
      onLaunchedRef.current();
    };
    const tick = () => {
      api.getExperimentProgress(progressRunId).then((p) => {
        if (!alive) return;
        setProgress(p);
        if (p.tracked && p.status === "running") {
          setTimeout(tick, 1500);
        } else {
          // done, failed, or untracked: stop polling, refresh once.
          finish();
        }
      }).catch(() => {
        // On a transient error, stop rather than hammering the server.
        if (alive) finish();
      });
    };
    tick();
    return () => { alive = false; };
  }, [progressRunId]);

  function toggleStrategy(s: string) {
    setStrategies((prev) => prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]);
  }

  async function launch(id: string) {
    setLaunching(true);
    setLaunchError(null);
    try {
      const r = await api.launchExperiment(id, {
        models: [model],
        strategies,
        sample_size: sampleSize ? Number(sampleSize) : undefined,
        rounds: Number(rounds),
      });
      setProgressRunId(r.run_id);
    } catch (e) {
      setLaunchError(e instanceof Error ? e.message : "Launch failed");
    } finally {
      setLaunching(false);
    }
  }

  if (!specs.length) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-700">Available experiments</h3>
      {specs.map((spec) => {
        const open = openId === spec.id;
        return (
          <div key={spec.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-slate-800">{spec.name}</div>
                <p className="mt-1 text-sm text-slate-500">{spec.summary}</p>
              </div>
              <button
                onClick={() => setOpenId(open ? null : spec.id)}
                className="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                {open ? "Close" : "Details & run"}
              </button>
            </div>

            {open && (
              <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
                {/* Dataset details + citation */}
                <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                  <div><span className="text-slate-400">Dataset:</span> <a href={spec.dataset_url} target="_blank" rel="noreferrer" className="text-indigo-600 underline">{spec.dataset_id}</a></div>
                  <div><span className="text-slate-400">Problems:</span> {spec.n_problems}</div>
                  <div className="sm:col-span-2"><span className="text-slate-400">Measures:</span> {spec.measures.join(", ")}</div>
                  <div className="sm:col-span-2"><span className="text-slate-400">Citation:</span> {spec.citation}</div>
                </div>
                {spec.notes && <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{spec.notes}</p>}

                {/* Launch form */}
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-xs text-slate-600">Sample size
                    <input value={sampleSize} onChange={(e) => setSampleSize(e.target.value)} placeholder="blank = all 164" className="mt-1 w-full rounded-lg border p-2 text-sm" />
                  </label>
                  <label className="text-xs text-slate-600">Model
                    <input value={model} onChange={(e) => setModel(e.target.value)} className="mt-1 w-full rounded-lg border p-2 text-sm" />
                  </label>
                  <label className="text-xs text-slate-600">Rounds
                    <input value={rounds} onChange={(e) => setRounds(e.target.value)} className="mt-1 w-full rounded-lg border p-2 text-sm" />
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400">Strategies:</span>
                  {["feedback", "oneshot", "hypothesis"].map((s) => (
                    <button key={s} onClick={() => toggleStrategy(s)}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${strategies.includes(s) ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600"}`}>
                      {s}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={() => launch(spec.id)}
                    disabled={launching || strategies.length === 0}
                    className="flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    <Play className="h-3.5 w-3.5" /> {launching ? "Launching…" : "Launch run"}
                  </button>
                  <span className="text-xs text-slate-400">Needs network and (for hosted models) credentials. Long runs continue in the background.</span>
                </div>
                {launchError && <p className="text-xs text-rose-600">{launchError}</p>}

                {/* Live progress */}
                {progress && progress.tracked && (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-700">
                        {progress.status === "running" ? "Running" : progress.status === "done" ? "Complete" : "Failed"} · {progress.completed}/{progress.total}
                      </span>
                      <span className="text-slate-500">
                        {progress.bug_detected} bugs · {progress.repair_successful} repaired{progress.errored ? ` · ${progress.errored} errored` : ""}
                      </span>
                    </div>
                    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
                      <div className="h-full bg-indigo-500" style={{ width: `${progress.total ? (100 * (progress.completed || 0) / progress.total) : 0}%` }} />
                    </div>
                    {progress.error && <p className="mt-2 text-xs text-rose-600">{progress.error}</p>}
                    {progress.log && progress.log.length > 0 && (
                      <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded bg-slate-900 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-slate-100">
                        {progress.log.slice(-20).map((l) =>
                          `${l.task_id} [${l.strategy}/${l.model}] ${l.error ? "ERROR " + l.error : (l.bug_detected ? "bug" : "no-bug") + (l.repair_successful ? " repaired" : "")}`
                        ).join("\n")}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function ExperimentsView() {
  const [runs, setRuns] = useState<ExperimentRunSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.listExperiments()
      .then((r) => alive && setRuns(r.runs))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  if (selected) return <RunDetail id={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-5 w-5 text-indigo-500" />
        <h2 className="text-xl font-semibold text-slate-800">Validation experiments</h2>
      </div>
      <p className="text-sm text-slate-500">
        HumanEvalFix benchmark runs: how well QALLM detects and repairs known bugs across strategies and models. Click a run to see its strategy comparison and per-problem detail.
      </p>
      <CatalogPanel onLaunched={useCallback(() => { api.listExperiments().then((r) => setRuns(r.runs)).catch(() => {}); }, [])} />
      <h3 className="pt-2 text-sm font-semibold text-slate-700">Historical runs</h3>
      {loading ? (
        <div className="py-8 text-center text-sm text-slate-400">Loading runs…</div>
      ) : (
        <RunList runs={runs} onSelect={setSelected} />
      )}
    </div>
  );
}
