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

// ─── Background jobs ───
// Long-running pipeline steps (verification today, others later) are
// dispatched as background jobs. The submit endpoint returns immediately
// with {job_id, session_id, status}; the frontend polls /api/jobs/{id}
// until the status reaches "done" or "error".

export type JobStatus = "pending" | "running" | "done" | "error";

export interface JobHandle {
  job_id: string;
  session_id: string;
  status: JobStatus;
}

export interface JobView<T = unknown> {
  job_id: string;
  session_id: string;
  kind: string;
  status: JobStatus;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  result: T | null;
  error: string | null;
}

export interface PollOptions {
  intervalMs?: number;  // default 500
  timeoutMs?: number;   // default 10 minutes
  signal?: AbortSignal;
}

export async function getJob<T = unknown>(jobId: string): Promise<JobView<T>> {
  return req<JobView<T>>(`/api/jobs/${jobId}`);
}

export async function pollJobUntilDone<T = unknown>(
  jobId: string,
  opts: PollOptions = {},
): Promise<JobView<T>> {
  const interval = opts.intervalMs ?? 500;
  const timeout = opts.timeoutMs ?? 10 * 60 * 1000;
  const deadline = Date.now() + timeout;

  while (true) {
    if (opts.signal?.aborted) {
      throw new Error("Job polling aborted");
    }
    const view = await getJob<T>(jobId);
    if (view.status === "done") return view;
    if (view.status === "error") {
      throw new Error(view.error || "Job failed without an error message");
    }
    if (Date.now() > deadline) {
      throw new Error(`Job ${jobId} did not finish within ${timeout}ms`);
    }
    await new Promise(r => setTimeout(r, interval));
  }
}

export async function submitTestGen(
  sid: string,
  model: string,
  oracle: string,
  rounds: number,
): Promise<JobHandle> {
  return post<JobHandle>("/api/verification/run", {
    session_id: sid,
    model,
    oracle,
    rounds,
  });
}

// Backwards-compatible wrapper: submits a job and waits for the result.
// Callers that want explicit progress can use submitTestGen + pollJobUntilDone.
export async function runTestGen(
  sid: string,
  model: string,
  oracle: string,
  rounds: number,
): Promise<VerificationResult> {
  const handle = await submitTestGen(sid, model, oracle, rounds);
  const view = await pollJobUntilDone<VerificationResult>(handle.job_id);
  if (view.result === null) {
    throw new Error("Verification job completed with no result");
  }
  return view.result;
}

// ─── Step 4: Results / Export ───
export interface DownloadedFile { name: string; content: string; }

export async function downloadTestFiles(sid: string): Promise<DownloadedFile[]> {
  return (await req<{ files: DownloadedFile[] }>(`/api/session/${sid}/download/tests`)).files;
}