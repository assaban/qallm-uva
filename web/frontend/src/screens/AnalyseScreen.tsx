import { useState, useEffect } from "react";
import { AlertTriangle, FileCode2, Search, Shield, CheckSquare, Square, FolderTree } from "lucide-react";
import { StatCard } from "../components/Shared";
import type { SessionState } from "../hooks/useSession";
import type { Finding } from "../types";
import * as api from "../api";

const SEV_CLS: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800",
  HIGH: "bg-orange-100 text-orange-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  LOW: "bg-blue-100 text-blue-800"
};

export default function AnalyseScreen({ state, patch }: { state: SessionState; patch: (p: Partial<SessionState>) => void; autoMode?: boolean }) {
  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set(state.files));
  const [filter, setFilter] = useState("");
  const [sevF, setSevF] = useState("");
  const [toolF, setToolF] = useState("");

  // Fetch available analysis tools from the server on component mount[cite: 35]
  useEffect(() => {
    api.getAnalysisTools()
      .then(res => {
        if (res.tools) {
          setAvailableTools(res.tools);
          setSelectedTools(res.tools); // Default to all tools enabled[cite: 35]
        }
      })
      .catch(err => patch({ error: "Failed to load tools: " + err.message }));
  }, [patch]);

  const has = state.findings.length > 0 || state.summary !== null;

  // Toggle selection for analysis tools[cite: 35]
  const toggleTool = (tool: string) => {
    setSelectedTools(prev =>
      prev.includes(tool) ? prev.filter(t => t !== tool) : [...prev, tool]
    );
  };

  // Toggle selection for specific files in the directory[cite: 35]
  const toggleFile = (file: string) => {
    const next = new Set(selectedFiles);
    if (next.has(file)) {
      next.delete(file);
    } else {
      next.add(file);
    }
    setSelectedFiles(next);
  };

  async function run() {
    // Ensure both files and tools are selected before proceeding[cite: 35]
    if (!state.sessionId || selectedTools.length === 0 || selectedFiles.size === 0) return;

    patch({ loading: true, error: null });
    try {
      // Execute multi-tool analysis via the API with three required arguments[cite: 30, 35]
      const r = await api.runAnalysis(state.sessionId, Array.from(selectedFiles), selectedTools);

      // Retrieve the updated analysis history[cite: 30, 35]
      const rounds = await api.getAnalysisHistory(state.sessionId).catch(() => []);

      patch({
        summary: r.summary,
        findings: r.findings,
        analysisRounds: rounds,
        loading: false
      });
    } catch (e: unknown) {
      patch({ loading: false, error: (e as Error).message });
    }
  }

  // Filter findings based on user input for severity, tool, or search text[cite: 35]
  const shown = state.findings.filter((f: Finding) => {
    if (sevF && f.severity !== sevF) return false;
    if (toolF && f.tool.toLowerCase() !== toolF.toLowerCase()) return false;
    if (filter && !`${f.message} ${f.file} ${f.tool}`.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

  const sev = state.summary?.by_severity || {};

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Tool Selection Section[cite: 35] */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 flex items-center gap-2 font-semibold">
            <Shield className="h-4 w-4" /> Analysis Tools
          </h3>
          <div className="space-y-2">
            {availableTools.map(tool => (
              <label key={tool} className="flex cursor-pointer items-center justify-between rounded-lg border p-2 hover:bg-slate-50">
                <span className="text-sm">{tool}</span>
                <input
                  type="checkbox"
                  checked={selectedTools.includes(tool)}
                  onChange={() => toggleTool(tool)}
                  className="rounded border-slate-300 text-slate-900 focus:ring-slate-900"
                />
              </label>
            ))}
          </div>
          <p className="mt-3 text-[10px] text-slate-400">At least one tool must be selected[cite: 35].</p>
        </div>

        {/* File Selection Section */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 font-semibold">
              <FolderTree className="h-4 w-4" /> Target Files
            </h3>
            <button
              onClick={() => {
                if (selectedFiles.size === state.files.length) {
                  setSelectedFiles(new Set());
                } else {
                  setSelectedFiles(new Set(state.files));
                }
              }}
              className="text-xs text-indigo-600 hover:underline"
            >
              {selectedFiles.size === state.files.length ? "Deselect all" : "Select all"}
            </button>
          </div>
          <div className="max-h-[160px] overflow-auto space-y-1 rounded-xl border border-slate-100 p-2">
            {state.files.map(file => (
              <label key={file} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-slate-50">
                {selectedFiles.has(file) ? (
                  <CheckSquare className="h-3.5 w-3.5 text-slate-900" />
                ) : (
                  <Square className="h-3.5 w-3.5 text-slate-300" />
                )}
                <span className="font-mono text-slate-700">{file}</span>
                <input
                  type="checkbox"
                  className="hidden"
                  checked={selectedFiles.has(file)}
                  onChange={() => toggleFile(file)}
                />
              </label>
            ))}
          </div>

          {/* Analysis Trigger: Disabled if selections are missing[cite: 35] */}
          <button
            onClick={run}
            disabled={state.loading || selectedTools.length === 0 || selectedFiles.size === 0}
            className="mt-4 w-full flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-slate-800 disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
            {state.loading ? "Analysing..." : "Run Multi-Tool Analysis"}
          </button>
        </div>
      </div>

      {state.error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {state.error}
        </div>
      )}

      {has && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total Findings" value={state.summary?.total || 0} icon={AlertTriangle} />
            <StatCard label="Critical + High" value={(sev.CRITICAL || 0) + (sev.HIGH || 0)} icon={Shield} />
            <StatCard label="Medium" value={sev.MEDIUM || 0} icon={FileCode2} />
            <StatCard label="Low" value={sev.LOW || 0} icon={FileCode2} />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex flex-wrap gap-3">
              <input
                type="text"
                placeholder="Search findings..."
                value={filter}
                onChange={e => setFilter(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-slate-400 sm:w-64"
              />
              <select
                value={sevF}
                onChange={e => setSevF(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-slate-400"
              >
                <option value="">All Severities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
              </select>
              <select
                value={toolF}
                onChange={e => setToolF(e.target.value)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm outline-none focus:border-slate-400"
              >
                <option value="">All Tools</option>
                {availableTools.map(t => (
                  <option key={t} value={t.toUpperCase()}>{t}</option>
                ))}
              </select>
              <span className="self-center text-xs text-slate-500">
                Showing {shown.length} of {state.findings.length}
              </span>
            </div>

            <div className="max-h-[400px] overflow-auto rounded-xl border border-slate-200 shadow-inner">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 border-b border-slate-200 bg-slate-50">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold text-slate-700">Severity</th>
                    <th className="px-3 py-2.5 font-semibold text-slate-700">Tool</th>
                    <th className="px-3 py-2.5 font-semibold text-slate-700">Location</th>
                    <th className="px-3 py-2.5 font-semibold text-slate-700">Message</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {shown.map((f, i) => (
                    <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-3 py-2.5">
                        <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase ${SEV_CLS[f.severity]}`}>
                          {f.severity}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-medium text-slate-600">{f.tool}</td>
                      <td className="px-3 py-2.5">
                        <div className="font-mono text-[10px] text-slate-500">
                          {f.file || "\u2014"}:{f.line || "\u2014"}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-slate-600 leading-relaxed">{f.message}</td>
                    </tr>
                  ))}
                  {shown.length === 0 && (
                    <tr>
                      <td colSpan={4} className="p-8 text-center text-slate-400 italic">
                        No findings match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}