import { useRef, useState, useEffect } from "react";
import {
  Upload, Settings2, Cpu, FlaskConical, Layers, Play, MousePointerClick,
  ChevronDown, ChevronRight, Scale, Wrench, TestTube2, Gauge,
} from "lucide-react";
import * as api from "../api";

interface ModelEntry { id: string; label: string; provider: string; available: boolean; }

const STRATEGY_INFO: Record<string, { title: string; desc: string }> = {
  rl: {
    title: "RL-guided (iterative feedback)",
    desc: "The LLM generates tests, executes them, scores the results with a reward function, then uses the feedback to generate better tests in subsequent rounds. This is the proposed method and the core thesis contribution.",
  },
  oneshot: {
    title: "One-shot (single generation)",
    desc: "The LLM generates tests once without feedback. This ablation isolates the LLM's contribution from the RL loop's contribution. Used as Strategy (b) in the three-strategy comparison.",
  },
  hypothesis: {
    title: "Hypothesis (property-based, no LLM)",
    desc: "Generates random typed inputs using the Hypothesis library with automatic shrinking. No LLM is involved. This is the non-trivial control group, Strategy (a) in the thesis.",
  },
};

const ORACLE_INFO: Record<string, { title: string; desc: string }> = {
  crash: {
    title: "Crash oracle",
    desc: "Feeds edge-case inputs (empty lists, None, zero, overflow) and asserts the function does not raise unhandled exceptions. The simplest but most effective oracle: if the code crashes on valid-typed inputs, it has a bug.",
  },
  property: {
    title: "Property oracle",
    desc: "Checks output invariants derivable from docstrings and type hints: correct return types, value range constraints, size relationships. Catches logic errors where the code runs but returns wrong results.",
  },
  metamorphic: {
    title: "Metamorphic oracle",
    desc: "Tests consistent relationships between related inputs: sorting the input to a monotonic function should yield sorted output; doubling the input should double the output. Catches subtle logic bugs without needing expected values.",
  },
};

// Explanations for the new advanced controls. Keep these accurate and brief.
const JUDGE_INFO: Record<string, string> = {
  lexicographic:
    "Default. Compares dimensions in priority order (Security, Reliability, Maintainability, Reproducibility, FAIRness). High-priority regression rejects; low-priority improvement accepts. Deterministic; no extra LLM cost.",
  strict:
    "Any regression on any dimension rejects the round. Conservative; useful when you want zero tolerance.",
  model:
    "LLM compares parent and variant verdicts with structured JSON output. Falls back to Strict on parse errors. Adds one LLM call per round per unit; useful for hard cases.",
};

const STABILITY_INFO: Record<string, string> = {
  frozen:
    "Tests are generated once and reused across all rounds. The repair model improves to pass a fixed test suite. This is the default and matches the verification-gap claim.",
  per_round:
    "Tests are regenerated each round. Tests adapt to the repair model's current variant. More expensive but exercises both subsystems together.",
};

const POLICY_INFO: Record<string, string> = {
  grow:
    "New tests accumulate across rounds. Catches regressions; tests from earlier rounds keep guarding the function. Default.",
  replay_only:
    "Only the latest round's tests run. Faster but loses regression coverage.",
};

export default function UploadScreen({ state, patch, onSessionReady }: any) {
  // Base config (always shown).
  const [config, setConfig] = useState({
    stage: "implementation",
    strategy: "rl",
    oracle: "crash",
    rounds: 5,
    model_name: "",
  });

  // Advanced config (under expandable panel, all optional).
  const [advanced, setAdvanced] = useState<{
    repair_model?: string;
    testgen_model?: string;
    judge_strategy: "strict" | "lexicographic" | "model";
    test_stability: "frozen" | "per_round";
    generation_policy: "replay_only" | "grow";
    max_tokens?: number;
    max_seconds?: number;
    max_round_seconds?: number;
    max_cost_usd?: number;
  }>({
    judge_strategy: "lexicographic",
    test_stability: "frozen",
    generation_policy: "grow",
  });

  const [autoMode, setAutoMode] = useState(false);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileNames, setFileNames] = useState<string[]>([]);
  const submitting = useRef(false);

  useEffect(() => {
    api.getModels().then((res: any) => {
      const list: ModelEntry[] = res.models || [];
      setModels(list);
      const first = list.find(m => m.available);
      if (first && !config.model_name) setConfig(prev => ({ ...prev, model_name: first.id }));
    }).catch(() => {});

    api.getVerificationStrategies().then(p => {
      setStrategies(p.configured || []);
    }).catch(() => {});
  }, []);

  function handleFileChange() {
    const files = fileRef.current?.files;
    if (files) setFileNames(Array.from(files).map(f => f.name));
  }

  async function handleStart() {
    const files = fileRef.current?.files;
    if (!files?.length || !config.model_name || submitting.current) return;
    submitting.current = true;

    patch({ loading: true, error: null });
    try {
      // Merge base and advanced. The api layer drops undefined fields so
      // the server uses its own defaults for anything we don't specify.
      const fullConfig = { ...config, ...advanced };
      const data = await api.uploadFiles(files, fullConfig);
      patch({ sessionId: data.session_id, files: data.files, selectedFiles: data.files, loading: false });
      // Pass session id + files explicitly: state.sessionId is not yet
      // updated at this point because React state updates are async.
      onSessionReady(autoMode, data.session_id, data.files);
    } catch (e: any) {
      patch({ loading: false, error: e.message });
      submitting.current = false;
    }
  }

  const selectedModel = models.find(m => m.id === config.model_name);
  const selectedStrategy = STRATEGY_INFO[config.strategy];
  const selectedOracle = ORACLE_INFO[config.oracle];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Left: configuration */}
      <div className="rounded-2xl border bg-white p-6 shadow-sm space-y-5">
        <h2 className="text-xl font-semibold">Research Pipeline Setup</h2>

        {/* Model selection */}
        <div className="space-y-1.5">
          <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase"><Cpu className="h-3.5 w-3.5" /> LLM Model</label>
          <select value={config.model_name} onChange={e => setConfig({ ...config, model_name: e.target.value })} className="w-full rounded-xl border p-2.5 text-sm">
            <option value="" disabled>Select a model...</option>
            {models.map(m => (
              <option key={m.id} value={m.id} disabled={!m.available}>
                {m.label}{!m.available ? " (not configured)" : ""}
              </option>
            ))}
          </select>
          {selectedModel && !selectedModel.available && (
            <p className="text-xs text-red-500">
              Set {selectedModel.provider === "openai" ? "OPENAI_API_KEY" : selectedModel.provider === "anthropic" ? "ANTHROPIC_API_KEY" : "OLLAMA_BASE_URL"} to enable this model.
            </p>
          )}
        </div>

        {/* Strategy + Oracle */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase"><Layers className="h-3.5 w-3.5" /> Strategy</label>
            <select value={config.strategy} onChange={e => setConfig({ ...config, strategy: e.target.value })} className="w-full rounded-xl border p-2.5 text-sm">
              {strategies.map(s => <option key={s} value={s}>{STRATEGY_INFO[s]?.title || s}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase"><FlaskConical className="h-3.5 w-3.5" /> Oracle</label>
            <select value={config.oracle} onChange={e => setConfig({ ...config, oracle: e.target.value })} className="w-full rounded-xl border p-2.5 text-sm">
              {Object.entries(ORACLE_INFO).map(([k, v]) => <option key={k} value={k}>{v.title}</option>)}
            </select>
          </div>
        </div>

        {/* Rounds (hidden for hypothesis) */}
        {config.strategy !== "hypothesis" && (
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-500 uppercase">Feedback Rounds</label>
            <input type="number" min={1} max={20} value={config.rounds} onChange={e => setConfig({ ...config, rounds: Number(e.target.value) })} className="w-full rounded-xl border p-2.5 text-sm" />
          </div>
        )}

        {/* Advanced settings, collapsible */}
        <div className="border-t pt-4">
          <button
            type="button"
            onClick={() => setAdvancedOpen(!advancedOpen)}
            className="flex w-full items-center justify-between text-xs font-bold text-slate-500 uppercase hover:text-slate-700"
          >
            <span className="flex items-center gap-1.5">
              <Settings2 className="h-3.5 w-3.5" /> Advanced settings
            </span>
            {advancedOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>

          {advancedOpen && (
            <div className="mt-4 space-y-4 rounded-xl bg-slate-50 p-4">
              {/* Separate models for repair vs test gen */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase">
                    <Wrench className="h-3.5 w-3.5" /> Repair model
                  </label>
                  <select
                    value={advanced.repair_model || ""}
                    onChange={e => setAdvanced({ ...advanced, repair_model: e.target.value || undefined })}
                    className="w-full rounded-xl border p-2 text-xs"
                  >
                    <option value="">(use default)</option>
                    {models.filter(m => m.available).map(m => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase">
                    <TestTube2 className="h-3.5 w-3.5" /> Test-gen model
                  </label>
                  <select
                    value={advanced.testgen_model || ""}
                    onChange={e => setAdvanced({ ...advanced, testgen_model: e.target.value || undefined })}
                    className="w-full rounded-xl border p-2 text-xs"
                  >
                    <option value="">(use default)</option>
                    {models.filter(m => m.available).map(m => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Judge strategy */}
              <div className="space-y-1.5">
                <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase">
                  <Scale className="h-3.5 w-3.5" /> Judge strategy
                </label>
                <select
                  value={advanced.judge_strategy}
                  onChange={e => setAdvanced({ ...advanced, judge_strategy: e.target.value as any })}
                  className="w-full rounded-xl border p-2 text-xs"
                >
                  <option value="lexicographic">Lexicographic (default)</option>
                  <option value="strict">Strict</option>
                  <option value="model">Model (LLM judge)</option>
                </select>
                <p className="text-xs text-slate-500">{JUDGE_INFO[advanced.judge_strategy]}</p>
              </div>

              {/* Test stability + generation policy */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-500 uppercase">Test stability</label>
                  <select
                    value={advanced.test_stability}
                    onChange={e => setAdvanced({ ...advanced, test_stability: e.target.value as any })}
                    className="w-full rounded-xl border p-2 text-xs"
                  >
                    <option value="frozen">Frozen (default)</option>
                    <option value="per_round">Per round</option>
                  </select>
                  <p className="text-xs text-slate-500">{STABILITY_INFO[advanced.test_stability]}</p>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-500 uppercase">Generation policy</label>
                  <select
                    value={advanced.generation_policy}
                    onChange={e => setAdvanced({ ...advanced, generation_policy: e.target.value as any })}
                    className="w-full rounded-xl border p-2 text-xs"
                  >
                    <option value="grow">Grow (default)</option>
                    <option value="replay_only">Replay only</option>
                  </select>
                  <p className="text-xs text-slate-500">{POLICY_INFO[advanced.generation_policy]}</p>
                </div>
              </div>

              {/* Budget caps */}
              <div className="space-y-2">
                <label className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase">
                  <Gauge className="h-3.5 w-3.5" /> Budget caps (leave blank for defaults)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number" min={0} placeholder="max tokens"
                    value={advanced.max_tokens ?? ""}
                    onChange={e => setAdvanced({ ...advanced, max_tokens: e.target.value ? Number(e.target.value) : undefined })}
                    className="w-full rounded-xl border p-2 text-xs"
                  />
                  <input
                    type="number" min={0} step="0.01" placeholder="max cost USD"
                    value={advanced.max_cost_usd ?? ""}
                    onChange={e => setAdvanced({ ...advanced, max_cost_usd: e.target.value ? Number(e.target.value) : undefined })}
                    className="w-full rounded-xl border p-2 text-xs"
                  />
                  <input
                    type="number" min={0} placeholder="max seconds (total)"
                    value={advanced.max_seconds ?? ""}
                    onChange={e => setAdvanced({ ...advanced, max_seconds: e.target.value ? Number(e.target.value) : undefined })}
                    className="w-full rounded-xl border p-2 text-xs"
                  />
                  <input
                    type="number" min={0} placeholder="max seconds per round"
                    value={advanced.max_round_seconds ?? ""}
                    onChange={e => setAdvanced({ ...advanced, max_round_seconds: e.target.value ? Number(e.target.value) : undefined })}
                    className="w-full rounded-xl border p-2 text-xs"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* File upload */}
        <div className="space-y-1.5 border-t pt-4">
          <label className="text-xs font-bold text-slate-500 uppercase">Source Files</label>
          <label className="flex min-h-[80px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-slate-50 hover:bg-slate-100 transition">
            <Upload className="h-6 w-6 text-slate-400 mb-1" />
            <span className="text-xs text-slate-500">Select .py, .ipynb, or .zip</span>
            <input ref={fileRef} type="file" multiple className="hidden" onChange={handleFileChange} />
          </label>
          {fileNames.length > 0 && (
            <div className="rounded-lg border bg-slate-50 p-2 text-xs text-slate-600 font-mono space-y-0.5">
              {fileNames.map((n, i) => <div key={i}>{n}</div>)}
            </div>
          )}
        </div>

        {/* Execution mode toggle */}
        <div className="border-t pt-4 space-y-3">
          <label className="text-xs font-bold text-slate-500 uppercase">Execution Mode</label>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setAutoMode(false)}
              className={`flex items-center gap-2 rounded-xl border p-3 text-left transition ${!autoMode ? "border-slate-900 bg-slate-50 ring-1 ring-slate-900" : "border-slate-200 hover:bg-slate-50"}`}
            >
              <MousePointerClick className={`h-5 w-5 ${!autoMode ? "text-slate-900" : "text-slate-400"}`} />
              <div>
                <div className="text-sm font-medium">Manual</div>
                <div className="text-xs text-slate-500">Click through each step</div>
              </div>
            </button>
            <button
              onClick={() => setAutoMode(true)}
              className={`flex items-center gap-2 rounded-xl border p-3 text-left transition ${autoMode ? "border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600" : "border-slate-200 hover:bg-slate-50"}`}
            >
              <Play className={`h-5 w-5 ${autoMode ? "text-indigo-600" : "text-slate-400"}`} />
              <div>
                <div className="text-sm font-medium">Automatic</div>
                <div className="text-xs text-slate-500">Run all steps, observe</div>
              </div>
            </button>
          </div>
        </div>

        <button onClick={handleStart} disabled={state.loading || !config.model_name || fileNames.length === 0}
          className="w-full rounded-xl bg-slate-900 py-3 font-semibold text-white shadow-lg transition-all active:scale-[0.98] disabled:opacity-50">
          {state.loading ? "Initializing..." : autoMode ? "Run Full Pipeline" : "Start Pipeline (Manual)"}
        </button>
      </div>

      {/* Right: explanations */}
      <div className="space-y-4">
        {/* Strategy explanation */}
        {selectedStrategy && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="font-semibold flex items-center gap-2"><Layers className="h-4 w-4" /> {selectedStrategy.title}</h3>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">{selectedStrategy.desc}</p>
          </div>
        )}

        {/* Oracle explanation */}
        {selectedOracle && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="font-semibold flex items-center gap-2"><FlaskConical className="h-4 w-4" /> {selectedOracle.title}</h3>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">{selectedOracle.desc}</p>
          </div>
        )}

        {/* Pipeline overview */}
        <div className="rounded-2xl border border-indigo-100 bg-indigo-50 p-5">
          <h3 className="font-semibold text-indigo-900 flex items-center gap-2"><Settings2 className="h-4 w-4" /> Pipeline</h3>
          <div className="mt-3 space-y-2 text-xs text-indigo-700">
            <p><span className="font-bold">1. Analyse:</span> Bandit (security), Radon (complexity), Ruff (linting)</p>
            <p><span className="font-bold">2. Repair:</span> LLM generates patches with compile validation and retry</p>
            <p><span className="font-bold">3. Re-analyse:</span> Measure improvement delta after repair</p>
            <p><span className="font-bold">4. Verify:</span> Generate tests, execute in sandbox, score with reward function</p>
            <p><span className="font-bold">5. Judge:</span> Accept or abandon each round's variant per the chosen judge</p>
            <p><span className="font-bold">6. Results:</span> Lineage, abandoned variants, halt reason, budget consumed</p>
          </div>
        </div>
      </div>
    </div>
  );
}
