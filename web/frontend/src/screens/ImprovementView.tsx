/**
 * ImprovementView: the observability panel.
 *
 * Answers, per round and per method (code unit / function), the questions:
 *   - Which quality indicators were tracked, and which improved or regressed?
 *   - Was the round accepted or abandoned, and why (judge rationale)?
 *   - What exactly did we ask the LLM, and what came back? (transcript)
 *
 * Data comes from GET /api/session/{id}/improvement, which the orchestrator
 * populates by writing improvement.json + transcript.json per round.
 */

import { useEffect, useState } from "react";
import {
  ArrowDownRight, ArrowUpRight, Minus, CheckCircle2, XCircle,
  ChevronRight, ChevronDown, MessageSquare, Sparkles, FlaskConical,
} from "lucide-react";
import * as api from "../api";
import type {
  ImprovementRound, ImprovementUnit, IndicatorDelta, LLMCall,
} from "../api";

const DIR_STYLE: Record<string, { color: string; bg: string; Icon: any; label: string }> = {
  improved:     { color: "text-emerald-700", bg: "bg-emerald-50", Icon: ArrowUpRight, label: "improved" },
  appeared:     { color: "text-emerald-700", bg: "bg-emerald-50", Icon: Sparkles, label: "new" },
  regressed:    { color: "text-rose-700", bg: "bg-rose-50", Icon: ArrowDownRight, label: "regressed" },
  disappeared:  { color: "text-rose-700", bg: "bg-rose-50", Icon: ArrowDownRight, label: "lost" },
  unchanged:    { color: "text-slate-500", bg: "bg-slate-50", Icon: Minus, label: "unchanged" },
};

function fmt(n: number | null): string {
  if (n === null || n === undefined) return "–";
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

function IndicatorRow({ ind }: { ind: IndicatorDelta }) {
  const style = DIR_STYLE[ind.direction] || DIR_STYLE.unchanged;
  const Icon = style.Icon;
  const deltaText =
    ind.measured_delta === null ? "" :
    `${ind.measured_delta > 0 ? "+" : ""}${fmt(ind.measured_delta)}`;
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-100 px-3 py-2 text-sm">
      <div className="min-w-0">
        <div className="truncate font-medium text-slate-700">{ind.name}</div>
        <div className="text-xs text-slate-400">
          {fmt(ind.parent_measured)} → {fmt(ind.variant_measured)}
          {ind.status_transition !== "n/a" && (
            <span className="ml-2">({ind.status_transition})</span>
          )}
        </div>
      </div>
      <div className={`flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold ${style.bg} ${style.color}`}>
        <Icon className="h-3.5 w-3.5" />
        {deltaText || style.label}
      </div>
    </div>
  );
}

function TranscriptViewer({ calls }: { calls: LLMCall[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!calls.length) {
    return <div className="px-3 py-2 text-xs text-slate-400">No LLM calls recorded for this unit this round.</div>;
  }
  return (
    <div className="space-y-2">
      {calls.map((c) => {
        const role = (c.context.role as string) || (c.context.stage as string) || "call";
        const fn = c.context.function as string | undefined;
        const isOpen = open === c.seq;
        return (
          <div key={c.seq} className="rounded-lg border border-slate-200 bg-white">
            <button
              onClick={() => setOpen(isOpen ? null : c.seq)}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
            >
              <span className="flex items-center gap-2">
                {isOpen ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                {role === "testgen" ? <FlaskConical className="h-4 w-4 text-indigo-500" /> : <MessageSquare className="h-4 w-4 text-amber-500" />}
                <span className="font-medium text-slate-700">
                  {role}{fn ? ` · ${fn}` : ""}
                </span>
              </span>
              <span className="shrink-0 text-xs text-slate-400">
                {c.input_tokens}+{c.output_tokens} tok · {c.latency_ms.toFixed(0)}ms
                {c.error ? <span className="ml-1 text-rose-500">· error</span> : ""}
              </span>
            </button>
            {isOpen && (
              <div className="space-y-2 border-t border-slate-100 px-3 py-2 text-xs">
                {c.error && (
                  <div className="rounded bg-rose-50 px-2 py-1 text-rose-700">Error: {c.error}</div>
                )}
                <Field label="System prompt" body={c.system_prompt} />
                <Field label="User prompt" body={c.user_prompt} />
                <Field label="Response" body={c.response_content} highlight />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Field({ label, body, highlight }: { label: string; body: string; highlight?: boolean }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
      <pre className={`max-h-64 overflow-auto whitespace-pre-wrap rounded-md p-2 font-mono text-[11px] leading-relaxed ${highlight ? "bg-slate-900 text-slate-100" : "bg-slate-50 text-slate-700"}`}>
        {body || "(empty)"}
      </pre>
    </div>
  );
}

function BugDetailView({ functions }: { functions: import("../api").FunctionBugDetail[] }) {
  if (!functions.length) {
    return <div className="px-1 py-2 text-xs text-slate-400">No verification results recorded for this round.</div>;
  }
  return (
    <div className="space-y-3">
      {functions.map((fn) => {
        const cov = fn.coverage_percent === null ? "n/a" : `${fn.coverage_percent.toFixed(0)}%`;
        return (
          <div key={fn.function} className="rounded-lg border border-slate-100">
            <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
              <span className="font-mono text-sm font-medium text-slate-700">{fn.function}()</span>
              <span className="flex shrink-0 items-center gap-2 text-xs">
                <span className="text-slate-400">{cov} cov</span>
                {fn.passed > 0 && <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-semibold text-emerald-700">{fn.passed} pass</span>}
                {fn.failed > 0 && <span className="rounded bg-rose-50 px-1.5 py-0.5 font-semibold text-rose-700">{fn.failed} bug{fn.failed > 1 ? "s" : ""}</span>}
                {fn.errors > 0 && <span className="rounded bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-700">{fn.errors} err</span>}
              </span>
            </div>
            <div className="divide-y divide-slate-50">
              {fn.all_tests.length === 0 && (
                <div className="px-3 py-2 text-xs text-slate-400">No tests executed.</div>
              )}
              {fn.all_tests.map((t, i) => {
                const isBug = t.status === "failed";
                const isErr = t.status === "error";
                const dot = isBug ? "bg-rose-500" : isErr ? "bg-amber-500" : t.status === "passed" ? "bg-emerald-500" : "bg-slate-300";
                return (
                  <div key={i} className="px-3 py-2">
                    <div className="flex items-center gap-2 text-xs">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
                      <span className="font-mono text-slate-700">{t.name}</span>
                      <span className={`ml-auto shrink-0 font-semibold ${isBug ? "text-rose-600" : isErr ? "text-amber-600" : t.status === "passed" ? "text-emerald-600" : "text-slate-400"}`}>
                        {t.status === "failed" ? "BUG" : t.status.toUpperCase()}
                      </span>
                    </div>
                    {/* The exact test body. For a passing test this is the
                        self-evident proof of success; for a failing one it
                        sits above the failure reason so both read together. */}
                    {t.body && (
                      <pre className="mt-1 max-h-56 overflow-auto whitespace-pre rounded bg-slate-50 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-slate-700">
                        {t.body}
                      </pre>
                    )}
                    {(isBug || isErr) && t.message && (
                      <div className="mt-1">
                        <div className="text-[10px] font-semibold uppercase tracking-wide text-rose-500">
                          {isBug ? "Why it failed" : "Error"}
                        </div>
                        <pre className="mt-0.5 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-slate-900 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-slate-100">
                          {t.message}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
              {fn.execution_error && (
                <div className="px-3 py-2">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-600">Execution error</div>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-amber-50 px-2 py-1.5 font-mono text-[11px] text-amber-800">{fn.execution_error}</pre>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function UnitCard({ unit }: { unit: ImprovementUnit }) {
  const totalBugs = unit.bug_detail.reduce((n, f) => n + f.failed, 0);
  const [tab, setTab] = useState<"bugs" | "deltas" | "transcript">("bugs");
  const imp = unit.improvement;
  const accepted = unit.accepted;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold text-slate-800">{unit.unit_id}</div>
          {imp && <div className="text-xs text-slate-500">{imp.headline}</div>}
        </div>
        {unit.is_baseline ? (
          <span className="shrink-0 rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">Baseline</span>
        ) : accepted ? (
          <span className="flex shrink-0 items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" />Accepted</span>
        ) : (
          <span className="flex shrink-0 items-center gap-1 rounded-md bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-700"><XCircle className="h-3.5 w-3.5" />Abandoned</span>
        )}
      </div>

      {imp?.judge_rationale && (
        <div className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <span className="font-semibold">Judge:</span> {imp.judge_rationale}
        </div>
      )}

      <div className="mb-3 flex gap-2 text-xs">
        <button onClick={() => setTab("bugs")} className={`rounded-md px-2.5 py-1 font-medium ${tab === "bugs" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>Bugs found by tests{totalBugs > 0 ? ` (${totalBugs})` : ""}</button>
        <button onClick={() => setTab("deltas")} className={`rounded-md px-2.5 py-1 font-medium ${tab === "deltas" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>Indicator deltas</button>
        <button onClick={() => setTab("transcript")} className={`rounded-md px-2.5 py-1 font-medium ${tab === "transcript" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>LLM transcript ({unit.llm_calls.length})</button>
      </div>

      {tab === "bugs" ? (
        <BugDetailView functions={unit.bug_detail} />
      ) : tab === "deltas" ? (
        imp && imp.dimensions.length ? (
          <div className="space-y-3">
            {imp.dimensions.map((dim) => (
              <div key={dim.dimension}>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{dim.dimension}</span>
                  <span className="text-[11px] text-slate-400">{dim.parent_status} → {dim.variant_status}</span>
                </div>
                <div className="space-y-1.5">
                  {dim.indicators.map((ind) => <IndicatorRow key={ind.name} ind={ind} />)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-400">
            {unit.is_baseline
              ? "Baseline round: the starting point, no comparison yet."
              : "No indicator deltas recorded."}
          </div>
        )
      ) : (
        <TranscriptViewer calls={unit.llm_calls} />
      )}
    </div>
  );
}

export default function ImprovementView({ sessionId }: { sessionId: string }) {
  const [rounds, setRounds] = useState<ImprovementRound[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openRound, setOpenRound] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getImprovement(sessionId)
      .then((res) => {
        if (!alive) return;
        if (!res.available) { setError(res.reason || "No data yet."); setRounds([]); }
        else {
          setRounds(res.rounds);
          // Open the first repair round by default (skip baseline).
          const firstRepair = res.rounds.find(r => r.round > 0);
          setOpenRound(firstRepair ? firstRepair.round : (res.rounds[0]?.round ?? null));
        }
      })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [sessionId]);

  if (loading) return <div className="py-8 text-center text-sm text-slate-400">Loading improvement audit…</div>;
  if (error) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">{error}</div>;
  if (!rounds.length) return null;

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Improvement audit</h2>
        <p className="mt-1 text-sm text-slate-500">Per round and per method: the bugs found by generated tests (discovered by execution, not static analysis), which quality indicators moved, the accept/abandon verdict, and the exact prompts sent to the model.</p>
      </div>
      {rounds.map((r) => {
        const isOpen = openRound === r.round;
        const isBaseline = r.round === 0;
        const accepted = r.units.filter(u => u.accepted).length;
        const abandoned = r.units.filter(u => !u.accepted && !u.is_baseline).length;
        return (
          <div key={r.round} className="rounded-2xl border border-slate-200 bg-white/70 shadow-sm">
            <button
              onClick={() => setOpenRound(isOpen ? null : r.round)}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            >
              <span className="flex items-center gap-2 font-semibold text-slate-800">
                {isOpen ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                {isBaseline ? "Round 0 · Baseline" : `Round ${r.round}`}
              </span>
              <span className="flex shrink-0 items-center gap-2 text-xs">
                <span className="text-slate-400">{r.units.length} method(s)</span>
                {!isBaseline && accepted > 0 && <span className="rounded bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">{accepted} accepted</span>}
                {!isBaseline && abandoned > 0 && <span className="rounded bg-rose-50 px-2 py-0.5 font-semibold text-rose-700">{abandoned} abandoned</span>}
              </span>
            </button>
            {isOpen && (
              <div className="space-y-3 border-t border-slate-100 p-4">
                {r.units.map((u) => <UnitCard key={`${u.bucket}-${u.unit_id}`} unit={u} />)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
