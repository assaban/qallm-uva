import { useRef, useState, useEffect } from "react";
import { Upload, Settings2 } from "lucide-react";
import * as api from "../api";

export default function UploadScreen({ state, patch }: any) {
  const [config, setConfig] = useState({
    stage: "implementation",
    strategy: "rl",
    oracle: "crash",
    rounds: 5,
    model_name: ""
  });

  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Fetch LLM Providers
    api.getProviders().then(p => {
      patch({ providers: p.configured || [] });
      if (p.configured?.length > 0) {
        setConfig(prev => ({ ...prev, model_name: p.configured[0] }));
      }
    }).catch(err => console.error("Providers fetch failed", err));

    // FIX: Patch verificationStrategies key instead of providers
    api.getVerificationStrategies().then(p => {
      patch({ verificationStrategies: p.configured || [] });
      if (p.configured?.length > 0) {
        setConfig(prev => ({ ...prev, strategy: p.configured[0] }));
      }
    }).catch(err => console.error("Strategies fetch failed", err));
  }, []);

  async function handleStart() {
    const files = fileRef.current?.files;
    if (!files?.length || !config.model_name) return;

    patch({ loading: true, error: null });
    try {
      const data = await api.uploadFiles(files, config);
      patch({
        sessionId: data.session_id,
        files: data.files,
        selectedFiles: data.files,
        loading: false,
        step: 2
      });
    } catch (e: any) {
      patch({ loading: false, error: e.message });
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-2xl border bg-white p-6 shadow-sm space-y-6">
        <h2 className="text-xl font-semibold">Step 1: Process Setup</h2>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-500 uppercase">Model</label>
            <select
              value={config.model_name}
              onChange={e => setConfig({...config, model_name: e.target.value})}
              className="w-full rounded-xl border p-2 text-sm"
            >
              {/* Added fallback to prevent map error */}
              {(state.providers || []).map((p: string) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-500 uppercase">Strategy</label>
            <select
              value={config.strategy}
              onChange={e => setConfig({...config, strategy: e.target.value})}
              className="w-full rounded-xl border p-2 text-sm"
            >
              {/* Added fallback to prevent map error[cite: 31] */}
              {(state.verificationStrategies || []).map((p: string) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-1.5 border-t pt-4">
          <label className="text-xs font-bold text-slate-500 uppercase">Source Files</label>
          <label className="flex min-h-[100px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-slate-50 hover:bg-slate-100 transition">
            <Upload className="h-6 w-6 text-slate-400 mb-1" />
            <span className="text-xs text-slate-500">Select .py, .ipynb, or .zip</span>
            <input ref={fileRef} type="file" multiple className="hidden" />
          </label>
        </div>

        <button
          onClick={handleStart}
          disabled={state.loading}
          className="w-full rounded-xl bg-slate-900 py-3 font-semibold text-white shadow-lg transition-all active:scale-[0.98]"
        >
          {state.loading ? "Initializing..." : "Start Research Pipeline"}
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="font-semibold flex items-center gap-2"><Settings2 className="h-4 w-4"/> Research Methodology</h3>
        <p className="mt-2 text-sm text-slate-500 italic">This setup initializes the Orchestrator with the context required for your experiment.</p>
      </div>
    </div>
  );
}