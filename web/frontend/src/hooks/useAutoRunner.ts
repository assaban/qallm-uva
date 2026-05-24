import { useRef, useCallback } from "react";
import type { SessionState } from "./useSession";
import * as api from "../api";

/**
 * Auto-runner: sequences analyse → repair → verify → results
 * with screen transitions between each step.
 *
 * IMPORTANT: ``run`` accepts ``sessionId`` and ``files`` as explicit
 * arguments rather than reading them from the captured ``state`` closure.
 *
 * The reason is a React stale-closure trap. ``onSessionReady`` invokes
 * ``run()`` immediately after ``patch({ sessionId })``; because React
 * state updates are asynchronous, ``state.sessionId`` is still the
 * pre-upload value at the moment ``run()`` runs. Reading from the
 * closure would see ``undefined`` and the guard at the top would bail
 * silently, which is exactly what produced the "auto mode does nothing"
 * symptom in earlier builds.
 */
export function useAutoRunner(
  state: SessionState,
  patch: (p: Partial<SessionState>) => void,
  setStep: (step: number) => void,
) {
  const aborted = useRef(false);

  const run = useCallback(async (sessionId: string, files: string[]) => {
    if (!sessionId) return;
    aborted.current = false;

    const sid = sessionId;

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
      patch({ loading: true, progress: null });
      await delay(600);

      // The session config was locked in at upload. The backend now runs
      // the full v3 loop (orch.run) regardless of the runTestGen args; we
      // pass empty strings and 0 to make the back-compat shape explicit.
      // The result includes tracks, judge verdicts, halt reason, budget,
      // and the legacy `functions` list.
      //
      // Live progress is forwarded into the session state so TestGenScreen
      // can render it. The orchestrator runs in a worker thread on the
      // server; each poll captures a snapshot of its in-progress state.
      const verification = await api.runTestGen(sid, "", "", 0, view => {
        if (view.progress) patch({ progress: view.progress });
      });
      patch({ testGenResult: verification, loading: false });
      if (aborted.current) return;
      await delay(1000);

      // ─── Step 6: Results ───
      setStep(6);

    } catch (e: any) {
      patch({ loading: false, error: e.message });
    }
  }, [patch, setStep]);

  const abort = useCallback(() => { aborted.current = true; }, []);

  return { run, abort };
}

function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
