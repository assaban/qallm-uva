import { useState, useEffect } from "react";
import { FlaskConical, Play } from "lucide-react";
import type { SessionState } from "../hooks/useSession";
import type { FunctionEntry } from "../types";
import * as api from "../api";

const ORACLES: Record<string, { title: string; desc: string }> = {
  crash: { title: "Crash oracle", desc: "Feeds edge cases (empty inputs, None, overflow) and asserts the function fails cleanly rather than crashing." },
  property: { title: "Property oracle", desc: "Checks output invariants: correct return types, size relationships, value range constraints." },
  metamorphic: { title: "Metamorphic oracle", desc: "Tests input/output relationships: permutations, negation, composition. Catches logic bugs without expected outputs." },
};

export default function TestGenScreen({ state, patch }: { state: SessionState; patch: (p: Partial<SessionState>) => void }) {
  const [oracle, setOracle] = useState("crash");
  const [model, setModel] = useState("");
  const [rounds, setRounds] = useState(5);
  const [models, setModels] = useState<string[]>([]);
  const [fns, setFns] = useState<FunctionEntry[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!state.sessionId) return;
    api.getModels().then(m => { setModels(m.configured); if (m.configured.length && !model) setModel(m.configured[0]); }).catch(() => {});
    api.getFunctions(state.sessionId).then(f => { setFns(f); setSel(new Set(f.map(x => x.name))); }).catch(() => {});
  }, [state.sessionId]);

  function toggle(name: string) {
    setSel(prev => { const n = new Set(prev); if (n.has(name)) n.delete(name); else n.add(name); return n; });
  }

  async function run() {
    if (!state.sessionId || !model) return;
    patch({ loading: true, error: null });
    try {
      const r = await api.runTestGen(state.sessionId, model, oracle, rounds);
      patch({ testGenResult: r, loading: false });
    } catch (e: unknown) { patch({ loading: false, error: (e as Error).message }); }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold">Generate tests on repaired code</h2>
          <p className="mt-1 text-sm text-slate-500">The test generator creates test cases, executes them, scores quality, then improves in subsequent rounds.</p>

          {state.versions.length > 2 && (
            <div className="mt-4 rounded-xl border bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-600">Code version</label>
              <select className="mt-1 w-full rounded-lg border px-3 py-1.5 text-sm" onChange={async e => {
                await api.restoreVersion(state.sessionId!, Number(e.target.value));
                const f = await api.getFunctions(state.sessionId!);
                setFns(f); setSel(new Set(f.map(x => x.name)));
              }}>
                {state.versions.map(v => <option key={v.round} value={v.round}>{v.label} ({v.files} files)</option>)}
              </select>
            </div>
          )}

          <div className="mt-4">
            <div className="mb-2 text-sm font-medium">Functions ({fns.length})</div>
            <div className="max-h-[160px] space-y-1 overflow-auto rounded-xl border p-2">
              {fns.map(f => (
                <label key={f.name} className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={sel.has(f.name)} onChange={() => toggle(f.name)} className="rounded" />
                  <span className="font-mono text-xs">{f.name}</span>
                  <span className="text-xs text-slate-400">({f.file}:{f.lineno})</span>
                </label>
              ))}
              {fns.length === 0 && <div className="p-2 text-xs text-slate-400">No extractable functions.</div>}
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div>
              <label className="text-xs font-medium text-slate-600">Oracle</label>
              <select value={oracle} onChange={e => setOracle(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-1.5 text-sm">
                <option value="crash">Crash</option><option value="property">Property</option><option value="metamorphic">Metamorphic</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600">Model</label>
              <select value={model} onChange={e => setModel(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-1.5 text-sm">
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600">Rounds</label>
              <input type="number" value={rounds} onChange={e => setRounds(Number(e.target.value))} min={1} max={20} className="mt-1 w-full rounded-lg border px-3 py-1.5 text-sm" />
            </div>
          </div>

          <button onClick={run} disabled={state.loading || !model || sel.size === 0}
            className="mt-5 flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50">
            <Play className="h-4 w-4" />{state.loading ? "Generating..." : "Generate and run tests"}
          </button>
        </div>

        <div className="space-y-6">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="font-semibold">What is an oracle?</h3>
            <p className="mt-2 text-sm text-slate-600">Without a specification, the test generator needs a strategy to decide if a test passes or fails. The oracle is that strategy.</p>
            <div className="mt-4 space-y-3">
              {Object.entries(ORACLES).map(([k, v]) => (
                <div key={k} className={`rounded-xl border p-3 transition ${oracle === k ? "border-slate-900 bg-slate-50" : "border-slate-200"}`}>
                  <div className="text-sm font-medium">{v.title}</div>
                  <div className="mt-1 text-xs text-slate-600">{v.desc}</div>
                </div>
              ))}
            </div>
          </div>
          {state.testGenResult && (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6">
              <div className="flex items-center gap-2"><FlaskConical className="h-5 w-5 text-emerald-600" /><h3 className="font-semibold text-emerald-900">Tests completed</h3></div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-emerald-700">Functions:</span> {state.testGenResult.total_functions}</div>
                <div><span className="text-emerald-700">Bugs:</span> {state.testGenResult.total_bugs}</div>
                <div><span className="text-emerald-700">Model:</span> {state.testGenResult.model}</div>
                <div><span className="text-emerald-700">Oracle:</span> {state.testGenResult.oracle}</div>
              </div>
              <p className="mt-3 text-xs text-emerald-700">Proceed to Step 6 for learning curve and results.</p>
            </div>
          )}
        </div>
      </div>
      {state.error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{state.error}</div>}
    </div>
  );
}
