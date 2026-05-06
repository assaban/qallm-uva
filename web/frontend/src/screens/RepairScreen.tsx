import { useState } from "react";
import { Wrench, FileCode2, CheckCircle2 } from "lucide-react";
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

export default function RepairScreen({ state, patch }: { state: SessionState; patch: (p: Partial<SessionState>) => void }) {
  const [provider, setProvider] = useState("");
  const [diffFile, setDiffFile] = useState("");
  const [diffContent, setDiffContent] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  if (!loaded && state.sessionId) {
    api.getProviders().then(p => patch({ providers: p.configured })).catch(() => {});
    setLoaded(true);
  }

  async function repair() {
    if (!state.sessionId) return;
    patch({ loading: true, error: null });
    try {
      const r = await api.runRepair(state.sessionId, provider || undefined);
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
            LLM repairs the issues
            {state.repairRound > 0 && <span className="ml-2 inline-block rounded-full bg-slate-900 px-2.5 py-0.5 text-xs text-white">Round {state.repairRound}</span>}
          </h2>
          <p className="mt-1 text-sm text-slate-500">Code is snapshotted before each repair round.</p>
        </div>
        <div className="flex items-center gap-3">
          {state.providers.length > 0 && (
            <select value={provider} onChange={e => setProvider(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
              <option value="">Auto</option>
              {state.providers.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          )}
          <button onClick={repair} disabled={state.loading} className="flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">
            <Wrench className="h-4 w-4" />{state.loading ? "Repairing..." : "Repair Findings"}
          </button>
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
