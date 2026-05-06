import { Shield } from "lucide-react";
import StepRail from "./components/StepRail";
import { NextBar } from "./components/Shared";
import { useSession } from "./hooks/useSession";
import UploadScreen from "./screens/UploadScreen";
import AnalyseScreen from "./screens/AnalyseScreen";
import RepairScreen from "./screens/RepairScreen";
import ReanalyseScreen from "./screens/ReanalyseScreen";
import TestGenScreen from "./screens/TestGenScreen";
import RLScreen from "./screens/RLScreen";

const STEPS = 6;

export default function App() {
  const { state, patch, setStep } = useSession();

  const screen = (() => {
    switch (state.step) {
      case 1: return <UploadScreen state={state} patch={patch} />;
      case 2: return <AnalyseScreen state={state} patch={patch} />;
      case 3: return <RepairScreen state={state} patch={patch} />;
      case 4: return <ReanalyseScreen state={state} patch={patch} />;
      case 5: return <TestGenScreen state={state} patch={patch} />;
      case 6: return <RLScreen state={state} />;
      default: return null;
    }
  })();

  const canNext = (() => {
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
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Quality Assessment of AI-Generated Code (NEW)</h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">Static analysis, LLM repair, and RL-guided test generation in one pipeline.</p>
          </div>
          {state.sessionId && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs text-slate-500 shadow-sm">
              Session: <span className="font-mono font-medium text-slate-700">{state.sessionId.slice(0, 8)}</span>
            </div>
          )}
        </div>
        <StepRail currentStep={state.step} onStepClick={setStep} />
        <div className="min-h-[400px]">{screen}</div>
        <NextBar step={state.step} maxStep={STEPS} onPrev={() => setStep(Math.max(1, state.step - 1))} onNext={() => canNext && setStep(Math.min(STEPS, state.step + 1))} nextDisabled={!canNext} />
      </div>
    </div>
  );
}
