import { useState, useEffect } from "react";
import { Wrench, FileCode2, CheckCircle2, Lock } from "lucide-react";
import { StatCard } from "../components/Shared";
import type { SessionState } from "../hooks/useSession";
import type { Patch } from "../types";
import * as api from "../api";

function DiffBlock({ diff }: { diff: string }) {
  if (!diff) return <div className="text-sm text-slate-400">No changes</div>;
  return (
    <pre className="max-h-[300px] overflow-auto rounded-lg bg-slate-950 p-3 font-mono text-xs leading-relaxed">
      {diff.split("\n").map((line, i) => {
        let c = "text-slate-400";
        if (line.startsWith("+") && !line.startsWith("+++")) c = "text-emerald-400";
        else if (line.startsWith("-") && !line.startsWith("---")) c = "text-red-400";
        else if (line.startsWith("@@")) c = "text-blue-400 font-semibold";
        return <div key={i} className={c}>{line}</div>;
      })}
    </pre>
  );
}

export default function RepairScreen({ state, patch, autoMode }: { state: SessionState; patch: (p: Partial<SessionState>) => void; autoMode?: boolean }) {
  const [diffFile, setDiffFile] = useState("");
  const [diffContent, setDiffContent] = useState<string | null>(null);
  const [sessionConfig, setSessionConfig] = useState<any>(null);

  useEffect(() => {
    if (state.sessionId) {
      fetch(`/api/session/${state.sessionId}/config`).then(r => r.json()).then(d => setSessionConfig(d.config)).catch(() => {});
    }
  }, [state.sessionId]);

  async function repair() {
    if (!state.sessionId) return;
    patch({ loading: true, error: null });
    try {
      const r = await api.runRepair(state.sessionId);
      const v = await api.getVersions(state.sessionId).catch(() => []);
      patch({ repairResult: r, repairRound: r.repair_round, versions: v, loading: false });
    } catch (e: unknown) { patch({ loading: false, error: (e as Error).message }); }
  }

  async function loadDiff(f: string) {
    if (!state.sessionId) return;
    setDiffFile(f);
    try { setDiffContent(await api.getFileDiff(state.sessionId, f)); } catch { setDiffContent("Could not load diff."); }
  }

  const applied = (state.repairResult?.patches || []).filter((p: Patch) => p.applied);
  const patchedFiles = [...new Set(applied.map((p: Patch) => p.meta?.file as string).filter(Boolean))];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-xl font-semibold">
            LLM Repair
            {state.repairRound > 0 && <span className="ml-2 inline-block rounded-full bg-slate-900 px-2.5 py-0.5 text-xs text-white">Round {state.repairRound}</span>}
          </h2>
          <p className="mt-1 text-sm text-slate-500">The selected LLM generates patches for all static analysis findings.</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Show locked model from session config */}
          {sessionConfig && (
            <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
              <Lock className="h-3 w-3 text-slate-400" />
              <span className="font-medium text-slate-700">{sessionConfig.model_label || sessionConfig.model_name}</span>
            </div>
          )}
          {!autoMode && (
            <button onClick={repair} disabled={state.loading} className="flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">
              <Wrench className="h-4 w-4" />{state.loading ? "Repairing..." : "Repair Findings"}
            </button>
          )}
          {autoMode && state.loading && (
            <div className="flex items-center gap-2 text-sm text-indigo-600">
              <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" /> Running repair...
            </div>
          )}
        </div>
      </div>

      {state.error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{state.error}</div>}

      {state.repairResult && <>
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Files patched" value={patchedFiles.length} icon={FileCode2} />
          <StatCard label="Patches applied" value={state.repairResult.repaired_count} icon={CheckCircle2} />
          <StatCard label="Model" value={state.repairResult.provider_used} icon={Wrench} />
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="mb-3 font-semibold">Patches</h3>
          {applied.map((p: Patch, i: number) => <div key={i} className="mb-2 rounded-xl border p-3 text-sm">{p.description}</div>)}
          {applied.length === 0 && <div className="text-sm text-slate-500">No patches applied.</div>}
        </div>
        {patchedFiles.length > 0 && (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="mb-3 font-semibold">Code changes</h3>
            <div className="mb-3 flex flex-wrap gap-2">
              {patchedFiles.map(f => (
                <button key={f} onClick={() => loadDiff(f)} className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${diffFile === f ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200"}`}>{f}</button>
              ))}
            </div>
            {diffContent !== null && <DiffBlock diff={diffContent} />}
          </div>
        )}
      </>}
    </div>
  );
}
