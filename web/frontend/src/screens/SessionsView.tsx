/**
 * SessionsView: browse every session the pipeline has processed.
 *
 * QALLM is a research tool, so the durable on-disk history of past runs is
 * valuable. This lists each session's report directory (summary.json) and
 * lets the user open any one's headline stats and full markdown report.
 * Read-only; it reflects what the orchestrator wrote to QALLM_SESSIONS_DIR.
 */

import { useEffect, useState } from "react";
import {
  Library, ChevronRight, ChevronLeft, FileText, CheckCircle2,
  XCircle, DollarSign, FileCode,
} from "lucide-react";
import * as api from "../api";
import type { SessionCard } from "../api";

function basename(path: string | null): string {
  if (!path) return "(unknown source)";
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

function SessionList({ sessions, onSelect }: {
  sessions: SessionCard[];
  onSelect: (id: string) => void;
}) {
  if (!sessions.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-500">
        No processed sessions found yet. Run the pipeline (Pipeline tab) and
        completed sessions will appear here.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {sessions.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className="flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-indigo-300 hover:bg-indigo-50/30"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2 truncate font-semibold text-slate-800">
              <FileCode className="h-4 w-4 shrink-0 text-slate-400" />
              {basename(s.source)}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
              <span className="font-mono text-slate-400">{s.id}</span>
              {s.strategy && <><span className="text-slate-300">·</span><span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">{s.strategy}</span></>}
              {s.model && <span>{s.model}</span>}
              {s.profile_id && <><span className="text-slate-300">·</span><span>{s.profile_id}</span></>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-3 text-xs text-slate-400">
            {s.rounds_accepted_total != null && (
              <span className="flex items-center gap-1 text-emerald-600"><CheckCircle2 className="h-3.5 w-3.5" />{s.rounds_accepted_total}</span>
            )}
            {s.rounds_abandoned_total != null && s.rounds_abandoned_total > 0 && (
              <span className="flex items-center gap-1 text-rose-500"><XCircle className="h-3.5 w-3.5" />{s.rounds_abandoned_total}</span>
            )}
            <ChevronRight className="h-4 w-4" />
          </div>
        </button>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-white p-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-slate-700">{value ?? "—"}</div>
    </div>
  );
}

function SessionDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [summary, setSummary] = useState<Record<string, any>>({});
  const [report, setReport] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getLibrarySession(id)
      .then((r) => alive && setSummary(r.summary))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [id]);

  function loadReport() {
    if (report !== null) { setShowReport(!showReport); return; }
    api.getLibrarySessionReport(id)
      .then((r) => { setReport(r.markdown); setShowReport(true); })
      .catch(() => setReport(""));
  }

  const cost = (summary.cost as Record<string, any>) || {};

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ChevronLeft className="h-4 w-4" /> All sessions
      </button>
      <div>
        <h2 className="text-xl font-semibold text-slate-800">{basename(summary.source as string)}</h2>
        <p className="mt-1 font-mono text-xs text-slate-400">{id}</p>
      </div>

      {loading ? (
        <div className="py-8 text-center text-sm text-slate-400">Loading session…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Stat label="Strategy" value={summary.strategy} />
            <Stat label="Model" value={summary.model} />
            <Stat label="Profile" value={(summary.profile as any)?.profile_id} />
            <Stat label="Oracle" value={summary.oracle} />
            <Stat label="Functions verified" value={summary.functions_verified} />
            <Stat label="Rounds accepted" value={summary.rounds_accepted_total} />
            <Stat label="Rounds abandoned" value={summary.rounds_abandoned_total} />
            <Stat label="Halt reason" value={summary.halt_reason} />
          </div>

          <div className="flex flex-wrap gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {cost.total_cost_usd != null && (
              <span className="flex items-center gap-1"><DollarSign className="h-3 w-3" /> {Number(cost.total_cost_usd).toFixed(4)} total</span>
            )}
            {cost.total_tokens != null && <span>{cost.total_tokens} tokens</span>}
            {summary.lifecycle_stage != null && <span>stage: {String(summary.lifecycle_stage)}</span>}
          </div>

          <div>
            <button onClick={loadReport} className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              <FileText className="h-3.5 w-3.5" /> {showReport ? "Hide" : "View"} session report
            </button>
            {showReport && report !== null && (
              <pre className="mt-2 max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl bg-slate-900 p-4 font-mono text-[11px] leading-relaxed text-slate-100">
                {report || "(no report.md for this session)"}
              </pre>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function SessionsView() {
  const [sessions, setSessions] = useState<SessionCard[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.listLibrarySessions()
      .then((r) => alive && setSessions(r.sessions))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  if (selected) return <SessionDetail id={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Library className="h-5 w-5 text-indigo-500" />
        <h2 className="text-xl font-semibold text-slate-800">Session library</h2>
      </div>
      <p className="text-sm text-slate-500">
        Every session the pipeline has processed, newest first. Click one to see its configuration, accept/abandon totals, cost, and full report.
      </p>
      {loading ? (
        <div className="py-8 text-center text-sm text-slate-400">Loading sessions…</div>
      ) : (
        <SessionList sessions={sessions} onSelect={setSelected} />
      )}
    </div>
  );
}
