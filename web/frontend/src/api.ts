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
  // Optional custom tags for grouping/retrieving the session later.
  tags?: string;
  // Optional advanced settings (NEW-08). Undefined values fall back to
  // server defaults; the upload endpoint only forwards what's present.
  repair_model?: string;
  testgen_model?: string;
  judge_strategy?: "strict" | "lexicographic" | "model";
  test_stability?: "frozen" | "per_round";
  generation_policy?: "replay_only" | "grow";
  max_tokens?: number;
  max_seconds?: number;
  max_round_seconds?: number;
  max_cost_usd?: number;
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
  // Optional advanced fields. Only append when defined so the server uses
  // its own defaults for the rest.
  if (config.repair_model) form.append("repair_model", config.repair_model);
  if (config.testgen_model) form.append("testgen_model", config.testgen_model);
  if (config.judge_strategy) form.append("judge_strategy", config.judge_strategy);
  if (config.test_stability) form.append("test_stability", config.test_stability);
  if (config.generation_policy) form.append("generation_policy", config.generation_policy);
  if (config.max_tokens !== undefined) form.append("max_tokens", String(config.max_tokens));
  if (config.max_seconds !== undefined) form.append("max_seconds", String(config.max_seconds));
  if (config.max_round_seconds !== undefined) form.append("max_round_seconds", String(config.max_round_seconds));
  if (config.max_cost_usd !== undefined) form.append("max_cost_usd", String(config.max_cost_usd));
  if (config.tags) form.append("tags", config.tags);

  return req<{ session_id: string; files: string[]; config?: Record<string, unknown> }>("/api/session/upload", {
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

export interface JobProgress {
  phase: "initialising" | "baseline" | "rounds" | "summary" | "done";
  current_round: number;
  total_rounds: number;
  current_stage: "analyse" | "repair" | "verify" | "judge" | null;
  current_unit_id: string | null;
  // Function-level granularity inside the verify stage. On slow local
  // LLMs an 8-function unit can spend 10+ minutes in verify; this field
  // changes per function, giving the UI something to render and the
  // inactivity timer something to reset on.
  current_function: string | null;
  function_index: number;
  function_total: number;
  units_total: number;
  units_completed: number;
  rounds_accepted: number;
  rounds_abandoned: number;
  elapsed_seconds: number;
  tokens_used: number;
  cost_usd: number;
  // Seconds since the last LLM-call heartbeat. Small while a call is in
  // flight or just completed; grows without bound only if truly stuck.
  seconds_since_activity?: number;
  halt_reason: string | null;
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
  // Present only while the orchestrator is running for this session.
  progress?: JobProgress;
}

export interface PollOptions {
  intervalMs?: number;       // default 500
  // Hard ceiling on total wait time, regardless of progress. Default 60
  // minutes. Set high enough to accommodate slow local LLMs on
  // multi-function, multi-round runs.
  timeoutMs?: number;
  // Soft ceiling: if no progress (snapshot fields don't change) for this
  // long, treat the job as stuck and give up. Default 5 minutes. This
  // catches "the worker is genuinely hung" without giving up on jobs
  // that are slow but still working.
  inactivityMs?: number;
  signal?: AbortSignal;
  // Called with each intermediate view. Useful for surfacing live
  // progress while the job is running.
  onProgress?: (view: JobView) => void;
}

export async function getJob<T = unknown>(jobId: string): Promise<JobView<T>> {
  return req<JobView<T>>(`/api/jobs/${jobId}`);
}

/** Build a stable signature of the progress fields we expect to change.
 *
 * Includes ``current_function`` and ``function_index`` so that within the
 * verify stage, advancing function-by-function resets the inactivity
 * timer. Without these, a unit with many functions on a slow LLM would
 * appear stuck for the duration even though work was happening.
 */
function progressSignature(view: JobView): string {
  const p = view.progress;
  if (!p) return view.status;
  return [
    p.phase, p.current_round, p.current_stage, p.current_unit_id,
    p.current_function, p.function_index,
    p.rounds_accepted, p.rounds_abandoned, p.tokens_used,
  ].join("|");
}

export async function pollJobUntilDone<T = unknown>(
  jobId: string,
  opts: PollOptions = {},
): Promise<JobView<T>> {
  const interval = opts.intervalMs ?? 500;
  const timeout = opts.timeoutMs ?? 60 * 60 * 1000;  // 60 minutes hard cap
  const inactivity = opts.inactivityMs ?? 5 * 60 * 1000;  // 5 minutes
  const startedAt = Date.now();
  let lastProgressAt = Date.now();
  let lastSignature = "";

  while (true) {
    if (opts.signal?.aborted) {
      throw new Error("Job polling aborted");
    }
    const view = await getJob<T>(jobId);
    opts.onProgress?.(view);  // surface every snapshot

    if (view.status === "done") return view;
    if (view.status === "error") {
      throw new Error(view.error || "Job failed without an error message");
    }

    // Reset the inactivity timer whenever progress moves. If the
    // orchestrator is making progress (a new unit, a new round, a new
    // accepted variant, more tokens spent), we are willing to wait.
    const sig = progressSignature(view);
    if (sig !== lastSignature) {
      lastSignature = sig;
      lastProgressAt = Date.now();
    }

    const now = Date.now();
    if (now - startedAt > timeout) {
      throw new Error(
        `Job ${jobId} hit the hard timeout of ${Math.round(timeout / 60000)} minutes. ` +
        `Last observed phase: ${view.progress?.phase ?? "unknown"}.`,
      );
    }
    if (now - lastProgressAt > inactivity) {
      // The progress signature has been flat for the inactivity window.
      // Before declaring a stall, check the heartbeat: if an LLM call is
      // in flight or recently completed (seconds_since_activity small), the
      // run is slow, not hung (a single local-model generation can run for
      // minutes), so keep waiting and reset the window. Only a flat
      // signature AND a stale heartbeat is a genuine stall.
      const sinceActivity = view.progress?.seconds_since_activity;
      const heartbeatStale = sinceActivity === undefined
        ? true  // backend did not report a heartbeat: fall back to old behaviour
        : sinceActivity * 1000 > inactivity;
      if (!heartbeatStale) {
        lastProgressAt = now;  // model is working; grant a fresh window
      } else {
        throw new Error(
          `Job ${jobId} made no progress for ${Math.round(inactivity / 60000)} minutes. ` +
          `Last observed: ${view.progress?.current_stage ?? view.status} on ${view.progress?.current_unit_id ?? "n/a"}.`,
        );
      }
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
// Callers that want explicit progress can use submitTestGen + pollJobUntilDone,
// or pass an ``onProgress`` callback here.
export async function runTestGen(
  sid: string,
  model: string,
  oracle: string,
  rounds: number,
  onProgress?: (view: JobView) => void,
): Promise<VerificationResult> {
  const handle = await submitTestGen(sid, model, oracle, rounds);
  const view = await pollJobUntilDone<VerificationResult>(handle.job_id, { onProgress });
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
// ─── Observability: per-round improvement audit + LLM transcript ───
export interface IndicatorDelta {
  name: string;
  dimension: string;
  comparator: string;
  threshold: number;
  parent_measured: number | null;
  variant_measured: number | null;
  parent_status: string | null;
  variant_status: string | null;
  measured_delta: number | null;
  status_transition: string;
  direction: "improved" | "regressed" | "unchanged" | "appeared" | "disappeared";
}

export interface DimensionDelta {
  dimension: string;
  parent_status: string | null;
  variant_status: string | null;
  net: string;
  indicators: IndicatorDelta[];
}

export interface ImprovementReport {
  round_number: number;
  unit_id: string;
  accepted: boolean;
  parent_round: number | null;
  overall_parent_status: string | null;
  overall_variant_status: string | null;
  judge_outcome: string | null;
  judge_rationale: string | null;
  counts: Record<string, number>;
  headline: string;
  dimensions: DimensionDelta[];
}

export interface LLMCall {
  seq: number;
  context: Record<string, unknown>;
  system_prompt: string;
  user_prompt: string;
  response_content: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  model: string;
  provider: string;
  error: string | null;
  timestamp: number;
}

export interface BugTest {
  name: string;
  status: "passed" | "failed" | "error" | "skipped";
  message: string | null;
  body: string;
}

export interface FunctionBugDetail {
  function: string;
  source_code: string;
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  total: number;
  discarded?: string[];
  coverage_percent: number | null;
  execution_error: string | null;
  test_code: string;
  bug_tests: BugTest[];
  all_tests: BugTest[];
}

export interface ImprovementUnit {
  unit_id: string;
  bucket: "lineage" | "abandoned";
  accepted: boolean;
  is_baseline: boolean;
  improvement: ImprovementReport | null;
  profile: Record<string, unknown> | null;
  judge: Record<string, unknown> | null;
  llm_calls: LLMCall[];
  bug_detail: FunctionBugDetail[];
}

export interface ImprovementRound {
  round: number;
  units: ImprovementUnit[];
}

export interface ImprovementResponse {
  available: boolean;
  rounds: ImprovementRound[];
  reason?: string;
}

export async function getImprovement(sid: string): Promise<ImprovementResponse> {
  return req<ImprovementResponse>(`/api/session/${sid}/improvement`);
}

// ─── Static-vs-execution gap ───
export type FindingStatus = "confirmed" | "unconfirmed" | "untested";

export interface GapFinding {
  tool: string;
  severity: string;
  line: number;
  message: string;
  rule_id: string;
  function: string | null;
  status: FindingStatus;
}

export interface GapRoundSummary {
  confirmed: number;
  unconfirmed: number;
  untested: number;
  execution_only: number;
  confirmation_rate: number | null;
}

export interface GapRound {
  round: number;
  findings: GapFinding[];
  execution_only_functions: string[];
  summary: GapRoundSummary;
}

export interface GapResponse {
  available: boolean;
  rounds: GapRound[];
  reason?: string;
}

export async function getGap(sid: string): Promise<GapResponse> {
  return req<GapResponse>(`/api/session/${sid}/gap`);
}

// ─── Confirm/refute individual findings ───
export type FindingVerdict =
  | "confirmed" | "refuted" | "inconclusive" | "not_execution_testable";

export interface FindingVerdictRow {
  finding_index: number;
  file?: string;
  tool: string;
  type: string;
  severity: string;
  line: number;
  message: string;
  rule_id: string;
  function: string | null;
  verdict: FindingVerdict;
  reason: string;
  reproducing_test: string | null;
}

export interface ConfirmFindingsResponse {
  available: boolean;
  verdicts: FindingVerdictRow[];
  reason?: string;
  summary?: {
    confirmed: number;
    refuted: number;
    inconclusive: number;
    not_execution_testable: number;
    confirmation_rate: number | null;
  };
}

export async function confirmFindings(sid: string): Promise<ConfirmFindingsResponse> {
  return req<ConfirmFindingsResponse>(`/api/session/${sid}/confirm-findings`, {
    method: "POST",
  });
}

// ─── Quality model profiles (selector) ───
export interface QualityProfileInfo {
  id: string;
  name: string;
  description: string;
  framework: string;
  dimensions: { name: string; indicators: string[] }[];
  available: boolean;
}

export async function getQualityProfiles(): Promise<{ profiles: QualityProfileInfo[]; default: string }> {
  return req<{ profiles: QualityProfileInfo[]; default: string }>("/api/quality-profiles");
}

// ─── Sample data (portal demo) ───
export interface SampleFile {
  name: string;
  description: string;
  content: string;
  lines: number;
}

export async function getSampleData(): Promise<{ samples: SampleFile[] }> {
  return req<{ samples: SampleFile[] }>("/api/sample-data");
}

// ─── Experiments (HumanEvalFix validation runs) ───
export interface ExperimentRunSummary {
  id: string;
  models: string[];
  strategies: string[];
  rounds: number | null;
  sample_size: number | null;
  created: string | null;
  n_results: number;
  n_combinations: number;
  has_report: boolean;
}

export interface ExperimentAggregate {
  strategy: string;
  model: string;
  n_problems: number;
  n_bug_detected: number;
  n_repair_successful: number;
  n_errored: number;
  mean_rounds: number;
  mean_cost_usd: number;
  mean_elapsed_seconds: number;
  bug_detection_rate: number;
  repair_success_rate: number;
}

export interface ExperimentProblemResult {
  task_id: string;
  strategy: string;
  model: string;
  bug_detected: boolean;
  repair_successful: boolean;
  rounds_run: number;
  final_coverage: number;
  cost_usd: number;
  elapsed_seconds: number;
  error: string | null;
}

export async function listExperiments(): Promise<{ runs_dir: string; runs: ExperimentRunSummary[] }> {
  return req<{ runs_dir: string; runs: ExperimentRunSummary[] }>("/api/experiments");
}

export async function getExperiment(id: string): Promise<{
  id: string;
  manifest: Record<string, unknown>;
  aggregates: ExperimentAggregate[];
  has_report: boolean;
}> {
  return req(`/api/experiments/${encodeURIComponent(id)}`);
}

export async function getExperimentResults(id: string): Promise<{ id: string; results: ExperimentProblemResult[] }> {
  return req(`/api/experiments/${encodeURIComponent(id)}/results`);
}

export async function getExperimentReport(id: string): Promise<{ id: string; markdown: string }> {
  return req(`/api/experiments/${encodeURIComponent(id)}/report`);
}

// ─── Session library (past processed sessions) ───
export interface SessionCard {
  id: string;
  source: string | null;
  tags: string[];
  strategy: string | null;
  model: string | null;
  profile_id: string | null;
  lifecycle_stage: string | null;
  oracle: string | null;
  rounds_per_function: number | null;
  units_analyzed: number | null;
  functions_verified: number | null;
  rounds_accepted_total: number | null;
  rounds_abandoned_total: number | null;
  total_cost_usd: number | null;
  halt_reason: string | null;
  has_report: boolean;
}

export async function listLibrarySessions(tag?: string): Promise<{ sessions_dir: string; sessions: SessionCard[]; all_tags: string[] }> {
  const q = tag ? `?tag=${encodeURIComponent(tag)}` : "";
  return req<{ sessions_dir: string; sessions: SessionCard[]; all_tags: string[] }>(`/api/library${q}`);
}

export async function getLibrarySession(id: string): Promise<{
  id: string;
  summary: Record<string, unknown>;
  has_report: boolean;
}> {
  return req(`/api/library/${encodeURIComponent(id)}`);
}

export async function getLibrarySessionReport(id: string): Promise<{ id: string; markdown: string }> {
  return req(`/api/library/${encodeURIComponent(id)}/report`);
}

// ─── Experiment catalog, launch, live progress ───
export interface ExperimentSpec {
  id: string;
  name: string;
  summary: string;
  dataset_id: string;
  dataset_url: string;
  citation: string;
  n_problems: number;
  measures: string[];
  notes: string;
}

export interface ExperimentProgress {
  run_id: string;
  tracked: boolean;
  status?: "running" | "done" | "failed";
  total?: number;
  completed?: number;
  bug_detected?: number;
  repair_successful?: number;
  errored?: number;
  log?: Array<{
    task_id: string; strategy: string; model: string;
    bug_detected: boolean; repair_successful: boolean;
    error: string | null; at: number;
  }>;
  error?: string | null;
}

export async function listExperimentCatalog(): Promise<{ experiments: ExperimentSpec[] }> {
  return req<{ experiments: ExperimentSpec[] }>("/api/experiment-catalog");
}

export async function launchExperiment(id: string, params: {
  models: string[]; strategies: string[]; sample_size?: number;
  seed?: number; rounds?: number; oracle?: string; judge_strategy?: string;
}): Promise<{ run_id: string; job_id: string; status: string }> {
  return post(`/api/experiment-catalog/${encodeURIComponent(id)}/run`, params);
}

export async function getExperimentProgress(runId: string): Promise<ExperimentProgress> {
  return req<ExperimentProgress>(`/api/experiment-runs/${encodeURIComponent(runId)}/progress`);
}

export async function listActiveExperimentRuns(): Promise<{ runs: ExperimentProgress[] }> {
  return req<{ runs: ExperimentProgress[] }>("/api/experiment-runs/active");
}

export async function datasetToPipeline(id: string, params: {
  sample_size?: number; seed?: number; model?: string; strategy?: string;
  oracle?: string; rounds?: number; tags?: string[];
}): Promise<{ session_id: string; experiment_id: string; n_files: number; directory: string }> {
  return post(`/api/experiment-catalog/${encodeURIComponent(id)}/to-pipeline`, params);
}
