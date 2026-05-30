/**
 * Shared "Report lineage and verdict" rendering.
 *
 * Extracted from ResultsScreen so the session library can show the exact
 * same per-unit lineage and verdict panels as the pipeline's final report.
 * Both the live pipeline result and a historical session loaded from disk
 * carry tracks in the same UnitTrackView shape, so one component serves
 * both.
 */

import { CheckCircle2, XCircle, Minus } from "lucide-react";
import type {
  UnitTrackView, LineageEntryView, AbandonedEntryView,
} from "../types";

// Pretty-print the judge outcome with an icon and colour.
export function OutcomeBadge({ outcome }: { outcome: string }) {
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

// One per-unit panel: lineage and abandoned variants.
export function UnitTrackPanel({ unitId, track }: { unitId: string; track: UnitTrackView }) {
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

// The full per-unit lineage section (header + panels), as shown on the
// pipeline final report.
export function LineageReport({ tracks }: { tracks: Record<string, UnitTrackView> }) {
  if (!tracks || Object.keys(tracks).length === 0) {
    return <div className="text-xs text-slate-400">No per-unit lineage recorded for this session.</div>;
  }
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-bold uppercase text-slate-500">Per-unit lineage</h3>
      {Object.entries(tracks).map(([unitId, track]) => (
        <UnitTrackPanel key={unitId} unitId={unitId} track={track} />
      ))}
    </div>
  );
}
