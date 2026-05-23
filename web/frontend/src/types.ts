export interface Finding {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  type: string;
  tool: string;
  rule_id?: string;
  file?: string;
  line?: number;
  message: string;
  code_snippet?: string;
}

export interface AnalysisSummary {
  total: number;
  by_severity: Record<string, number>;
}

export interface Patch {
  finding_id: string;
  description: string;
  unified_diff: string;
  applied: boolean;
  error?: string;
  meta?: Record<string, unknown>;
}

export interface RepairResult {
  patches: Patch[];
  token_usage: Record<string, number>;
  repaired_count: number;
  repair_round: number;
  provider_used: string;
}

export interface FunctionEntry {
  name: string;
  file: string;
  lineno: number;
  args: { name: string; type: string | null }[];
  docstring: string | null;
}

export interface RoundExecution {
  passed: number;
  failed: number;
  errors: number;
  total: number;
  coverage_percent: number | null;
  duration_seconds: number;
}

export interface RoundReward {
  bug_reward: number;
  coverage_reward: number;
  validity_penalty: number;
  redundancy_penalty: number;
  total: number;
  bugs_found: number;
  coverage_gain: number;
}

export interface RoundResult {
  round_number: number;
  execution: RoundExecution;
  reward: RoundReward;
  cumulative_coverage: number | null;
  cumulative_bugs: number;
}

export interface VerificationFunction {
  function_name: string;
  oracle: string;
  model: string;
  rounds: RoundResult[];
}

// v3 surface: per-unit lineage and abandoned tracking.

export interface JudgeVerdictView {
  outcome: "improvement" | "regression" | "no_change";
  strategy: string;
  explanation: string;
  confidence?: number | null;
}

export interface LineageEntryView {
  round_number: number;
  judge_verdict: JudgeVerdictView | null;
}

export interface AbandonedEntryView {
  round_number: number;
  judge_verdict: JudgeVerdictView;
}

export interface UnitTrackView {
  unit_id: string;
  lineage: LineageEntryView[];
  abandoned: AbandonedEntryView[];
}

export interface BudgetSummary {
  rounds_completed?: number;
  elapsed_seconds?: number;
  caps?: Record<string, number>;
}

export interface VerificationResult {
  session_id: string;
  model: string;
  repair_model?: string;
  testgen_model?: string;
  oracle: string;
  rounds_per_function: number;
  total_functions: number;
  total_bugs: number;
  functions: VerificationFunction[];
  // v3 fields (optional for back-compat; absent on legacy responses):
  tracks?: Record<string, UnitTrackView>;
  rounds_accepted_total?: number;
  rounds_abandoned_total?: number;
  judge_strategy?: string;
  halt_reason?: string | null;
  budget?: BudgetSummary;
  test_persistence?: Record<string, string>;
  token_usage?: Record<string, number>;
  report_dir?: string;
}

export interface VersionInfo {
  round: number;
  label: string;
  files: number;
}

export interface AnalysisRound {
  round: number;
  total: number;
  by_severity: Record<string, number>;
}
