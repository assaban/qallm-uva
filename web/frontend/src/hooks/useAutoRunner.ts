import { useRef, useCallback } from "react";
import type { SessionState } from "./useSession";
import * as api from "../api";

/**
 * Auto-runner: sequences analyse → repair → verify → results
 * with screen transitions between each step.
 */
export function useAutoRunner(
  state: SessionState,
  patch: (p: Partial<SessionState>) => void,
  setStep: (step: number) => void,
) {
  const aborted = useRef(false);

  const run = useCallback(async () => {
    if (!state.sessionId) return;
    aborted.current = false;

    const sid = state.sessionId;
    const files = state.files;

    try {
      // ─── Step 2: Analyse ───
      setStep(2);
      patch({ loading: true, error: null });
      await delay(600); // Let the UI render

      const tools = await api.getAnalysisTools();
      const analysis = await api.runAnalysis(sid, files, tools.tools);
      const rounds = await api.getAnalysisHistory(sid).catch(() => []);
      patch({ summary: analysis.summary, findings: analysis.findings, analysisRounds: rounds, loading: false });
      if (aborted.current) return;
      await delay(1500); // Pause so user sees results

      // ─── Step 3: Repair ───
      setStep(3);
      patch({ loading: true });
      await delay(600);

      const repair = await api.runRepair(sid);
      const versions = await api.getVersions(sid).catch(() => []);
      patch({ repairResult: repair, repairRound: repair.repair_round, versions, loading: false });
      if (aborted.current) return;
      await delay(1500);

      // ─── Step 4: Re-analyse ───
      setStep(4);
      patch({ loading: true });
      await delay(600);

      const reanalysis = await api.runAnalysis(sid, files, tools.tools);
      const rounds2 = await api.getAnalysisHistory(sid).catch(() => []);
      patch({ summary: reanalysis.summary, findings: reanalysis.findings, analysisRounds: rounds2, loading: false });
      if (aborted.current) return;
      await delay(1500);

      // ─── Step 5: Generate Tests ───
      setStep(5);
      patch({ loading: true });
      await delay(600);

      const verification = await api.runTestGen(sid, "", "", 0); // Uses session defaults
      patch({ testGenResult: verification, loading: false });
      if (aborted.current) return;
      await delay(1000);

      // ─── Step 6: Results ───
      setStep(6);

    } catch (e: any) {
      patch({ loading: false, error: e.message });
    }
  }, [state.sessionId, state.files, patch, setStep]);

  const abort = useCallback(() => { aborted.current = true; }, []);

  return { run, abort };
}

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
