import { useCallback, useState } from "react";
import type { AnalysisRound, AnalysisSummary, Finding, RepairResult, VerificationResult, VersionInfo } from "../types";

export interface SessionState {
  sessionId: string | null;
  step: number;
  files: string[];
  selectedFiles: string[];
  summary: AnalysisSummary | null;
  findings: Finding[];
  analysisRounds: AnalysisRound[];
  repairResult: RepairResult | null;
  repairRound: number;
  providers: string[];
  verificationStrategies: string[];
  testGenResult: VerificationResult | null;
  versions: VersionInfo[];
  loading: boolean;
  error: string | null;
}

const INIT: SessionState = {
  sessionId: null,
  step: 1,
  files: [],
  selectedFiles: [],
  providers: [],
  verificationStrategies: [],
  summary: null,
  findings: [],
  analysisRounds: [],
  repairResult: null,
  repairRound: 0,
  testGenResult: null,
  versions: [],
  loading: false,
  error: null,
};

export function useSession() {
  const [state, setState] = useState<SessionState>(INIT);
  const patch = useCallback((p: Partial<SessionState>) => setState(s => ({ ...s, ...p })), []);
  const setStep = useCallback((step: number) => patch({ step, error: null }), [patch]);
  const reset = useCallback(() => setState(INIT), []);
  return { state, patch, setStep, reset };
}
