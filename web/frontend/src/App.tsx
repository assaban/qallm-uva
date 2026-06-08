import { useState } from "react";
import { Shield, FlaskConical, Library, Sparkles, BookOpen } from "lucide-react";
import StepRail from "./components/StepRail";
import { NextBar } from "./components/Shared";
import { useSession } from "./hooks/useSession";
import { useAutoRunner } from "./hooks/useAutoRunner";
import UploadScreen from "./screens/UploadScreen";
import AnalyseScreen from "./screens/AnalyseScreen";
import RepairScreen from "./screens/RepairScreen";
import ReanalyseScreen from "./screens/ReanalyseScreen";
import TestGenScreen from "./screens/TestGenScreen";
import ResultsScreen from "./screens/ResultsScreen";
import ExperimentsView from "./screens/ExperimentsView";
import SessionsView from "./screens/SessionsView";
import AboutView from "./screens/AboutView";
import DocsView from "./screens/DocsView";

const STEPS_MANUAL = 6;
const STEPS_AUTO = 4;

export default function App() {
  const { state, patch, setStep } = useSession();
  const [mode, setMode] = useState<"manual" | "auto">("manual");
  const [view, setView] = useState<"pipeline" | "experiments" | "sessions" | "about" | "docs">("pipeline");
  const autoRunner = useAutoRunner(state, patch, setStep);

  // Called by UploadScreen after successful upload. We accept the
  // sessionId and files explicitly because React state updates are
  // asynchronous; the global `state` will not yet reflect the upload
  // when this is invoked. Reading state.sessionId here would see the
  // pre-upload value and the auto-runner would bail silently.
  function onSessionReady(autoMode: boolean, sessionId: string, files: string[]) {
    setMode(autoMode ? "auto" : "manual");
    if (autoMode) {
      autoRunner.run(sessionId, files);
    } else {
      setStep(2);
    }
  }

  // Screen routing is mode-aware. Auto mode runs the real pipeline in
  // four phases (Upload, Baseline, Improvement rounds, Report) and maps
  // step 3 to the live rounds view and step 4 to the report. Manual mode
  // keeps the six-stage inspectable breakdown.
  const screen = (() => {
    if (mode === "auto") {
      switch (state.step) {
        case 1: return <UploadScreen state={state} patch={patch} onSessionReady={onSessionReady} />;
        case 2: return <AnalyseScreen state={state} patch={patch} autoMode />;
        case 3: return <TestGenScreen state={state} patch={patch} autoMode />;
        case 4: return <ResultsScreen state={state} />;
        default: return null;
      }
    }
    switch (state.step) {
      case 1: return <UploadScreen state={state} patch={patch} onSessionReady={onSessionReady} />;
      case 2: return <AnalyseScreen state={state} patch={patch} autoMode={false} />;
      case 3: return <RepairScreen state={state} patch={patch} autoMode={false} />;
      case 4: return <ReanalyseScreen state={state} patch={patch} />;
      case 5: return <TestGenScreen state={state} patch={patch} autoMode={false} />;
      case 6: return <ResultsScreen state={state} />;
      default: return null;
    }
  })();

  const maxStep = mode === "auto" ? STEPS_AUTO : STEPS_MANUAL;

  const canNext = (() => {
    if (mode === "auto") {
      switch (state.step) {
        case 1: return !!state.sessionId;
        case 2: return state.findings.length > 0 || state.summary !== null;
        case 3: return state.testGenResult !== null;
        default: return false;
      }
    }
    switch (state.step) {
      case 1: return !!state.sessionId;
      case 2: return state.findings.length > 0 || state.summary !== null;
      case 3: return state.repairResult !== null;
      case 4: return state.analysisRounds.length >= 2;
      case 5: return state.testGenResult !== null;
      default: return false;
    }
  })();

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-indigo-50/30 to-slate-50 p-4 text-slate-900 md:p-6">
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 shadow-sm">
              <Shield className="h-3.5 w-3.5" /> QALLM Pipeline
              {mode === "auto" && state.loading && (
                <span className="ml-1 inline-flex items-center gap-1 text-indigo-600">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
                  Auto-running
                </span>
              )}
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Execution-Based Code Quality Assessment</h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">Baseline, then LLM repair and execution-based verification across budget-capped rounds, judged against a quality model.</p>
          </div>
          {state.sessionId && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs text-slate-500 shadow-sm">
              Session: <span className="font-mono font-medium text-slate-700">{state.sessionId.slice(0, 8)}</span>
              {mode === "auto" && <span className="ml-2 rounded bg-indigo-100 px-1.5 py-0.5 text-indigo-700 font-medium">AUTO</span>}
            </div>
          )}
        </div>

        {/* Top-level view switch: the step-based pipeline vs read-only
            browsing of historical validation experiments. */}
        <div className="flex gap-1 rounded-xl border border-slate-200 bg-white p-1 text-sm shadow-sm w-fit">
          <button
            onClick={() => setView("pipeline")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium ${view === "pipeline" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
          >
            <Shield className="h-3.5 w-3.5" /> Pipeline
          </button>
          <button
            onClick={() => setView("experiments")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium ${view === "experiments" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
          >
            <FlaskConical className="h-3.5 w-3.5" /> Experiments
          </button>
          <button
            onClick={() => setView("sessions")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium ${view === "sessions" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
          >
            <Library className="h-3.5 w-3.5" /> Sessions
          </button>
          <button
            onClick={() => setView("about")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium ${view === "about" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
          >
            <Sparkles className="h-3.5 w-3.5" /> The Gap
          </button>
          <button
            onClick={() => setView("docs")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium ${view === "docs" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-50"}`}
          >
            <BookOpen className="h-3.5 w-3.5" /> Docs
          </button>
        </div>
        {/* Step navigation: locked while an auto run is in flight to
            prevent the user from disrupting the pipeline. Once the run
            ends (success OR failure), navigation is re-enabled so the
            user can review or retry. Without this, an auto-mode run
            that errors out leaves the user trapped on the failed step. */}
        {view === "experiments" ? (
          <div className="min-h-[400px]">
            <ExperimentsView />
          </div>
        ) : view === "about" ? (
          <div className="min-h-[400px]">
            <AboutView />
          </div>
        ) : view === "sessions" ? (
          <div className="min-h-[400px]">
            <SessionsView />
          </div>
        ) : view === "docs" ? (
          <div className="min-h-[400px]">
            <DocsView />
          </div>
        ) : (
          <>
            <StepRail
              currentStep={state.step}
              mode={mode}
              onStepClick={(mode === "auto" && state.loading) ? () => {} : setStep}
            />
            {/* Manual-mode preview banner. In manual mode, steps 2 to 4 let
                the user inspect a static-analysis baseline and a single LLM
                repair pass. These are a teaching preview: the full pipeline,
                with all rounds and judge accept/abandon decisions, runs in the
                "Run pipeline" step. Auto mode has no such preview, it runs the
                real loop directly, so this banner is manual-only. */}
            {mode === "manual" && state.step >= 2 && state.step <= 4 && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-xs text-blue-800">
                <span className="font-semibold">Preview stages.</span>{" "}
                Steps 2 to 4 let you inspect a static-analysis baseline and a
                single LLM repair pass, so you can confirm your code parses and
                see what one repair looks like. The full QALLM pipeline (all
                rounds of repair, verification, and judge accept/abandon) runs
                in the "Run pipeline" step against its own baseline. To run the
                real pipeline directly, start a new session in Auto mode.
              </div>
            )}
            {state.error && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                <div>{state.error}</div>
                {mode === "auto" && (
                  <div className="mt-2 text-xs text-red-600">
                    Auto mode halted. Use the step rail above to navigate back
                    and review earlier stages, or refresh the page to start over.
                  </div>
                )}
              </div>
            )}
            <div className="min-h-[400px]">{screen}</div>
            {/* NextBar visible whenever navigation is allowed. */}
            {!(mode === "auto" && state.loading) && (
              <NextBar
                step={state.step} maxStep={maxStep}
                onPrev={() => setStep(Math.max(1, state.step - 1))}
                onNext={() => canNext && setStep(Math.min(maxStep, state.step + 1))}
                nextDisabled={!canNext}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
