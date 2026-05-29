import { useRef, useCallback } from "react";
import type { SessionState } from "./useSession";
import * as api from "../api";

/**
 * Auto-runner: runs the real QALLM pipeline as a single call and renders
 * its live progress.
 *
 * Design (post-convergence). Earlier builds sequenced a hand-rolled
 * analyse -> repair -> re-analyse mini-loop on the client and *then* also
 * called the verification step, which itself runs the full orchestrator
 * loop (orch.run). The effect was that repair ran twice: once standalone,
 * once inside the loop, against two different baselines. That contradicted
 * the workflow design, where repair happens only inside a round, after the
 * baseline.
 *
 * The corrected flow has exactly one source of truth for the loop, the
 * orchestrator:
 *
 *   Step 2  Baseline   one static-analysis pass so the user sees the
 *                      round-0 starting point and can confirm the code
 *                      parsed. This is read-only; it does not repair.
 *   Step 3  Rounds     api.runTestGen submits /api/verification/run, which
 *                      calls orch.run(): baseline -> N rounds of
 *                      (repair -> analyse -> verify -> judge), budget
 *                      capped, with per-unit accept/abandon. Live progress
 *                      is forwarded into session state for the rounds view.
 *   Step 4  Report     the final lineage, verdicts, halt reason, budget.
 *
 * ``run`` takes ``sessionId`` and ``files`` explicitly rather than reading
 * the captured ``state`` closure: ``onSessionReady`` calls ``run()``
 * immediately after ``patch({ sessionId })`` and React state updates are
 * asynchronous, so the closure would still hold the pre-upload value.
 */
export function useAutoRunner(
  _state: SessionState,
  patch: (p: Partial<SessionState>) => void,
  setStep: (step: number) => void,
) {
  const aborted = useRef(false);

  const run = useCallback(async (sessionId: string, files: string[]) => {
    if (!sessionId) return;
    aborted.current = false;
    const sid = sessionId;

    try {
      // --- Step 2: Baseline (round 0 preview, read-only) ---
      setStep(2);
      patch({ loading: true, error: null });
      await delay(400); // let the UI render

      const tools = await api.getAnalysisTools();
      const baseline = await api.runAnalysis(sid, files, tools.tools);
      const rounds = await api.getAnalysisHistory(sid).catch(() => []);
      patch({
        summary: baseline.summary,
        findings: baseline.findings,
        analysisRounds: rounds,
        loading: false,
      });
      if (aborted.current) return;
      await delay(1200); // pause so the user sees the baseline

      // --- Step 3: Improvement rounds (the real loop) ---
      setStep(3);
      patch({ loading: true, progress: null });
      await delay(400);

      // Session config was locked in at upload. The backend runs the full
      // loop (orch.run) on submit; the args here are the back-compat shape.
      // Live progress is forwarded so the rounds view can render phase,
      // current round, stage, unit, and accepted/abandoned counts.
      const verification = await api.runTestGen(sid, "", "", 0, view => {
        if (view.progress) patch({ progress: view.progress });
      });
      patch({ testGenResult: verification, loading: false });
      if (aborted.current) return;
      await delay(800);

      // --- Step 4: Report ---
      setStep(4);
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
