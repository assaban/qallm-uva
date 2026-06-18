import { Fragment, useEffect, useState } from "react";
import {
  getCrossEvaluation,
  type CrossEvaluation,
  type CrossEvalCell,
} from "../api";

// Outcome -> cell colour. Green pass, red fail, amber error, grey none.
const OUTCOME_BG: Record<string, string> = {
  pass: "bg-emerald-500 text-white",
  fail: "bg-rose-500 text-white",
  error: "bg-amber-500 text-white",
  none: "bg-slate-100 text-slate-400",
};
// Per-test status -> small heat cell colour.
const STATUS_BG: Record<string, string> = {
  passed: "bg-emerald-500",
  failed: "bg-rose-500",
  error: "bg-amber-500",
  skipped: "bg-slate-300",
};

function colKey(c: CrossEvalCell): string {
  return `${c.round_number}:${c.bucket}`;
}
function colLabel(round: number, bucket: string): string {
  const tag = bucket === "abandoned" ? " (aband)" : round === 0 ? " (base)" : "";
  return `R${round}${tag}`;
}

export default function CrossEvalTable({ sessionId }: { sessionId: string }) {
  const [data, setData] = useState<CrossEvaluation | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let live = true;
    getCrossEvaluation(sessionId)
      .then((res) => {
        if (!live) return;
        if (res.available && res.cells.length) setData(res);
        else setReason(res.reason ?? "No cross-evaluation available yet.");
      })
      .catch(() => live && setReason("Could not load cross-evaluation."));
    return () => {
      live = false;
    };
  }, [sessionId]);

  if (reason) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-700">Round comparison</h3>
        <p className="mt-1 text-xs text-slate-400">{reason}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-400">
        Loading round comparison…
      </div>
    );
  }

  // Stable ordered columns: every (round, bucket) pair that appears, sorted by
  // round then accepted-before-abandoned.
  const colSet = new Map<string, { round: number; bucket: string }>();
  for (const c of data.cells) colSet.set(colKey(c), { round: c.round_number, bucket: c.bucket });
  const cols = [...colSet.entries()].sort((a, b) =>
    a[1].round - b[1].round || (a[1].bucket === "lineage" ? -1 : 1),
  );

  // index: function -> colKey -> cell
  const byFn = new Map<string, Map<string, CrossEvalCell>>();
  for (const c of data.cells) {
    if (!byFn.has(c.function_name)) byFn.set(c.function_name, new Map());
    byFn.get(c.function_name)!.set(colKey(c), c);
  }

  const toggle = (fn: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(fn)) next.delete(fn); else next.add(fn);
      return next;
    });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-700">Round comparison</h3>
        <p className="text-xs text-slate-400">
          Final accumulated test suite run against every variant. Click a function for the per-test heat map.
        </p>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-white px-2 py-1.5 text-left font-semibold text-slate-500">Function</th>
              {cols.map(([k, m]) => (
                <th key={k} className="px-2 py-1.5 text-center font-semibold text-slate-500">
                  {colLabel(m.round, m.bucket)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.functions.map((fn) => {
              const row = byFn.get(fn) ?? new Map();
              const isOpen = expanded.has(fn);
              // Union of test names across this function's cells, in first-seen order.
              const testNames: string[] = [];
              const seen = new Set<string>();
              for (const [, m] of cols) {
                const cell = row.get(`${m.round}:${m.bucket}`);
                if (!cell) continue;
                for (const t of cell.tests) if (!seen.has(t.name)) { seen.add(t.name); testNames.push(t.name); }
              }
              return (
                <Fragment key={fn}>
                  <tr className="border-t border-slate-100">
                    <td className="sticky left-0 bg-white px-2 py-1.5">
                      <button onClick={() => toggle(fn)} className="flex items-center gap-1 font-mono font-medium text-slate-700 hover:text-slate-900">
                        <span className="text-slate-400">{isOpen ? "▾" : "▸"}</span>
                        {fn}()
                      </button>
                    </td>
                    {cols.map(([k, m]) => {
                      const cell = row.get(`${m.round}:${m.bucket}`);
                      if (!cell) return <td key={k} className="px-2 py-1.5 text-center text-slate-300">—</td>;
                      return (
                        <td key={k} className="px-1.5 py-1.5 text-center">
                          <span className={`inline-block min-w-[3.5rem] rounded px-1.5 py-0.5 text-[11px] font-semibold ${OUTCOME_BG[cell.outcome]}`}>
                            {cell.passed}/{cell.total}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                  {isOpen && testNames.map((tn) => (
                    <tr key={`${fn}:${tn}`} className="border-t border-slate-50 bg-slate-50/40">
                      <td className="sticky left-0 bg-slate-50/40 py-1 pl-6 pr-2 font-mono text-[10px] text-slate-500">{tn}</td>
                      {cols.map(([k, m]) => {
                        const cell = row.get(`${m.round}:${m.bucket}`);
                        const t = cell?.tests.find((x: import("../api").CrossEvalCellTest) => x.name === tn);
                        const cls = t ? STATUS_BG[t.status] ?? "bg-slate-200" : "bg-transparent";
                        return (
                          <td key={k} className="px-1.5 py-1 text-center">
                            <span className={`inline-block h-3 w-3 rounded-sm ${cls}`} title={t ? t.status : "not present"} />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-slate-400">
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" /> pass</span>
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-rose-500" /> fail</span>
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-amber-500" /> error</span>
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-sm bg-slate-300" /> skipped</span>
        <span className="ml-2">Cell shows pass/total under the common final suite.</span>
      </div>
    </div>
  );
}
