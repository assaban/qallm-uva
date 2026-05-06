import type {
  AnalysisRound, AnalysisSummary, Finding, FunctionEntry,
  RepairResult, VerificationResult, VersionInfo
} from "./types";

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface SessionConfig {
  stage: string;
  strategy: string;
  model_name: string;
  oracle: string;
  rounds: number;
}

export async function uploadFiles(files: FileList, config: SessionConfig) {
  const form = new FormData();
  Array.from(files).forEach(f => form.append("archives", f));

  form.append("stage", config.stage);
  form.append("strategy", config.strategy);
  form.append("model", config.model_name);
  form.append("oracle", config.oracle);
  form.append("rounds", config.rounds.toString());

  return req<{ session_id: string; files: string[] }>("/api/session/upload", {
    method: "POST",
    body: form
  });
}

// Added to resolve build errors[cite: 23, 25]
export async function getVersions(sid: string) {
  return (await req<{ versions: VersionInfo[] }>(`/api/session/${sid}/versions`)).versions;
}

export async function getFileDiff(sid: string, fp: string) {
  return (await req<{ diff: string }>(`/api/session/${sid}/diff/${fp}`)).diff;
}

export async function restoreVersion(sid: string, round: number) {
  return req(`/api/session/${sid}/restore/${round}`, { method: "POST" });
}

export interface DownloadedFile { name: string; content: string; }
export async function downloadTestFiles(sid: string): Promise<DownloadedFile[]> {
  return (await req<{ files: DownloadedFile[] }>(`/api/session/${sid}/download/tests`)).files;
}

export async function getProviders() { return req<{ configured: string[] }>("/api/llm/providers"); }

export async function getVerificationStrategies() { return req<{ configured: string[] }>("/api/verification/strategies"); }

/** Retrieves the list of available analysis tools from the server[cite: 30]. */
export async function getAnalysisTools() {
  return req<{ tools: string[] }>("/api/analysis/tools");
}

/**
 * Triggers the analysis process.
 * Updated to accept the third argument: selectedTools.
 */
export async function runAnalysis(sid: string, files: string[], tools: string[]) {
  return post<{ summary: AnalysisSummary; findings: Finding[] }>("/api/analyse", {
    session_id: sid,
    selected_files: files,
    selected_tools: tools // Now correctly passed to the backend
  });
}

/**
 * FIX: Added this function to resolve "is not a function" errors[cite: 27, 30].
 */
export async function getAnalysisHistory(sid: string) {
  const d = await req<{ rounds: AnalysisRound[] }>(`/api/session/${sid}/analysis-history`);
  return d.rounds;
}

export async function getSessionFiles(sid: string) {
  return (await req<{ files: string[] }>(`/api/session/${sid}/files`)).files;
}