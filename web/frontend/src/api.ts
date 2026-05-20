import type {
  AnalysisRound, AnalysisSummary, Finding, FunctionEntry,
  RepairResult, VerificationResult, VersionInfo
} from "./types";

// ─── HTTP helpers ───
async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(url: string, body: unknown): Promise<T> {
  return req<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ─── Session config ───
export interface SessionConfig {
  stage: string;
  strategy: string;
  model_name: string;
  oracle: string;
  rounds: number;
}

// ─── Step 0: Upload / Ingest ───
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
    body: form,
  });
}

export async function getSessionFiles(sid: string) {
  return (await req<{ files: string[] }>(`/api/session/${sid}/files`)).files;
}

// ─── Providers / Strategies / Models ───
export async function getProviders() {
  return req<{ configured: string[] }>("/api/llm/providers");
}

export async function getVerificationStrategies() {
  return req<{ configured: string[] }>("/api/verification/strategies");
}

export async function getModels() {
  return req<{ models: { id: string; label: string; provider: string; available: boolean }[] }>("/api/verification/models");
}

// ─── Step 1: Analysis ───
export async function getAnalysisTools() {
  return req<{ tools: string[] }>("/api/analysis/tools");
}

export async function runAnalysis(sid: string, files: string[], tools: string[] = []) {
  return post<{ summary: AnalysisSummary; findings: Finding[] }>("/api/analyse", {
    session_id: sid,
    selected_files: files,
    selected_tools: tools,
  });
}

export async function getAnalysisHistory(sid: string) {
  const d = await req<{ rounds: AnalysisRound[] }>(`/api/session/${sid}/analysis-history`);
  return d.rounds;
}

// ─── Step 2: Repair ───
export async function runRepair(sid: string, provider?: string) {
  return post<RepairResult>(`/api/repair/${sid}`, { provider });
}

export async function getFileDiff(sid: string, fp: string) {
  return (await req<{ diff: string }>(`/api/session/${sid}/diff/${fp}`)).diff;
}

export async function getVersions(sid: string) {
  return (await req<{ versions: VersionInfo[] }>(`/api/session/${sid}/versions`)).versions;
}

export async function restoreVersion(sid: string, round: number) {
  return req(`/api/session/${sid}/restore/${round}`, { method: "POST" });
}

// ─── Step 3: Verification ───
export async function getFunctions(sid: string): Promise<FunctionEntry[]> {
  return (await req<{ functions: FunctionEntry[] }>(`/api/verification/functions/${sid}`)).functions;
}

export async function runTestGen(sid: string, model: string, oracle: string, rounds: number): Promise<VerificationResult> {
  return post<VerificationResult>("/api/verification/run", {
    session_id: sid,
    model,
    oracle,
    rounds,
  });
}

// ─── Step 4: Results / Export ───
export interface DownloadedFile { name: string; content: string; }

export async function downloadTestFiles(sid: string): Promise<DownloadedFile[]> {
  return (await req<{ files: DownloadedFile[] }>(`/api/session/${sid}/download/tests`)).files;
}